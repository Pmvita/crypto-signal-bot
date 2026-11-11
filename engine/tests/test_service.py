import json
from datetime import UTC, datetime
from email.utils import format_datetime

import httpx
import pytest

from csb.candles import BAR_MS, HOUR_MS, upsert_candles
from csb.config import load_settings
from csb.db import connect, get_meta, init_schema
from csb.models import Candle, HeadlineScore, Position, PositionSide, Quote
from csb.news_feeds import Feed
from csb.news_scoring import ScoringError
from csb.portfolio import load_portfolio, save_portfolio
from csb.risk import RiskManager, SqliteRiskStore, utc_day
from csb.service import TradingService, scoring_status
from csb.strategy import StrategyParams

T0 = 1_700_006_400_000
PARAMS = StrategyParams(ema_fast=3, ema_slow=6, breakout_bars=3, atr_period=3)
# Flat for 8 fifteen-minute bars, then a rising bar that breaks out: bar 8 is an entry signal.
CLOSES = [100.0] * 8 + [102.0]
SIGNAL_BAR = 8
NOW = T0 + (SIGNAL_BAR + 1) * BAR_MS + 60_000  # one minute after the signal bar closed
FEED = Feed("Example", "news", "https://example.com/rss")


def bars_from(closes, t0=T0):
    """One 15m candle per close."""
    out, prev = [], closes[0]
    for i, close in enumerate(closes):
        out.append(
            Candle(
                t0 + i * BAR_MS,
                prev,
                max(prev, close) + 0.5,
                min(prev, close) - 0.5,
                close,
                1.0,
            )
        )
        prev = close
    return out


class FakeMarket:
    exchange_id = "fake"

    def __init__(self, price=102.0):
        self.price = price
        self.fail = None

    def update(self, symbol):
        if self.fail:
            raise self.fail
        return 0

    def quote(self, symbol):
        return Quote(symbol, bid=self.price - 0.1, ask=self.price + 0.1, last=self.price, ts=NOW)


class StubScorer:
    provider = "stub"
    model = "stub-1"

    def __init__(self, direction=0, fail=False):
        self.direction = direction
        self.fail = fail
        self.calls = 0

    def score(self, headlines, coins):
        self.calls += 1
        if self.fail:
            raise ScoringError("stub provider is down")
        return {i: [HeadlineScore("BTC", self.direction, 0.9, 0.9, "stub rationale")] for i, _ in headlines}


def rss(now_ms, n=2):
    when = format_datetime(datetime.fromtimestamp((now_ms - HOUR_MS) / 1000, tz=UTC))
    items = "".join(
        f"<item><title>Headline {i}</title><link>https://example.com/{i}</link><pubDate>{when}</pubDate></item>"
        for i in range(n)
    )
    return f'<?xml version="1.0"?><rss version="2.0"><channel><title>x</title>{items}</channel></rss>'.encode()


def http_client(status=200, now_ms=NOW):
    def handler(request):
        return httpx.Response(status, content=rss(now_ms) if status == 200 else b"")

    return httpx.Client(transport=httpx.MockTransport(handler))


@pytest.fixture
def env(tmp_path):
    settings = load_settings({"CSB_SYMBOLS": "BTC/USD", "CSB_DB_PATH": str(tmp_path / "s.sqlite3")})
    conn = connect(settings.db_path)
    init_schema(conn)
    upsert_candles(conn, "fake", "BTC/USD", "15m", bars_from(CLOSES))
    return settings, conn


def make(env, scorer=None, market=None, clock=lambda: NOW, status=200):
    settings, conn = env
    reason = None if scorer else "No LLM API key configured: OPENAI_API_KEY is not set in .env."
    return TradingService(
        settings,
        conn,
        market or FakeMarket(),
        scorer,
        reason,
        http_client=http_client(status),
        clock=clock,
        feeds=(FEED,),
        params=PARAMS,
    )


def rows(conn, table):
    return [dict(r) for r in conn.execute(f"select * from {table} order by 1")]


def test_refresh_market_data_updates_quotes_without_signals_or_orders(env):
    _, conn = env
    summary = make(env).refresh_market_data()
    assert "candles_added" in summary
    assert rows(conn, "signals") == []
    assert rows(conn, "orders") == []
    assert rows(conn, "cycles") == []
    assert rows(conn, "quotes")[0]["last"] == 102.0
    assert len(rows(conn, "equity_snapshots")) == 1


