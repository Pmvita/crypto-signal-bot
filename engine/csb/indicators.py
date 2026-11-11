"""Technical indicators as pure functions. Outputs align index-for-index with inputs; None means warming up."""

from __future__ import annotations

from collections.abc import Sequence

from csb.models import Candle


def ema(values: Sequence[float], period: int) -> list[float | None]:
    """Exponential moving average seeded with the simple average of the first `period` values."""
    out: list[float | None] = [None] * len(values)
    if period <= 0 or len(values) < period:
        return out
    alpha = 2.0 / (period + 1)
    current = sum(values[:period]) / period
    out[period - 1] = current
    for i in range(period, len(values)):
        current = current + alpha * (values[i] - current)
        out[i] = current
    return out


def prior_highest(highs: Sequence[float], period: int) -> list[float | None]:
    """Highest of the previous `period` values, excluding the current one."""
    out: list[float | None] = [None] * len(highs)
    for i in range(period, len(highs)):
        out[i] = max(highs[i - period : i])
    return out


def prior_lowest(lows: Sequence[float], period: int) -> list[float | None]:
    """Lowest of the previous `period` values, excluding the current one."""
    out: list[float | None] = [None] * len(lows)
    for i in range(period, len(lows)):
        out[i] = min(lows[i - period : i])
    return out


def atr(candles: Sequence[Candle], period: int) -> list[float | None]:
    """Wilder average true range. The first value appears at index `period`."""
    out: list[float | None] = [None] * len(candles)
    if period <= 0 or len(candles) <= period:
        return out
    true_ranges = []
    for i in range(1, len(candles)):
        c, prev_close = candles[i], candles[i - 1].close
        true_ranges.append(max(c.high - c.low, abs(c.high - prev_close), abs(c.low - prev_close)))
    current = sum(true_ranges[:period]) / period
    out[period] = current
    for i in range(period + 1, len(candles)):
        current = (current * (period - 1) + true_ranges[i - 1]) / period
        out[i] = current
    return out
