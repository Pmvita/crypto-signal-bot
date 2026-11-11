"""Headline and score persistence, and the per-coin news score the strategy is given."""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping, Sequence

from csb.candles import HOUR_MS
from csb.models import Headline, HeadlineScore, NewsState, NewsView, ScoredHeadline
from csb.news_feeds import Feed
from csb.strategy import StrategyParams, news_state_for

NEWS_LOOKBACK_MS = 24 * HOUR_MS


def save_headlines(conn: sqlite3.Connection, headlines: Sequence[Headline], now_ms: int) -> int:
    """Insert headlines not seen before (keyed by URL). Returns how many were new."""
    before = conn.total_changes
    conn.executemany(
        "insert or ignore into news_items (source, kind, title, url, published_at, fetched_at)"
        " values (?, ?, ?, ?, ?, ?)",
        [(h.source, h.kind, h.title, h.url, h.published_at, now_ms) for h in headlines],
    )
    conn.commit()
    return conn.total_changes - before


def record_source(conn: sqlite3.Connection, feed: Feed, ok: bool, error: str | None, count: int, now_ms: int) -> None:
    conn.execute(
        """
        insert into news_sources (name, kind, url, last_attempt_at, last_ok_at, last_error, last_count)
        values (?, ?, ?, ?, ?, ?, ?)
        on conflict (name) do update set
            kind = excluded.kind, url = excluded.url, last_attempt_at = excluded.last_attempt_at,
            last_ok_at = coalesce(excluded.last_ok_at, news_sources.last_ok_at),
            last_error = excluded.last_error, last_count = excluded.last_count
        """,
        (feed.name, feed.kind, feed.url, now_ms, now_ms if ok else None, error, count),
    )
    conn.commit()


def pending_headlines(conn: sqlite3.Connection, now_ms: int, max_age_ms: int, limit: int) -> list[tuple[int, str]]:
    """Recent headlines that still need a score (never scored, or the last attempt failed), newest first."""
    rows = conn.execute(
        """
        select id, title from news_items
        where score_status in ('unscored', 'error') and published_at >= ?
        order by published_at desc, id desc limit ?
        """,
        (now_ms - max_age_ms, limit),
    ).fetchall()
    return [(r["id"], r["title"]) for r in rows]


def save_scores(
    conn: sqlite3.Connection, scores: Mapping[int, Sequence[HeadlineScore]], provider: str, model: str, now_ms: int
) -> None:
    for news_id, entries in scores.items():
        conn.execute("delete from news_scores where news_id = ?", (news_id,))
        conn.executemany(
            "insert into news_scores (news_id, coin, direction, strength, confidence, rationale, provider, model,"
            " scored_at) values (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (news_id, s.coin, s.direction, s.strength, s.confidence, s.rationale, provider, model, now_ms)
                for s in entries
            ],
        )
        conn.execute("update news_items set score_status = 'scored', score_error = null where id = ?", (news_id,))
    conn.commit()


def mark_error(conn: sqlite3.Connection, ids: Sequence[int], error: str) -> None:
    conn.executemany(
        "update news_items set score_status = 'error', score_error = ? where id = ?",
        [(error[:500], news_id) for news_id in ids],
    )
    conn.commit()


def news_view(
    conn: sqlite3.Connection,
    coin: str,
    now_ms: int,
    enabled: bool,
    params: StrategyParams,
    lookback_ms: int = NEWS_LOOKBACK_MS,
) -> NewsView:
    """Confidence- and recency-weighted score for one coin over the lookback window.

    weight = confidence x (1 - age / lookback); score = sum(weight x direction x strength) / max(sum(weight), 1)
    """
    if not enabled:
        return NewsView(NewsState.OFF, None, [])
    rows = conn.execute(
        """
        select n.id, n.source, n.title, n.url, n.published_at,
               s.coin, s.direction, s.strength, s.confidence, s.rationale
        from news_scores s join news_items n on n.id = s.news_id
        where s.coin = ? and n.published_at > ? and n.published_at <= ?
        order by n.published_at desc, n.id desc
        """,
        (coin, now_ms - lookback_ms, now_ms),
    ).fetchall()
    if not rows:
        return NewsView(NewsState.NO_HEADLINES, None, [])

    weighted, total_weight = 0.0, 0.0
    headlines: list[ScoredHeadline] = []
    for r in rows:
        weight = r["confidence"] * (1 - (now_ms - r["published_at"]) / lookback_ms)
        weighted += weight * r["direction"] * r["strength"]
        total_weight += weight
        score = HeadlineScore(r["coin"], r["direction"], r["strength"], r["confidence"], r["rationale"])
        headlines.append(ScoredHeadline(r["id"], r["source"], r["title"], r["url"], r["published_at"], score))
    value = weighted / max(total_weight, 1.0)
    return NewsView(news_state_for(value, True, params), value, headlines)
