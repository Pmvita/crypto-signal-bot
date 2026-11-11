"""Plain data types shared by every module."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Side(StrEnum):
    BUY = "buy"
    SELL = "sell"


class Action(StrEnum):
    ENTER = "enter"
    EXIT = "exit"
    HOLD = "hold"


class NewsState(StrEnum):
    OFF = "off"  # scoring disabled: no LLM key configured
    NO_HEADLINES = "no_headlines"  # scoring on, nothing scored for this coin in the lookback
    NEUTRAL = "neutral"
    BOOST = "boost"
    VETO = "veto"


@dataclass(frozen=True)
class Candle:
    ts: int  # open time, Unix ms UTC
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class Quote:
    symbol: str
    bid: float | None
    ask: float | None
    last: float
    ts: int


@dataclass
class Position:
    symbol: str
    qty: float
    entry_price: float
    entry_ts: int
    stop_price: float
    highest_close: float
    entry_fee: float = 0.0


@dataclass(frozen=True)
class Fill:
    symbol: str
    side: Side
    qty: float
    price: float
    fee: float
    ts: int
    broker: str


@dataclass(frozen=True)
class OrderRequest:
    symbol: str
    side: Side
    qty: float
    signal_id: int | None = None


@dataclass(frozen=True)
class Headline:
    source: str
    kind: str  # "news" or "exchange"
    title: str
    url: str
    published_at: int


@dataclass(frozen=True)
class HeadlineScore:
    coin: str
    direction: int  # -1 bearish, 0 neutral, 1 bullish
    strength: float  # 0..1
    confidence: float  # 0..1
    rationale: str


@dataclass(frozen=True)
class ScoredHeadline:
    id: int
    source: str
    title: str
    url: str
    published_at: int
    score: HeadlineScore


@dataclass(frozen=True)
class NewsView:
    """What the strategy is told about news for one coin."""

    state: NewsState
    score: float | None
    headlines: list[ScoredHeadline]
