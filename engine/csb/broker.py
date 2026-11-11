"""Broker interface and the paper broker.

Phase 1 ships PaperBroker only. It never contacts an exchange. A phase 2 live broker implements the same
`market_order` method by placing a real order and returning the exchange's fill; the strategy, risk manager
and order router do not change.
"""

from __future__ import annotations

from typing import Protocol

from csb.models import Fill, Quote, Side


class Broker(Protocol):
    name: str

    def market_order(self, symbol: str, side: Side, qty: float, quote: Quote, ts_ms: int) -> Fill: ...


def expected_fill_price(side: Side, quote: Quote, slippage_bps: float) -> float:
    """Ask for buys and bid for sells (last if missing), moved against the trader by the slippage."""
    slip = slippage_bps / 10_000
    if side is Side.BUY:
        return (quote.ask or quote.last) * (1 + slip)
    return (quote.bid or quote.last) * (1 - slip)


class PaperBroker:
    """Simulates an immediate full fill at the quoted price with slippage and a proportional fee."""

    name = "paper"

    def __init__(self, fee_bps: float, slippage_bps: float) -> None:
        self.fee_bps = fee_bps
        self.slippage_bps = slippage_bps

    def market_order(self, symbol: str, side: Side, qty: float, quote: Quote, ts_ms: int) -> Fill:
        if qty <= 0:
            raise ValueError("quantity must be positive")
        price = expected_fill_price(side, quote, self.slippage_bps)
        fee = qty * price * self.fee_bps / 10_000
        return Fill(symbol=symbol, side=side, qty=qty, price=price, fee=fee, ts=ts_ms, broker=self.name)