def test_cycle_records_signal_and_fills_long_entry_at_live_quote(env):
    _, conn = env
    summary = make(env).run_cycle()
    assert summary["status"] == "ok" and summary["error"] is None

    (signal,) = rows(conn, "signals")
    assert signal["action"] == "enter" and signal["symbol"] == "BTC/USD"
    assert signal["ts"] == T0 + SIGNAL_BAR * BAR_MS
    indicators = json.loads(signal["indicators"])
    assert indicators["close"] == 102.0
    assert indicators["side"] == "long"
    assert len(json.loads(signal["reasons"])) >= 3
    assert any("LONG" in r for r in json.loads(signal["reasons"]))

    (order,) = rows(conn, "orders")
    assert order["status"] == "filled" and order["side"] == "buy" and order["broker"] == "paper"
    assert order["signal_id"] == signal["id"]
    assert order["fill_price"] == pytest.approx(102.1 * 1.0005)  # live ask plus slippage
    assert order["fee"] == pytest.approx(order["qty"] * order["fill_price"] * 0.004)

    portfolio = load_portfolio(conn, 10_000)
    position = portfolio.positions["BTC/USD"]
    assert position.side is PositionSide.LONG
    assert position.qty == pytest.approx(order["qty"])
    assert position.stop_price == pytest.approx(indicators["stop"])
    assert portfolio.cash == pytest.approx(10_000 - order["qty"] * order["fill_price"] * 1.004)

    assert len(rows(conn, "equity_snapshots")) == 1
    (cycle,) = rows(conn, "cycles")
    assert cycle["status"] == "ok" and cycle["finished_at"] is not None
    assert rows(conn, "quotes")[0]["last"] == 102.0


def test_bar_is_evaluated_once_across_cycles(env):
    _, conn = env
    service = make(env)
    service.run_cycle()
    service.run_cycle()
    assert len(rows(conn, "signals")) == 1
    assert len(rows(conn, "orders")) == 1
    assert len(rows(conn, "cycles")) == 2


def test_kill_switch_stops_all_orders_but_signals_are_still_recorded(env):
    settings, conn = env
    api_conn = connect(settings.db_path)  # the API uses its own connection
    RiskManager(SqliteRiskStore(api_conn)).set_kill_switch(True)

    summary = make(env).run_cycle()
    assert summary["status"] == "ok"
    (signal,) = rows(conn, "signals")
    assert signal["action"] == "enter"
    (order,) = rows(conn, "orders")
    assert order["status"] == "rejected" and "kill switch" in order["reject_reason"].lower()
    assert order["fill_price"] is None
    portfolio = load_portfolio(conn, 10_000)
    assert portfolio.positions == {} and portfolio.cash == 10_000


def test_kill_switch_also_blocks_exits(env):
    settings, conn = env
    portfolio = load_portfolio(conn, 10_000)
    portfolio.positions["BTC/USD"] = Position(
        "BTC/USD", 1.0, 100.0, T0, stop_price=500.0, highest_close=500.0, side=PositionSide.LONG
    )
    save_portfolio(conn, portfolio)
    RiskManager(SqliteRiskStore(conn)).set_kill_switch(True)

    make(env).run_cycle()
    assert rows(conn, "signals")[0]["action"] == "exit"
    assert rows(conn, "orders")[0]["status"] == "rejected"
    assert "BTC/USD" in load_portfolio(conn, 10_000).positions


def test_daily_loss_limit_trips_in_the_cycle_and_rejects_the_entry(env):
    _, conn = env
    store = SqliteRiskStore(conn)
    store.save_day(utc_day(NOW), 10_400.0, False, None)  # the day started 4% higher than equity is now

    make(env).run_cycle()
    state = RiskManager(store).state
    assert state.halted and state.halted_at == NOW
    (order,) = rows(conn, "orders")
    assert order["status"] == "rejected" and "daily loss" in order["reject_reason"].lower()
    assert load_portfolio(conn, 10_000).positions == {}


def test_daily_loss_halt_still_allows_the_exit(env):
    _, conn = env
    portfolio = load_portfolio(conn, 10_000)
    portfolio.cash = 9_900.0
    portfolio.positions["BTC/USD"] = Position(
        "BTC/USD", 1.0, 100.0, T0, stop_price=500.0, highest_close=500.0, side=PositionSide.LONG
    )
    save_portfolio(conn, portfolio)
    SqliteRiskStore(conn).save_day(utc_day(NOW), 10_500.0, False, None)

    make(env).run_cycle()
    assert RiskManager(SqliteRiskStore(conn)).state.halted
    (order,) = rows(conn, "orders")
    assert (order["side"], order["status"]) == ("sell", "filled")
    assert order["fill_price"] == pytest.approx(101.9 * 0.9995)  # live bid minus slippage
    assert order["realized_pnl"] == pytest.approx(order["fill_price"] - 100.0 - order["fee"])
    assert load_portfolio(conn, 10_000).positions == {}


def test_stale_market_data_is_not_traded(env):
    _, conn = env
    later = NOW + 3 * 24 * HOUR_MS
    summary = make(env, clock=lambda: later).run_cycle()
    assert summary["status"] == "ok"
    assert rows(conn, "signals") == [] and rows(conn, "orders") == []
    assert any("BTC/USD" in s for s in summary["skipped"])


