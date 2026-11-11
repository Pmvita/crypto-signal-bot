"""Trend-following breakout strategy with a news filter. Pure functions: no I/O, no broker, no clock.

Rules on closed 15m bars (long and short, one position per symbol):
  long   EMA50 > EMA200 and close > highest high of the previous 20 bars, unless news vetoes it
  short  EMA50 < EMA200 and close < lowest low of the previous 20 bars, unless news vetoes it
  stop   long:  favorable extreme (highest close) − 3×ATR14 (ratchets up only)
         short: favorable extreme (lowest close) + 3×ATR14 (ratchets down only)
  exit   long:  close < stop, or EMA50 < EMA200
         short: close > stop, or EMA50 > EMA200
News can block an entry or enlarge it. It never opens or closes a position on its own.
For longs, bearish news vetoes and bullish news boosts; for shorts the polarity is inverted.

These constants are fixed by the design and are not tuned against backtest results.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from csb.indicators import atr, ema, prior_highest, prior_lowest
from csb.models import Action, Candle, NewsState, NewsView, Position, PositionSide


@dataclass(frozen=True)
class StrategyParams:
    ema_fast: int = 50
    ema_slow: int = 200
    breakout_bars: int = 20
    atr_period: int = 14
    stop_atr_mult: float = 3.0
    risk_per_trade: float = 0.01
    news_veto: float = -0.30
    news_boost: float = 0.30
    news_boost_mult: float = 1.25


@dataclass(frozen=True)
class Snapshot:
    """Indicator values at the close of one bar."""

    ts: int
    close: float
    ema_fast: float
    ema_slow: float
    prior_high: float
    prior_low: float
    atr: float


@dataclass(frozen=True)
class Decision:
    action: Action
    reasons: list[str]
    size_multiplier: float
    stop_price: float | None
    highest_close: float | None
    position_side: PositionSide | None = None


def build_snapshots(candles: Sequence[Candle], params: StrategyParams) -> list[Snapshot | None]:
    closes = [c.close for c in candles]
    fast = ema(closes, params.ema_fast)
    slow = ema(closes, params.ema_slow)
    highs = prior_highest([c.high for c in candles], params.breakout_bars)
    lows = prior_lowest([c.low for c in candles], params.breakout_bars)
    ranges = atr(candles, params.atr_period)
    out: list[Snapshot | None] = []
    for i, candle in enumerate(candles):
        f, s, h, lo, a = fast[i], slow[i], highs[i], lows[i], ranges[i]
        if f is None or s is None or h is None or lo is None or a is None:
            out.append(None)
        else:
            out.append(Snapshot(candle.ts, candle.close, f, s, h, lo, a))
    return out


def news_state_for(score: float | None, enabled: bool, params: StrategyParams) -> NewsState:
    if not enabled:
        return NewsState.OFF
    if score is None:
        return NewsState.NO_HEADLINES
    if score <= params.news_veto:
        return NewsState.VETO
    if score >= params.news_boost:
        return NewsState.BOOST
    return NewsState.NEUTRAL


def _news_for_side(news: NewsView, side: PositionSide, params: StrategyParams) -> tuple[NewsState, str]:
    """Map raw news state onto the entry side. Shorts invert boost/veto polarity."""
    state = news.state
    if state is NewsState.OFF:
        return state, "News: scoring is off (no LLM API key), so news had no effect."
    if state is NewsState.NO_HEADLINES:
        return state, "News: no scored headlines for this coin in the last 24h; no effect."
    if state is NewsState.NEUTRAL:
        return state, f"News: score {news.score:+.2f} is inside the neutral band; no effect."

    if side is PositionSide.LONG:
        if state is NewsState.BOOST:
            return state, (
                f"News: score {news.score:+.2f} >= {params.news_boost:+.2f}; "
                f"LONG entry size x{params.news_boost_mult:g}."
            )
        if state is NewsState.VETO:
            return state, f"News: score {news.score:+.2f} <= {params.news_veto:+.2f}; LONG entry blocked."
    else:
        # Invert: bullish (BOOST) vetoes shorts; bearish (VETO) boosts shorts.
        if state is NewsState.VETO:
            return (
                NewsState.BOOST,
                f"News: score {news.score:+.2f} <= {params.news_veto:+.2f}; "
                f"SHORT entry size x{params.news_boost_mult:g}.",
            )
        if state is NewsState.BOOST:
            return (
                NewsState.VETO,
                f"News: score {news.score:+.2f} >= {params.news_boost:+.2f}; SHORT entry blocked.",
            )
    raise AssertionError(f"unhandled news state {state!r} for {side}")


def decide(snap: Snapshot, position: Position | None, news: NewsView, params: StrategyParams) -> Decision:
    trend_up = snap.ema_fast > snap.ema_slow
    trend_down = snap.ema_fast < snap.ema_slow
    trend_text = (
        f"EMA{params.ema_fast} {snap.ema_fast:,.2f} "
        f"{'>' if trend_up else '<' if trend_down else '=='} EMA{params.ema_slow} {snap.ema_slow:,.2f}"
    )

    if position is None:
        long_breakout = snap.close > snap.prior_high
        short_breakdown = snap.close < snap.prior_low

        if trend_up and long_breakout:
            return _enter_long(snap, news, params, trend_text)
        if trend_down and short_breakdown:
            return _enter_short(snap, news, params, trend_text)

        reasons: list[str] = []
        if trend_up:
            reasons.append(f"Waiting for LONG: trend is up ({trend_text}).")
            if not long_breakout:
                reasons.append(
                    f"No LONG yet: close {snap.close:,.2f} is not above the {params.breakout_bars}-bar high "
                    f"{snap.prior_high:,.2f}."
                )
        elif trend_down:
            reasons.append(f"Waiting for SHORT: trend is down ({trend_text}).")
            if not short_breakdown:
                reasons.append(
                    f"No SHORT yet: close {snap.close:,.2f} is not below the {params.breakout_bars}-bar low "
                    f"{snap.prior_low:,.2f}."
                )
        else:
            reasons.append(f"No entry: EMAs are flat ({trend_text}).")
        return Decision(Action.HOLD, reasons, 1.0, None, None, None)

    if position.side is PositionSide.LONG:
        return _manage_long(snap, position, params, trend_text, trend_up)
    return _manage_short(snap, position, params, trend_text, trend_down)


def _enter_long(snap: Snapshot, news: NewsView, params: StrategyParams, trend_text: str) -> Decision:
    effect, sentence = _news_for_side(news, PositionSide.LONG, params)
    price_reasons = [
        f"LONG: trend is up ({trend_text}).",
        f"Breakout: close {snap.close:,.2f} is above the {params.breakout_bars}-bar high {snap.prior_high:,.2f}.",
    ]
    if effect is NewsState.VETO:
        return Decision(Action.HOLD, [*price_reasons, sentence], 1.0, None, None, None)
    multiplier = params.news_boost_mult if effect is NewsState.BOOST else 1.0
    stop = snap.close - params.stop_atr_mult * snap.atr
    return Decision(
        Action.ENTER,
        [
            *price_reasons,
            f"Initial LONG stop {stop:,.2f} = close - {params.stop_atr_mult:g} x ATR{params.atr_period} "
            f"({snap.atr:,.2f}).",
            sentence,
        ],
        multiplier,
        stop,
        snap.close,
        PositionSide.LONG,
    )


def _enter_short(snap: Snapshot, news: NewsView, params: StrategyParams, trend_text: str) -> Decision:
    effect, sentence = _news_for_side(news, PositionSide.SHORT, params)
    price_reasons = [
        f"SHORT: trend is down ({trend_text}).",
        f"Breakdown: close {snap.close:,.2f} is below the {params.breakout_bars}-bar low {snap.prior_low:,.2f}.",
    ]
    if effect is NewsState.VETO:
        return Decision(Action.HOLD, [*price_reasons, sentence], 1.0, None, None, None)
    multiplier = params.news_boost_mult if effect is NewsState.BOOST else 1.0
    stop = snap.close + params.stop_atr_mult * snap.atr
    return Decision(
        Action.ENTER,
        [
            *price_reasons,
            f"Initial SHORT stop {stop:,.2f} = close + {params.stop_atr_mult:g} x ATR{params.atr_period} "
            f"({snap.atr:,.2f}).",
            sentence,
        ],
        multiplier,
        stop,
        snap.close,
        PositionSide.SHORT,
    )


def _manage_long(
    snap: Snapshot, position: Position, params: StrategyParams, trend_text: str, trend_up: bool
) -> Decision:
    highest = max(position.highest_close, snap.close)
    stop = max(position.stop_price, highest - params.stop_atr_mult * snap.atr)
    if snap.close < stop:
        return Decision(
            Action.EXIT,
            [f"Exit LONG: close {snap.close:,.2f} is below the trailing stop {stop:,.2f}."],
            1.0,
            stop,
            highest,
            PositionSide.LONG,
        )
    if not trend_up:
        return Decision(
            Action.EXIT,
            [f"Exit LONG: trend is no longer up ({trend_text})."],
            1.0,
            stop,
            highest,
            PositionSide.LONG,
        )
    return Decision(
        Action.HOLD,
        [f"Holding LONG: trend is up ({trend_text}) and close {snap.close:,.2f} is above the stop {stop:,.2f}."],
        1.0,
        stop,
        highest,
        PositionSide.LONG,
    )


def _manage_short(
    snap: Snapshot, position: Position, params: StrategyParams, trend_text: str, trend_down: bool
) -> Decision:
    lowest = min(position.highest_close, snap.close)
    stop = min(position.stop_price, lowest + params.stop_atr_mult * snap.atr)
    if snap.close > stop:
        return Decision(
            Action.EXIT,
            [f"Exit SHORT: close {snap.close:,.2f} is above the trailing stop {stop:,.2f}."],
            1.0,
            stop,
            lowest,
            PositionSide.SHORT,
        )
    if not trend_down:
        return Decision(
            Action.EXIT,
            [f"Exit SHORT: trend is no longer down ({trend_text})."],
            1.0,
            stop,
            lowest,
            PositionSide.SHORT,
        )
    return Decision(
        Action.HOLD,
        [f"Holding SHORT: trend is down ({trend_text}) and close {snap.close:,.2f} is below the stop {stop:,.2f}."],
        1.0,
        stop,
        lowest,
        PositionSide.SHORT,
    )


def position_size(equity: float, atr_value: float, size_multiplier: float, params: StrategyParams) -> float:
    """Quantity that loses `risk_per_trade` of equity if price moves from entry to the initial stop."""
    stop_distance = params.stop_atr_mult * atr_value
    if stop_distance <= 0 or equity <= 0:
        return 0.0
    return equity * params.risk_per_trade * size_multiplier / stop_distance
