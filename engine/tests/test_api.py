import pytest
from fastapi.testclient import TestClient

from csb.api import create_app
from csb.config import load_settings
from csb.db import connect, init_schema
from csb.models import Headline, Quote
from csb.news_store import save_headlines
from csb.service import TradingService


@pytest.fixture
def client(tmp_path):
    db = tmp_path / "api.sqlite3"
    settings = load_settings(
        {
            "CSB_DB_PATH": str(db),
            "CSB_EXCHANGE": "fake",
            "CSB_SYMBOLS": "BTC/USD,ETH/USD",
            "CSB_STARTING_CASH": "10000",
            "OPENAI_API_KEY": "",
            "OPENAI_MODEL": "",
        }
    )

    def factory(s, conn):
        class StubMarket:
            exchange_id = "fake"

            def update(self, symbol):
                return 0

            def quote(self, symbol):
                return Quote(symbol, 100.0, 100.2, 100.1, 1_700_000_000_000)

        reason = "No LLM API key configured: OPENAI_API_KEY is not set in .env."
        return TradingService(s, conn, StubMarket(), None, reason)

    app = create_app(settings, start_loop=False, service_factory=factory)
    with TestClient(app) as c:
        yield c, settings, db


def test_status_reports_paper_mode_and_live_trading_unavailable(client):
    c, _, _ = client
    body = c.get("/api/status").json()
    assert body["mode"] == "paper"
    assert body["live_trading"]["available"] is False


def test_status_reports_scoring_off_without_key(client):
    c, _, _ = client
    ns = c.get("/api/status").json()["news_scoring"]
    assert ns["enabled"] is False
    assert "OPENAI_API_KEY" in ns["reason"]


def test_kill_switch_round_trip_and_persists(client):
    c, _, db = client
    assert c.get("/api/risk").json()["kill_switch"] is False
    body = c.post("/api/kill-switch", json={"engaged": True}).json()
    assert body["kill_switch"] is True
    # Fresh connection path: re-read through the API
    assert c.get("/api/risk").json()["kill_switch"] is True
    c.post("/api/kill-switch", json={"engaged": False})
    assert c.get("/api/risk").json()["kill_switch"] is False
    conn = connect(db)
    row = conn.execute("select kill_switch from risk_state where id = 1").fetchone()
    assert row["kill_switch"] == 0


def test_put_risk_validates_ranges(client):
    c, _, _ = client
    res = c.put("/api/risk", json={"max_position_pct": 0, "max_open_positions": 3, "daily_loss_limit_pct": 3})
    assert res.status_code == 422


def test_rejects_foreign_host_header(client):
    c, _, _ = client
    res = c.get("/api/status", headers={"Host": "evil.example"})
    assert res.status_code == 400


def test_no_route_places_orders(client):
    c, _, _ = client
    app = c.app
    paths = {getattr(r, "path", "") for r in app.routes}
    assert not any("order" in p for p in paths)


def test_news_endpoint_marks_headlines_unscored(client):
    c, settings, db = client
    conn = connect(db)
    init_schema(conn)
    save_headlines(
        conn,
        [Headline("Example", "news", "BTC pumps", "https://example.com/1", 1_700_000_000_000)],
        1_700_000_000_000,
    )
    body = c.get("/api/news").json()
    assert body["scoring"]["enabled"] is False
    assert body["headlines"][0]["score_status"] == "unscored"
    assert body["headlines"][0]["scores"] == []


def test_backtest_latest_is_null_before_any_run(client):
    c, _, _ = client
    assert c.get("/api/backtests/latest").json() is None


def test_candles_summary_reports_not_ready_without_history(client):
    c, _, _ = client
    body = c.get("/api/candles/summary").json()
    assert body["ready_for_backtest"] is False
    assert body["max_signal_bars"] == 0
    assert body["required_signal_bars"] >= 200
    assert "backfill" in (body["message"] or "").lower()


def test_backtest_run_rejects_missing_candles_with_actionable_detail(client):
    c, _, _ = client
    res = c.post("/api/backtests")
    assert res.status_code == 400
    detail = res.json()["detail"].lower()
    assert "candle" in detail
    assert "backfill" in detail