def test_bar_waits_for_closed_15m_candle(env):
    _, conn = env
    signal_ts = T0 + SIGNAL_BAR * BAR_MS
    conn.execute("delete from candles where ts = ?", (signal_ts,))
    conn.commit()
    service = make(env)
    service.run_cycle()
    assert rows(conn, "signals") == []

    upsert_candles(conn, "fake", "BTC/USD", "15m", [c for c in bars_from(CLOSES) if c.ts == signal_ts])
    service.run_cycle()
    assert len(rows(conn, "signals")) == 1


def test_without_scorer_headlines_stay_unscored_and_news_state_is_off(env):
    settings, conn = env
    summary = make(env).run_cycle()
    assert summary["news"]["new"] == 2 and summary["news"]["scoring"] == "off"
    assert {r["score_status"] for r in rows(conn, "news_items")} == {"unscored"}
    assert rows(conn, "news_scores") == []
    signal = rows(conn, "signals")[0]
    assert signal["news_state"] == "off" and signal["news_score"] is None
    assert signal["action"] == "enter"  # price rules still trade with news off
    status = scoring_status(conn, settings, None, "No LLM API key configured: OPENAI_API_KEY is not set in .env.")
    assert status["enabled"] is False and "OPENAI_API_KEY" in status["reason"]


def test_news_veto_from_stub_scorer_blocks_entry_and_links_headlines(env):
    _, conn = env
    scorer = StubScorer(direction=-1)
    make(env, scorer=scorer).run_cycle()
    assert scorer.calls == 1
    assert {r["score_status"] for r in rows(conn, "news_items")} == {"scored"}
    (signal,) = rows(conn, "signals")
    assert signal["action"] == "hold" and signal["news_state"] == "veto"
    assert signal["news_score"] < -0.30
    assert sorted(json.loads(signal["news_ids"])) == sorted(r["id"] for r in rows(conn, "news_items"))
    assert rows(conn, "orders") == []


def test_news_boost_from_stub_scorer_enlarges_the_entry(env):
    _, conn = env
    make(env, scorer=StubScorer(direction=1)).run_cycle()
    (signal,) = rows(conn, "signals")
    assert signal["action"] == "enter" and signal["news_state"] == "boost" and signal["size_multiplier"] == 1.25
    atr_value = json.loads(signal["indicators"])["atr"]
    (order,) = rows(conn, "orders")
    assert order["requested_qty"] == pytest.approx(10_000 * 0.01 * 1.25 / (3 * atr_value))


def test_scoring_failure_is_surfaced_and_does_not_invent_scores(env):
    settings, conn = env
    scorer = StubScorer(fail=True)
    summary = make(env, scorer=scorer).run_cycle()
    assert summary["status"] == "ok"
    assert {r["score_status"] for r in rows(conn, "news_items")} == {"error"}
    assert rows(conn, "news_scores") == []
    assert rows(conn, "signals")[0]["news_state"] == "no_headlines"
    assert "stub provider is down" in scoring_status(conn, settings, scorer, None)["last_error"]


def test_failing_feed_is_recorded_and_the_cycle_continues(env):
    _, conn = env
    summary = make(env, status=403).run_cycle()
    assert summary["status"] == "ok"
    assert summary["news"]["failed_sources"] == ["Example"]
    (source,) = rows(conn, "news_sources")
    assert source["last_error"] == "HTTP 403" and source["last_ok_at"] is None
    assert len(rows(conn, "signals")) == 1


def test_news_is_refetched_only_after_the_refresh_interval(env):
    clock = {"now": NOW}
    service = make(env, clock=lambda: clock["now"])
    assert service.run_cycle()["news"] is not None
    clock["now"] = NOW + 60_000
    assert service.run_cycle()["news"] is None
    clock["now"] = NOW + 601_000
    assert service.run_cycle()["news"] is not None


def test_cycle_error_is_recorded_and_does_not_raise(env):
    _, conn = env
    market = FakeMarket()
    market.fail = RuntimeError("exchange unreachable")
    summary = make(env, market=market).run_cycle()
    assert summary["status"] == "error" and "exchange unreachable" in summary["error"]
    (cycle,) = rows(conn, "cycles")
    assert cycle["status"] == "error" and "exchange unreachable" in cycle["error"]
    assert rows(conn, "orders") == []


def test_trailing_stop_is_persisted_while_holding(env):
    _, conn = env
    portfolio = load_portfolio(conn, 10_000)
    portfolio.positions["BTC/USD"] = Position(
        "BTC/USD", 1.0, 100.0, T0, stop_price=90.0, highest_close=100.0, side=PositionSide.LONG
    )
    save_portfolio(conn, portfolio)
    make(env).run_cycle()
    signal = rows(conn, "signals")[0]
    assert signal["action"] == "hold"
    position = load_portfolio(conn, 10_000).positions["BTC/USD"]
    assert position.highest_close == 102.0
    assert position.stop_price == pytest.approx(json.loads(signal["indicators"])["stop"])
    assert position.stop_price > 90.0
    assert get_meta(conn, "last_eval:BTC/USD") == str(T0 + SIGNAL_BAR * BAR_MS)
