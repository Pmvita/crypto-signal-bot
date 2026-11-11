from csb.candles import HOUR_MS, upsert_candles
from csb.config import load_settings
from csb.db import connect, init_schema
from csb.jobs import run_stored_backtest
from csb.models import Candle

T0 = 1_700_000_000_000


def _hourly(n: int = 1400) -> list[Candle]:
    """Enough 1h bars (~1400 ≈ 58 days) for EMA200 warm-up plus tradeable 4h headroom."""
    out = []
    price = 100.0
    for i in range(n):
        price += 0.02
        out.append(Candle(T0 + i * HOUR_MS, price - 0.1, price + 0.2, price - 0.2, price, 1.0))
    return out


def test_run_stored_backtest_persists_a_run_from_stored_candles(tmp_path):
    db = tmp_path / "t.sqlite3"
    conn = connect(db)
    init_schema(conn)
    settings = load_settings(
        {
            "CSB_DB_PATH": str(db),
            "CSB_EXCHANGE": "fake",
            "CSB_SYMBOLS": "BTC/USD",
            "CSB_STARTING_CASH": "10000",
        }
    )
    upsert_candles(conn, "fake", "BTC/USD", "1h", _hourly())
    result = run_stored_backtest(settings, conn)
    assert result["news_included"] is False
    row = conn.execute("select count(*) as n from backtest_runs").fetchone()
    assert row["n"] == 1
    assert "total_return_pct" in result
    assert result["id"] == 1
