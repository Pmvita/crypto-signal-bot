"""One-shot jobs shared by the CLI and the API (backtest on stored candles)."""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

from csb.backtest import run_backtest
from csb.candles import BASE_TIMEFRAME, SIGNAL_HOURS, aggregate, load_candles
from csb.config import Settings
from csb.db import init_schema, now_ms
from csb.marketdata import MarketData, create_exchange
from csb.risk import SqliteRiskStore
from csb.strategy import StrategyParams

# EMA200 needs 200 closed 4h bars before the first signal; keep headroom so a run can trade.
MIN_BARS_AFTER_WARMUP = 100


def min_backtest_bars(params: StrategyParams | None = None) -> int:
    p = params or StrategyParams()
    return p.ema_slow + MIN_BARS_AFTER_WARMUP


def candle_history_summary(settings: Settings, conn) -> dict[str, Any]:
    """Per-symbol 1h counts and aggregated 4h bar counts used by the backtest readiness check."""
    init_schema(conn)
    params = StrategyParams()
    required = min_backtest_bars(params)
    now = now_ms()
    symbols: list[dict[str, Any]] = []
    max_bars = 0
    for symbol in settings.symbols:
        hourly = load_candles(conn, settings.exchange, symbol, BASE_TIMEFRAME)
        bars = aggregate(hourly, SIGNAL_HOURS, now)
        max_bars = max(max_bars, len(bars))
        symbols.append(
            {
                "symbol": symbol,
                "hourly_candles": len(hourly),
                "signal_bars": len(bars),
                "oldest_ts": hourly[0].ts if hourly else None,
                "newest_ts": hourly[-1].ts if hourly else None,
            }
        )
    ready = max_bars >= required
    return {
        "exchange": settings.exchange,
        "symbols": symbols,
        "max_signal_bars": max_bars,
        "required_signal_bars": required,
        "ready_for_backtest": ready,
        "backfill_days_default": settings.backfill_days,
        "message": None
        if ready
        else (
            f"Not enough candle history for a meaningful backtest "
            f"({max_bars} 4h bars stored; need at least {required}). "
            f"Download history (backfill), then run again."
        ),
    }


def run_backfill(settings: Settings, conn, days: int | None = None) -> dict[str, Any]:
    """Download historical 1h candles into the DB. Returns stored counts and a fresh history summary."""
    init_schema(conn)
    target_days = days if days is not None else settings.backfill_days
    if target_days < 1:
        raise RuntimeError("Backfill days must be at least 1.")
    market = MarketData(create_exchange(settings.exchange), settings.exchange, conn)
    stored: dict[str, int] = {}
    for symbol in settings.symbols:
        stored[symbol] = market.backfill(symbol, target_days)
    summary = candle_history_summary(settings, conn)
    return {"days": target_days, "stored": stored, "summary": summary}


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
        raise RuntimeError(
            "No candles stored. Download history (backfill) from the Backtest page or Settings, then run again."
        )
    max_bars = max(len(bars) for bars in bars_by_symbol.values())
    required = min_backtest_bars(params)
    if max_bars < required:
        raise RuntimeError(
            f"Not enough candle history for a meaningful backtest "
            f"({max_bars} 4h bars; need at least {required}). "
            f"Download history (backfill), then run again."
        )

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
