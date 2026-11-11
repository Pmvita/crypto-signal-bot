"""OrderRouter: the only path from a trading decision to a broker. Risk is checked first, every time."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

from csb.broker import Broker, expected_fill_price
from csb.models import Fill, OrderRequest, PositionSide, Quote, Side
from csb.portfolio import Portfolio
from csb.risk import RiskManager


@dataclass(frozen=True)
class OrderResult:
    status: Literal["filled", "rejected"]
    requested_qty: float
    qty: float
    ref_price: float
    fill: Fill | None = None
    reason: str | None = None
    notes: list[str] = field(default_factory=list)
    realized_pnl: float | None = None


Recorder = Callable[[OrderRequest, OrderResult, int], None]


class OrderRouter:
    def __init__(
        self,
        risk: RiskManager,
        broker: Broker,
        portfolio: Portfolio,
        fee_bps: float,
        slippage_bps: float,
        recorder: Recorder | None = None,
    ) -> None:
        self._risk = risk
        self._broker = broker
        self._portfolio = portfolio
        self._fee_rate = fee_bps / 10_000
        self._slippage_bps = slippage_bps
        self._recorder = recorder

    def submit(
        self,
        request: OrderRequest,
        quote: Quote,
        equity: float,
        ts_ms: int,
        stop_price: float | None = None,
        highest_close: float | None = None,
        position_side: PositionSide | None = None,
    ) -> OrderResult:
        position = self._portfolio.positions.get(request.symbol)
        held_side = position.side if position is not None else None
        is_exit = (
            position is not None
            and (
                (request.side is Side.SELL and held_side is PositionSide.LONG)
                or (request.side is Side.BUY and held_side is PositionSide.SHORT)
            )
        )
        # Exits always close the whole position.
        requested = position.qty if is_exit and position is not None else request.qty
        ref_price = expected_fill_price(request.side, quote, self._slippage_bps)
        entry_side = position_side
        if is_exit:
            entry_side = held_side
        elif entry_side is None:
            entry_side = PositionSide.LONG if request.side is Side.BUY else PositionSide.SHORT

        decision = self._risk.check_order(
            side=request.side,
            qty=requested,
            price=ref_price,
            equity=equity,
            cash=self._portfolio.cash,
            open_positions=len(self._portfolio.positions),
            has_position=position is not None,
            fee_rate=self._fee_rate,
            position_side=held_side if is_exit else (None if position is not None else entry_side),
        )
        if decision.approved:
            fill = self._broker.market_order(request.symbol, request.side, decision.qty, quote, ts_ms)
            pnl = self._portfolio.apply_fill(
                fill,
                stop_price=stop_price,
                highest_close=highest_close,
                position_side=None if is_exit else entry_side,
            )
            result = OrderResult("filled", requested, fill.qty, ref_price, fill, None, decision.notes, pnl)
        else:
            result = OrderResult("rejected", requested, 0.0, ref_price, None, decision.reason, decision.notes)

        if self._recorder is not None:
            self._recorder(request, result, ts_ms)
        return result
