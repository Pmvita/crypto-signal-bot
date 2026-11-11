"""Candle storage and local aggregation of 1h candles into the signal timeframe."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Sequence

from csb.models import Candle

HOUR_MS = 3_600_000
BASE_TIMEFRAME = "1h"
SIGNAL_HOURS = 4


def upsert_candles(
    conn: sqlite3.Connection, exchange: str, symbol: str, timeframe: str, candles: Iterable[Candle]
) -> int:
    rows = [(exchange, symbol, timeframe, c.ts, c.open, c.high, c.low, c.close, c.volume) for c in candles]
    conn.executemany(
        """
        insert into candles (exchange, symbol, timeframe, ts, open, high, low, close, volume)
        values (?, ?, ?, ?, ?, ?, ?, ?, ?)
        on conflict (exchange, symbol, timeframe, ts) do update set
            open = excluded.open, high = excluded.high, low = excluded.low,
            close = excluded.close, volume = excluded.volume
        """,
        rows,
    )
    conn.commit()
    return len(rows)


def load_candles(
    conn: sqlite3.Connection, exchange: str, symbol: str, timeframe: str, since_ms: int | None = None
) -> list[Candle]:
    rows = conn.execute(
        """
        select ts, open, high, low, close, volume from candles
        where exchange = ? and symbol = ? and timeframe = ? and ts >= ?
        order by ts
        """,
        (exchange, symbol, timeframe, since_ms if since_ms is not None else 0),
    ).fetchall()
    return [Candle(r["ts"], r["open"], r["high"], r["low"], r["close"], r["volume"]) for r in rows]


def latest_ts(conn: sqlite3.Connection, exchange: str, symbol: str, timeframe: str) -> int | None:
    row = conn.execute(
        "select max(ts) as ts from candles where exchange = ? and symbol = ? and timeframe = ?",
        (exchange, symbol, timeframe),
    ).fetchone()
    return row["ts"]


def aggregate(candles: Sequence[Candle], hours: int, now_ms: int) -> list[Candle]:
    """Combine 1h candles into UTC-aligned `hours`-long bars. Buckets that have not ended yet are dropped."""
    bucket_ms = hours * HOUR_MS
    out: list[Candle] = []
    current_start: int | None = None
    o = h = low = c = v = 0.0
    for candle in candles:
        start = candle.ts - candle.ts % bucket_ms
        if start != current_start:
            if current_start is not None and current_start + bucket_ms <= now_ms:
                out.append(Candle(current_start, o, h, low, c, v))
            current_start, o, h, low, c, v = start, candle.open, candle.high, candle.low, candle.close, 0.0
        h = max(h, candle.high)
        low = min(low, candle.low)
        c = candle.close
        v += candle.volume
    if current_start is not None and current_start + bucket_ms <= now_ms:
        out.append(Candle(current_start, o, h, low, c, v))
    return out
