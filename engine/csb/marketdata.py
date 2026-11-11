"""Exchange-agnostic market data through ccxt. Public endpoints only: no API key is ever set."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from typing import Any

import ccxt

from csb.candles import BAR_MS, BASE_TIMEFRAME, HOUR_MS, latest_ts, upsert_candles
from csb.db import now_ms
from csb.models import Candle, Quote

PAGE_LIMIT = 300
DAY_MS = 24 * HOUR_MS
# EMA200 on 15m needs ~2.1 days; fetch ~90 days so first start / backtest warm-up has headroom.
WARMUP_DAYS = 90


def create_exchange(exchange_id: str) -> Any:
    if exchange_id not in ccxt.exchanges:
        raise ValueError(f"Unknown ccxt exchange id: {exchange_id!r}")
    return getattr(ccxt, exchange_id)({"enableRateLimit": True, "timeout": 20_000})


class MarketData:
    def __init__(
        self, exchange: Any, exchange_id: str, conn: sqlite3.Connection, clock: Callable[[], int] = now_ms
    ) -> None:
        self._exchange = exchange
        self.exchange_id = exchange_id
        self._conn = conn
        self._clock = clock

    def backfill(self, symbol: str, days: int, progress: Callable[[int], None] | None = None) -> int:
        """Fetch 15m candles from `days` ago to now. Returns the number of closed candles stored."""
        return self._sync(symbol, self._clock() - days * DAY_MS, progress)

    def update(self, symbol: str) -> int:
        """Fetch candles newer than the newest stored one. With nothing stored, fetch the warm-up window."""
        newest = latest_ts(self._conn, self.exchange_id, symbol, BASE_TIMEFRAME)
        if newest is None:
            return self.backfill(symbol, WARMUP_DAYS)
        return self._sync(symbol, newest + BAR_MS, None)

    def quote(self, symbol: str) -> Quote:
        ticker = self._exchange.fetch_ticker(symbol)
        last = ticker.get("last") or ticker.get("close")
        if not last:
            raise ValueError(f"{self.exchange_id} returned no last price for {symbol}")
        return Quote(
            symbol=symbol,
            bid=ticker.get("bid") or None,
            ask=ticker.get("ask") or None,
            last=float(last),
            ts=int(ticker.get("timestamp") or self._clock()),
        )

    def _sync(self, symbol: str, since: int, progress: Callable[[int], None] | None) -> int:
        now = self._clock()
        since -= since % BAR_MS
        newest_seen: int | None = None
        stored = 0
        while since < now:
            rows = self._exchange.fetch_ohlcv(symbol, BASE_TIMEFRAME, since=since, limit=PAGE_LIMIT)
            if not rows:
                since += PAGE_LIMIT * BAR_MS  # nothing in this window (not listed yet, or a gap): move on
                continue
            last = int(rows[-1][0])
            if newest_seen is not None and last <= newest_seen:
                break  # no progress: the exchange is ignoring `since` (Kraken serves only its latest 720)
            closed = [
                Candle(int(r[0]), float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5] or 0.0))
                for r in rows
                if int(r[0]) + BAR_MS <= now and (newest_seen is None or int(r[0]) > newest_seen)
            ]
            stored += upsert_candles(self._conn, self.exchange_id, symbol, BASE_TIMEFRAME, closed)
            if progress is not None:
                progress(stored)
            newest_seen = last
            since = last + BAR_MS
        return stored
