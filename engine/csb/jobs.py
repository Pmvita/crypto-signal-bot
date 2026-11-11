"""One-shot jobs shared by the CLI and the API (backtest on stored candles)."""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

from csb.backtest import run_backtest
from csb.candles import BASE_TIMEFRAME, SIGNAL_HOURS, aggregate, load_candles
from csb.config import Settings
from csb.db import init_schema, now_ms
from csb.risk import SqliteRiskStore
from csb.strategy import StrategyParams


def run_stored_backtest(settings: Settings, conn) -> dict[str, Any]:
    """Aggregate stored 1h candles to 4h bars, run the price-only backtest, persist the run."""
    init_schema(conn)
    params = StrategyParams()
    limits = SqliteRiskStore(conn).load_limits()
    now = now_ms()
    bars_by_symbol: dict[str, list] = {}
    for symbol in settings.symbols:
        hourly = load_candles(conn, settings.exchange, symbol, BASE_TIMEFRAME)
        bars = aggregate(hourly, SIGNAL_HOURS, now)
        if bars:
            bars_by_symbol[symbol] = bars
    if not bars_by_symbol:
        raise RuntimeError("No candles stored. Run `python -m csb backfill` first.")

    result = run_backtest(
        bars_by_symbol,
        params,
        limits,
        settings.starting_cash,
        settings.fee_bps,
        settings.slippage_bps,
    )
    payload = result.to_dict()
    cursor = conn.execute(
        "insert into backtest_runs (created_at, params, result) values (?, ?, ?)",
        (
            now,
            json.dumps(
                {
                    "params": asdict(params),
                    "limits": asdict(limits),
                    "starting_cash": settings.starting_cash,
                    "fee_bps": settings.fee_bps,
                    "slippage_bps": settings.slippage_bps,
                    "exchange": settings.exchange,
                    "symbols": list(settings.symbols),
                    "news_included": False,
                }
            ),
            json.dumps(payload),
        ),
    )
    conn.commit()
    return {"id": cursor.lastrowid, "created_at": now, "news_included": False, **payload}
