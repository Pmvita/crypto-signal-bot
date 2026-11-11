"""Trend-following breakout strategy with a news filter. Pure functions: no I/O, no broker, no clock.

Rules on closed 4h bars (long only, one position per symbol):
  entry  EMA50 > EMA200 and close > highest high of the previous 20 bars, unless news vetoes it
  stop   highest close since entry minus 3 x ATR14; it only moves up
  exit   close < stop, or EMA50 < EMA200
News can block an entry or enlarge it. It never opens or closes a position on its own.

These constants are fixed by the design spec and are not tuned against backtest results.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from csb.indicators import atr, ema, prior_highest
from csb.models import Action, Candle, NewsState, NewsView, Position


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
    min_notional: float = 10.0


@dataclass(frozen=True)
class Snapshot:
    """Indicator values at the close of one bar."""

    ts: int
    close: float
    ema_fast: float
    ema_slow: float
    prior_high: float
    atr: float


@dataclass(frozen=True)
class Decision:
    action: Action
    reasons: list[str]
    size_multiplier: float
    stop_price: float | None
    highest_close: float | None


def build_snapshots(candles: Sequence[Candle], params: StrategyParams) -> list[Snapshot | None]:
    closes = [c.close for c in candles]
    fast = ema(closes, params.ema_fast)
    slow = ema(closes, params.ema_slow)
    highs = prior_highest([c.high for c in candles], params.breakout_bars)
    ranges = atr(candles, params.atr_period)
    out: list[Snapshot | None] = []
    for i, candle in enumerate(candles):
        f, s, h, a = fast[i], slow[i], highs[i], ranges[i]
        if f is None or s is None or h is None or a is None:
            out.append(None)
        else:
            out.append(Snapshot(candle.ts, candle.close, f, s, h, a))
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


def _news_sentence(news: NewsView, params: StrategyParams) -> str:
    state = news.state
    if state is NewsState.OFF:
        return "News: scoring is off (no LLM API key), so news had no effect."
    if state is NewsState.NO_HEADLINES:
        return "News: no scored headlines for this coin in the last 24h; no effect."
    if state is NewsState.NEUTRAL:
        return f"News: score {news.score:+.2f} is inside the neutral band; no effect."
    if state is NewsState.BOOST:
        return f"News: score {news.score:+.2f} >= {params.news_boost:+.2f}; entry size x{params.news_boost_mult:g}."
    if state is NewsState.VETO:
        return f"News: score {news.score:+.2f} <= {params.news_veto:+.2f}; entry blocked."
    raise AssertionError(f"unhandled news state {state!r}")


def decide(snap: Snapshot, position: Position | None, news: NewsView, params: StrategyParams) -> Decision:
    trend_up = snap.ema_fast > snap.ema_slow
    trend_text = (
        f"EMA{params.ema_fast} {snap.ema_fast:,.2f} "
        f"{'>' if trend_up else '<='} EMA{params.ema_slow} {snap.ema_slow:,.2f}"
    )

    if position is None:
        breakout = snap.close > snap.prior_high
        reasons: list[str] = []
        if not trend_up:
            reasons.append(f"No entry: trend is not up ({trend_text}).")
        if not breakout:
            reasons.append(
                f"No entry: close {snap.close:,.2f} is not above the {params.breakout_bars}-bar high "
                f"{snap.prior_high:,.2f}."
            )
        if reasons:
            return Decision(Action.HOLD, reasons, 1.0, None, None)

        price_reasons = [
            f"Trend is up ({trend_text}).",
            f"Breakout: close {snap.close:,.2f} is above the {params.breakout_bars}-bar high {snap.prior_high:,.2f}.",
        ]
        if news.state is NewsState.VETO:
            return Decision(Action.HOLD, [*price_reasons, _news_sentence(news, params)], 1.0, None, None)

        multiplier = params.news_boost_mult if news.state is NewsState.BOOST else 1.0
        stop = snap.close - params.stop_atr_mult * snap.atr
        return Decision(
            Action.ENTER,
            [
                *price_reasons,
                f"Initial stop {stop:,.2f} = close - {params.stop_atr_mult:g} x ATR{params.atr_period} "
                f"({snap.atr:,.2f}).",
                _news_sentence(news, params),
            ],
            multiplier,
            stop,
            snap.close,
        )

    highest = max(position.highest_close, snap.close)
    stop = max(position.stop_price, highest - params.stop_atr_mult * snap.atr)
    if snap.close < stop:
        return Decision(
            Action.EXIT, [f"Exit: close {snap.close:,.2f} is below the trailing stop {stop:,.2f}."], 1.0, stop, highest
        )
    if not trend_up:
        return Decision(Action.EXIT, [f"Exit: trend is no longer up ({trend_text})."], 1.0, stop, highest)
    return Decision(
        Action.HOLD,
        [f"Holding: trend is up ({trend_text}) and close {snap.close:,.2f} is above the stop {stop:,.2f}."],
        1.0,
        stop,
        highest,
    )


def position_size(equity: float, atr_value: float, size_multiplier: float, params: StrategyParams) -> float:
    """Quantity that loses `risk_per_trade` of equity if price falls from entry to the initial stop."""
    stop_distance = params.stop_atr_mult * atr_value
    if stop_distance <= 0 or equity <= 0:
        return 0.0
    return equity * params.risk_per_trade * size_multiplier / stop_distance
