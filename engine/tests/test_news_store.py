import pytest

from csb.db import connect, init_schema
from csb.models import Headline, HeadlineScore, NewsState
from csb.news_feeds import Feed
from csb.news_store import (
    mark_error,
    news_view,
    pending_headlines,
    record_source,
    save_headlines,
    save_scores,
)
from csb.strategy import StrategyParams

HOUR = 3_600_000
NOW = 1_800_000_000_000
P = StrategyParams()


@pytest.fixture
def conn(tmp_path):
    c = connect(tmp_path / "n.sqlite3")
    init_schema(c)
    return c


def headline(n, age_hours=1.0, source="Example"):
    return Headline(source, "news", f"Headline {n}", f"https://example.com/{n}", int(NOW - age_hours * HOUR))


def add(conn, n, age_hours, coin="BTC", direction=1, strength=1.0, confidence=1.0):
    save_headlines(conn, [headline(n, age_hours)], NOW)
    news_id = conn.execute("select id from news_items where url = ?", (f"https://example.com/{n}",)).fetchone()["id"]
    save_scores(conn, {news_id: [HeadlineScore(coin, direction, strength, confidence, "because")]}, "stub", "m", NOW)
    return news_id


def test_save_headlines_dedupes_by_url(conn):
    assert save_headlines(conn, [headline(1), headline(2)], NOW) == 2
    assert save_headlines(conn, [headline(2), headline(3)], NOW) == 1
    assert conn.execute("select count(*) as n from news_items").fetchone()["n"] == 3


def test_new_headlines_are_unscored_and_pending_newest_first(conn):
    save_headlines(conn, [headline(1, 5), headline(2, 1), headline(3, 60)], NOW)
    pending = pending_headlines(conn, NOW, max_age_ms=48 * HOUR, limit=10)
    assert [title for _, title in pending] == ["Headline 2", "Headline 1"]  # the 60h-old one is too old
    statuses = {r["score_status"] for r in conn.execute("select score_status from news_items")}
    assert statuses == {"unscored"}


def test_scored_headlines_leave_the_pending_queue_even_with_no_affected_coin(conn):
    save_headlines(conn, [headline(1), headline(2)], NOW)
    ids = [i for i, _ in pending_headlines(conn, NOW, 48 * HOUR, 10)]
    save_scores(conn, {ids[0]: [HeadlineScore("BTC", 1, 0.5, 0.5, "x")], ids[1]: []}, "stub", "m", NOW)
    assert pending_headlines(conn, NOW, 48 * HOUR, 10) == []
    assert conn.execute("select count(*) as n from news_scores").fetchone()["n"] == 1


def test_failed_batches_are_marked_and_retried(conn):
    save_headlines(conn, [headline(1)], NOW)
    ids = [i for i, _ in pending_headlines(conn, NOW, 48 * HOUR, 10)]
    mark_error(conn, ids, "provider returned HTTP 500")
    row = conn.execute("select score_status, score_error from news_items").fetchone()
    assert (row["score_status"], row["score_error"]) == ("error", "provider returned HTTP 500")
    assert len(pending_headlines(conn, NOW, 48 * HOUR, 10)) == 1


def test_news_view_is_off_when_scoring_disabled_even_if_scores_exist(conn):
    add(conn, 1, 1)
    view = news_view(conn, "BTC", NOW, enabled=False, params=P)
    assert view.state is NewsState.OFF and view.score is None and view.headlines == []


def test_news_view_reports_no_headlines_for_a_coin_without_scores(conn):
    add(conn, 1, 1, coin="BTC")
    view = news_view(conn, "ETH", NOW, enabled=True, params=P)
    assert view.state is NewsState.NO_HEADLINES and view.score is None


def test_news_view_weights_by_confidence_and_recency(conn):
    add(conn, 1, age_hours=0, direction=1, strength=1.0, confidence=1.0)  # weight 1.0
    add(conn, 2, age_hours=12, direction=-1, strength=1.0, confidence=1.0)  # weight 0.5
    view = news_view(conn, "BTC", NOW, enabled=True, params=P)
    assert view.score == pytest.approx((1.0 - 0.5) / 1.5)
    assert view.state is NewsState.BOOST
    assert [h.title for h in view.headlines] == ["Headline 1", "Headline 2"]
    assert view.headlines[0].score.direction == 1


def test_single_weak_headline_cannot_produce_extreme_score(conn):
    add(conn, 1, age_hours=0, direction=-1, strength=1.0, confidence=0.2)
    view = news_view(conn, "BTC", NOW, enabled=True, params=P)
    assert view.score == pytest.approx(-0.2)  # 0.2 * -1 / max(0.2, 1.0)
    assert view.state is NewsState.NEUTRAL


def test_strong_bearish_news_produces_veto(conn):
    add(conn, 1, age_hours=0, direction=-1, strength=0.9, confidence=0.9)
    add(conn, 2, age_hours=1, direction=-1, strength=0.8, confidence=0.9)
    assert news_view(conn, "BTC", NOW, enabled=True, params=P).state is NewsState.VETO


def test_headlines_older_than_lookback_or_from_the_future_are_ignored(conn):
    add(conn, 1, age_hours=25)
    add(conn, 2, age_hours=-1)
    assert news_view(conn, "BTC", NOW, enabled=True, params=P).state is NewsState.NO_HEADLINES


def test_record_source_tracks_last_success_and_last_error(conn):
    feed = Feed("Example", "news", "https://example.com/rss")
    record_source(conn, feed, ok=True, error=None, count=12, now_ms=NOW)
    record_source(conn, feed, ok=False, error="HTTP 403", count=0, now_ms=NOW + 1000)
    row = conn.execute("select * from news_sources where name = 'Example'").fetchone()
    assert row["last_ok_at"] == NOW and row["last_attempt_at"] == NOW + 1000
    assert row["last_error"] == "HTTP 403" and row["last_count"] == 0
