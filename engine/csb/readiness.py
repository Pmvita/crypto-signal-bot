"""Live per-symbol strategy readiness for the Trading desk (paper watch board)."""

from __future__ import annotations

import sqlite3
from typing import Any

from csb.candles import BASE_TIMEFRAME, SIGNAL_HOURS, aggregate, load_candles
from csb.config import Settings
from csb.db import get_meta, now_ms
from csb.news_store import news_view
from csb.portfolio import load_portfolio
from csb.strategy import StrategyParams, build_snapshots, decide


def _pct(numer: float, denom: float) -> float | None:
    if denom == 0:
        return None
    return (numer / denom) * 100.0


def _sparkline_closes(bars: list[Any], limit: int = 48) -> list[float]:
    closes = [b.close for b in bars if b.close is not None]
    if len(closes) <= limit:
        return closes
    return closes[-limit:]


def symbol_readiness(
    conn: sqlite3.Connection,
    settings: Settings,
    symbol: str,
    *,
    params: StrategyParams,
    quotes: dict[str, dict[str, Any]],
    position: Any | None,
    now: int,
    scoring_enabled: bool,
) -> dict[str, Any]:
    quote = quotes.get(symbol)
    last = float(quote["last"]) if quote and quote.get("last") is not None else None
    quote_ts = int(quote["ts"]) if quote and quote.get("ts") is not None else None

    hourly = load_candles(conn, settings.exchange, symbol, BASE_TIMEFRAME)
    bars = aggregate(hourly, SIGNAL_HOURS, now)
    snaps = build_snapshots(bars, params)
    snap = next((s for s in reversed(snaps) if s is not None), None)
    news = news_view(conn, symbol.split("/")[0], now, scoring_enabled, params)

    sparkline = _sparkline_closes(bars)
    last_eval_raw = get_meta(conn, f"last_eval:{symbol}")
    last_eval_bar_ts = int(last_eval_raw) if last_eval_raw and last_eval_raw.isdigit() else None

    base: dict[str, Any] = {
        "symbol": symbol,
        "last": last,
        "quote_ts": quote_ts,
        "bar_close": None,
        "bar_ts": None,
        "ema_fast": None,
        "ema_slow": None,
        "ema_fast_period": params.ema_fast,
        "ema_slow_period": params.ema_slow,
        "trend_up": None,
        "ema_gap_pct": None,
        "prior_high": None,
        "breakout_bars": params.breakout_bars,
        "breakout_ready": None,
        "distance_to_breakout": None,
        "distance_to_breakout_pct": None,
        "atr": None,
        "atr_period": params.atr_period,
        "stop_atr_mult": params.stop_atr_mult,
        "trail_stop": None,
        "in_position": position is not None,
        "position_stop": position.stop_price if position is not None else None,
        "action": "hold",
        "state": "warming_up",
        "conditions": {
            "trend_up": False,
            "breakout": False,
            "news_ok": news.state.value != "veto",
        },
        "news_state": news.state.value,
        "news_score": news.score,
        "sparkline": sparkline,
        "breakout_level": None,
        "last_eval_bar_ts": last_eval_bar_ts,
        "ready_for_enter": False,
        "bars_ready": len(bars),
        "bars_needed": params.ema_slow + 1,
    }

    if snap is None:
        return base

    trend_up = snap.ema_fast > snap.ema_slow
    breakout = snap.close > snap.prior_high
    ema_gap_pct = _pct(snap.ema_fast - snap.ema_slow, snap.ema_slow)
    distance = snap.prior_high - snap.close
    distance_pct = _pct(distance, snap.close)

    decision = decide(snap, position, news, params)
    trail_stop = decision.stop_price

    if position is not None:
        state = "in_position"
    elif decision.action.value == "enter":
        state = "ready_to_enter"
    else:
        state = "waiting_for_enter"

    ready = (
        position is None
        and trend_up
        and breakout
        and news.state.value != "veto"
    )

    base.update(
        {
            "bar_close": snap.close,
            "bar_ts": snap.ts,
            "ema_fast": snap.ema_fast,
            "ema_slow": snap.ema_slow,
            "trend_up": trend_up,
            "ema_gap_pct": ema_gap_pct,
            "prior_high": snap.prior_high,
            "breakout_ready": breakout,
            "distance_to_breakout": distance,
            "distance_to_breakout_pct": distance_pct,
            "atr": snap.atr,
            "trail_stop": trail_stop,
            "action": decision.action.value,
            "state": state,
            "conditions": {
                "trend_up": trend_up,
                "breakout": breakout,
                "news_ok": news.state.value != "veto",
            },
            "breakout_level": snap.prior_high,
            "ready_for_enter": ready,
        }
    )
    return base


def trading_readiness(
    conn: sqlite3.Connection,
    settings: Settings,
    *,
    trading_enabled: bool,
    scoring_enabled: bool,
    heartbeat: dict[str, Any] | None,
    clock: Any = now_ms,
) -> dict[str, Any]:
    """Structured live metrics for the Trading active-watch board."""
    now = clock()
    params = StrategyParams()
    pf = load_portfolio(conn, settings.starting_cash)
    quotes = {
        r["symbol"]: {"bid": r["bid"], "ask": r["ask"], "last": r["last"], "ts": r["ts"]}
        for r in conn.execute("select * from quotes").fetchall()
    }

    symbols = [
        symbol_readiness(
            conn,
            settings,
            symbol,
            params=params,
            quotes=quotes,
            position=pf.positions.get(symbol),
            now=now,
            scoring_enabled=scoring_enabled,
        )
        for symbol in settings.symbols
    ]

    cycle_seconds = settings.cycle_seconds
    last_finished = heartbeat.get("finished_at") if heartbeat else None
    next_cycle_at = None
    if last_finished is not None:
        next_cycle_at = int(last_finished) + cycle_seconds * 1000
    elif trading_enabled:
        next_cycle_at = now + cycle_seconds * 1000

    return {
        "mode": "paper",
        "trading_enabled": trading_enabled,
        "exchange": settings.exchange,
        "cycle_seconds": cycle_seconds,
        "server_time": now,
        "heartbeat": heartbeat,
        "last_cycle_at": last_finished,
        "next_cycle_at": next_cycle_at,
        "params": {
            "ema_fast": params.ema_fast,
            "ema_slow": params.ema_slow,
            "breakout_bars": params.breakout_bars,
            "atr_period": params.atr_period,
            "stop_atr_mult": params.stop_atr_mult,
            "signal_hours": SIGNAL_HOURS,
        },
        "symbols": symbols,
    }
