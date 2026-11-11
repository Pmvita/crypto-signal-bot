"""Historical replay of the price rules.

Uses the same decision, sizing, risk and ledger code as paper trading. Decisions are made on a closed bar
and filled at the next bar's open with slippage and fees, so nothing uses information from the future.
News is not part of the replay: historical headlines are not available, so this validates price rules only.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from csb.broker import PaperBroker
from csb.candles import BAR_MS
from csb.execution import OrderRouter
from csb.models import Action, Candle, NewsState, NewsView, OrderRequest, PositionSide, Quote, Side
from csb.portfolio import Portfolio
from csb.risk import MemoryRiskStore, RiskLimits, RiskManager
from csb.strategy import StrategyParams, build_snapshots, decide, position_size

NEWS_OFF = NewsView(NewsState.OFF, None, [])
MAX_CURVE_POINTS = 600


@dataclass
class _Pending:
    symbol: str
    side: Side
    qty: float
    stop_price: float | None
    highest_close: float | None
    reason: str
    position_side: PositionSide | None


@dataclass
class BacktestResult:
    symbols: list[str]
    data_start: int | None
    period_start: int | None
    period_end: int | None
    bars: int
    starting_cash: float
    final_equity: float
    total_return_pct: float
    max_drawdown_pct: float
    trades: int
    wins: int
    win_rate_pct: float | None
    profit_factor: float | None
    total_fees: float
    buy_hold_return_pct: float | None
    rejected_orders: int
    fee_bps: float
    slippage_bps: float
    trade_list: list[dict] = field(default_factory=list)
    open_positions: list[dict] = field(default_factory=list)
    equity_curve: list[tuple[int, float]] = field(default_factory=list)
    news_included: bool = False

    def to_dict(self) -> dict:
        curve = self.equity_curve
        step = max(1, -(-len(curve) // MAX_CURVE_POINTS))
        sampled = curve[::step]
        if curve and sampled[-1] != curve[-1]:
            sampled[-1] = curve[-1]
        return {
            "symbols": self.symbols,
            "data_start": self.data_start,
            "period_start": self.period_start,
            "period_end": self.period_end,
            "bars": self.bars,
            "starting_cash": self.starting_cash,
            "final_equity": self.final_equity,
            "total_return_pct": self.total_return_pct,
            "max_drawdown_pct": self.max_drawdown_pct,
            "trades": self.trades,
            "wins": self.wins,
            "win_rate_pct": self.win_rate_pct,
            "profit_factor": self.profit_factor,
            "total_fees": self.total_fees,
            "buy_hold_return_pct": self.buy_hold_return_pct,
            "rejected_orders": self.rejected_orders,
            "fee_bps": self.fee_bps,
            "slippage_bps": self.slippage_bps,
            "trade_list": self.trade_list,
            "open_positions": self.open_positions,
            "equity_curve": [{"ts": ts, "equity": equity} for ts, equity in sampled],
            "news_included": self.news_included,
        }


def max_drawdown_pct(equities: Sequence[float]) -> float:
    """Largest peak-to-trough fall of the series, in percent of the peak."""
    peak, worst = 0.0, 0.0
    for value in equities:
        peak = max(peak, value)
        if peak > 0:
            worst = max(worst, (peak - value) / peak * 100)
    return worst


def run_backtest(
    bars_by_symbol: Mapping[str, Sequence[Candle]],
    params: StrategyParams,
    limits: RiskLimits,
    starting_cash: float,
    fee_bps: float,
    slippage_bps: float,
    bar_ms: int = BAR_MS,
) -> BacktestResult:
    symbols = list(bars_by_symbol)
    snapshots = {s: build_snapshots(bars_by_symbol[s], params) for s in symbols}
    index = {s: {bar.ts: i for i, bar in enumerate(bars_by_symbol[s])} for s in symbols}
    timeline = sorted({bar.ts for s in symbols for bar in bars_by_symbol[s]})

    risk = RiskManager(MemoryRiskStore(limits))
    portfolio = Portfolio(cash=starting_cash, starting_cash=starting_cash, positions={})
    router = OrderRouter(risk, PaperBroker(fee_bps, slippage_bps), portfolio, fee_bps, slippage_bps)

    pending: list[_Pending] = []
    last_close: dict[str, float] = {}
    start_close: dict[str, float] = {}
    entry_bar: dict[str, int] = {}
    trade_list: list[dict] = []
    curve: list[tuple[int, float]] = []
    rejected = 0
    period_start: int | None = None

    for step, ts in enumerate(timeline):
        # 1. Fill orders decided on the previous bar at this bar's open. Exits first, then entries.
        waiting: list[_Pending] = []
        for order in sorted(
            pending,
            key=lambda o: (
                0
                if (
                    (o.side is Side.SELL and o.position_side is PositionSide.LONG)
                    or (o.side is Side.BUY and o.position_side is PositionSide.SHORT)
                )
                else 1,
                symbols.index(o.symbol),
            ),
        ):
            i = index[order.symbol].get(ts)
            if i is None:  # this symbol has no bar at this time (gap in the data): wait for its next bar
                waiting.append(order)
                continue
            bar = bars_by_symbol[order.symbol][i]
            quote = Quote(order.symbol, bid=bar.open, ask=bar.open, last=bar.open, ts=ts)
            held = portfolio.positions.get(order.symbol)
            result = router.submit(
                OrderRequest(order.symbol, order.side, order.qty),
                quote,
                equity=portfolio.equity(last_close) if last_close else starting_cash,
                ts_ms=ts,
                stop_price=order.stop_price,
                highest_close=order.highest_close,
                position_side=order.position_side,
            )
            if result.status == "rejected":
                rejected += 1
            elif held is None and result.fill is not None:
                entry_bar[order.symbol] = step
            elif held is not None and result.fill is not None:
                trade_list.append(
                    {
                        "symbol": order.symbol,
                        "side": held.side.value,
                        "entry_ts": held.entry_ts,
                        "entry_price": held.entry_price,
                        "exit_ts": ts,
                        "exit_price": result.fill.price,
                        "qty": held.qty,
                        "pnl": result.realized_pnl,
                        "return_pct": result.realized_pnl / (held.qty * held.entry_price) * 100
                        if held.qty * held.entry_price
                        else 0.0,
                        "fees": held.entry_fee + result.fill.fee,
                        "bars_held": step - entry_bar.pop(order.symbol, step),
                        "exit_reason": order.reason,
                    }
                )
        pending = waiting

        # 2. Value the portfolio at this bar's close.
        for s in symbols:
            i = index[s].get(ts)
            if i is not None:
                last_close[s] = bars_by_symbol[s][i].close
        equity = portfolio.equity(last_close) if last_close else starting_cash
        risk.update_equity(equity, ts + bar_ms)

        # 3. Decide on the bar that just closed; orders wait for the next open.
        queued = {o.symbol for o in pending}
        for s in symbols:
            i = index[s].get(ts)
            snap = snapshots[s][i] if i is not None else None
            if snap is None:
                continue
            if period_start is None:
                period_start = ts
            start_close.setdefault(s, snap.close)
            if s in queued:
                continue
            position = portfolio.positions.get(s)
            decision = decide(snap, position, NEWS_OFF, params)
            if decision.action is Action.ENTER and decision.position_side is not None:
                qty = position_size(equity, snap.atr, decision.size_multiplier, params)
                if qty > 0:
                    entry_side = Side.BUY if decision.position_side is PositionSide.LONG else Side.SELL
                    pending.append(
                        _Pending(
                            s,
                            entry_side,
                            qty,
                            decision.stop_price,
                            decision.highest_close,
                            decision.reasons[0],
                            decision.position_side,
                        )
                    )
            elif decision.action is Action.EXIT and position is not None:
                exit_side = Side.SELL if position.side is PositionSide.LONG else Side.BUY
                pending.append(
                    _Pending(s, exit_side, position.qty, None, None, decision.reasons[0], position.side)
                )
            elif position is not None and decision.stop_price is not None and decision.highest_close is not None:
                position.stop_price = decision.stop_price
                position.highest_close = decision.highest_close

        if period_start is not None:
            curve.append((ts + bar_ms, equity))

    final_equity = portfolio.equity(last_close) if last_close else starting_cash
    wins = sum(1 for t in trade_list if t["pnl"] > 0)
    gross_profit = sum(t["pnl"] for t in trade_list if t["pnl"] > 0)
    gross_loss = -sum(t["pnl"] for t in trade_list if t["pnl"] < 0)
    hold_returns = [last_close[s] / start_close[s] - 1 for s in symbols if s in start_close and start_close[s] > 0]

    return BacktestResult(
        symbols=symbols,
        data_start=timeline[0] if timeline else None,
        period_start=period_start,
        period_end=timeline[-1] + bar_ms if timeline else None,
        bars=len(curve),
        starting_cash=starting_cash,
        final_equity=final_equity,
        total_return_pct=(final_equity / starting_cash - 1) * 100,
        max_drawdown_pct=max_drawdown_pct([e for _, e in curve]),
        trades=len(trade_list),
        wins=wins,
        win_rate_pct=wins / len(trade_list) * 100 if trade_list else None,
        profit_factor=gross_profit / gross_loss if gross_loss > 0 else None,
        total_fees=portfolio.fees_paid,
        buy_hold_return_pct=sum(hold_returns) / len(hold_returns) * 100 if hold_returns else None,
        rejected_orders=rejected,
        fee_bps=fee_bps,
        slippage_bps=slippage_bps,
        trade_list=trade_list,
        open_positions=[
            {
                "symbol": p.symbol,
                "side": p.side.value,
                "qty": p.qty,
                "entry_ts": p.entry_ts,
                "entry_price": p.entry_price,
                "last_close": last_close[p.symbol],
                "unrealized_pnl": (
                    (last_close[p.symbol] - p.entry_price) * p.qty - p.entry_fee
                    if p.side is PositionSide.LONG
                    else (p.entry_price - last_close[p.symbol]) * p.qty - p.entry_fee
                ),
            }
            for p in portfolio.positions.values()
        ],
        equity_curve=curve,
    )
