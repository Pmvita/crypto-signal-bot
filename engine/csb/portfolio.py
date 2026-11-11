"""Cash and position ledger. Used unchanged by paper trading (persisted) and the backtester (in memory).

Longs: BUY opens, SELL closes. Shorts: SELL opens (cash rises by sale proceeds), BUY covers.
`highest_close` stores the favorable extreme (highest close for longs, lowest close for shorts).
Existing AppData rows without a `side` column migrate as long.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass

from csb.models import Fill, Position, PositionSide, Side

CASH_TOLERANCE = 1e-6


@dataclass
class Portfolio:
    cash: float
    starting_cash: float
    positions: dict[str, Position]
    realized_pnl: float = 0.0
    fees_paid: float = 0.0

    def apply_fill(
        self,
        fill: Fill,
        stop_price: float | None = None,
        highest_close: float | None = None,
        position_side: PositionSide | None = None,
    ) -> float | None:
        """Apply a fill. Returns realised P&L (net of entry and exit fees) on exits, None on entries."""
        notional = fill.qty * fill.price
        held = self.positions.get(fill.symbol)

        if held is None:
            return self._open(fill, notional, stop_price, highest_close, position_side)
        return self._close(fill, notional, held)

    def _open(
        self,
        fill: Fill,
        notional: float,
        stop_price: float | None,
        highest_close: float | None,
        position_side: PositionSide | None,
    ) -> None:
        if fill.side is Side.BUY:
            side = position_side or PositionSide.LONG
            if side is not PositionSide.LONG:
                raise ValueError("BUY without a short opens a long; pass PositionSide.LONG or omit side")
            cost = notional + fill.fee
            if cost > self.cash + CASH_TOLERANCE:
                raise ValueError(f"insufficient cash: need {cost:.2f}, have {self.cash:.2f}")
            self.cash -= cost
            self.fees_paid += fill.fee
            self.positions[fill.symbol] = Position(
                symbol=fill.symbol,
                qty=fill.qty,
                entry_price=fill.price,
                entry_ts=fill.ts,
                stop_price=stop_price if stop_price is not None else 0.0,
                highest_close=highest_close if highest_close is not None else fill.price,
                entry_fee=fill.fee,
                side=PositionSide.LONG,
            )
            return None

        # SELL with no position → open short; cash receives sale proceeds.
        side = position_side or PositionSide.SHORT
        if side is not PositionSide.SHORT:
            raise ValueError("SELL without a long opens a short; pass PositionSide.SHORT or omit side")
        self.cash += notional - fill.fee
        self.fees_paid += fill.fee
        self.positions[fill.symbol] = Position(
            symbol=fill.symbol,
            qty=fill.qty,
            entry_price=fill.price,
            entry_ts=fill.ts,
            stop_price=stop_price if stop_price is not None else 0.0,
            highest_close=highest_close if highest_close is not None else fill.price,
            entry_fee=fill.fee,
            side=PositionSide.SHORT,
        )
        return None

    def _close(self, fill: Fill, notional: float, position: Position) -> float:
        if abs(fill.qty - position.qty) > 1e-9 * max(1.0, position.qty):
            raise ValueError("partial exits are not supported")

        if position.side is PositionSide.LONG:
            if fill.side is not Side.SELL:
                raise ValueError(f"cannot BUY to close a long for {fill.symbol}")
            del self.positions[fill.symbol]
            self.cash += notional - fill.fee
            self.fees_paid += fill.fee
            pnl = (fill.price - position.entry_price) * fill.qty - fill.fee - position.entry_fee
            self.realized_pnl += pnl
            return pnl

        if fill.side is not Side.BUY:
            raise ValueError(f"cannot SELL to close a short for {fill.symbol}")
        cost = notional + fill.fee
        if cost > self.cash + CASH_TOLERANCE:
            raise ValueError(f"insufficient cash to cover short: need {cost:.2f}, have {self.cash:.2f}")
        del self.positions[fill.symbol]
        self.cash -= cost
        self.fees_paid += fill.fee
        pnl = (position.entry_price - fill.price) * fill.qty - fill.fee - position.entry_fee
        self.realized_pnl += pnl
        return pnl

    def equity(self, prices: Mapping[str, float]) -> float:
        """Cash plus mark-to-market. Longs add qty×price; shorts subtract qty×price (proceeds already in cash)."""
        total = self.cash
        for symbol, p in self.positions.items():
            mark = prices[symbol]
            if p.side is PositionSide.LONG:
                total += p.qty * mark
            else:
                total -= p.qty * mark
        return total


def _row_side(row: sqlite3.Row) -> PositionSide:
    try:
        raw = row["side"]
    except (IndexError, KeyError):
        return PositionSide.LONG
    if raw is None or raw == "":
        return PositionSide.LONG
    return PositionSide(str(raw))


def load_portfolio(conn: sqlite3.Connection, starting_cash: float) -> Portfolio:
    row = conn.execute("select * from account where id = 1").fetchone()
    if row is None:
        conn.execute(
            "insert into account (id, cash, starting_cash, realized_pnl, fees_paid) values (1, ?, ?, 0, 0)",
            (starting_cash, starting_cash),
        )
        conn.commit()
        return Portfolio(cash=starting_cash, starting_cash=starting_cash, positions={})
    positions = {
        r["symbol"]: Position(
            symbol=r["symbol"],
            qty=r["qty"],
            entry_price=r["entry_price"],
            entry_ts=r["entry_ts"],
            stop_price=r["stop_price"],
            highest_close=r["highest_close"],
            entry_fee=r["entry_fee"],
            side=_row_side(r),
        )
        for r in conn.execute("select * from positions order by symbol")
    }
    return Portfolio(
        cash=row["cash"],
        starting_cash=row["starting_cash"],
        positions=positions,
        realized_pnl=row["realized_pnl"],
        fees_paid=row["fees_paid"],
    )


def save_portfolio(conn: sqlite3.Connection, portfolio: Portfolio) -> None:
    conn.execute(
        """
        insert into account (id, cash, starting_cash, realized_pnl, fees_paid) values (1, ?, ?, ?, ?)
        on conflict (id) do update set cash = excluded.cash, realized_pnl = excluded.realized_pnl,
            fees_paid = excluded.fees_paid
        """,
        (portfolio.cash, portfolio.starting_cash, portfolio.realized_pnl, portfolio.fees_paid),
    )
    conn.execute("delete from positions")
    conn.executemany(
        "insert into positions (symbol, qty, entry_price, entry_ts, entry_fee, stop_price, highest_close, side)"
        " values (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                p.symbol,
                p.qty,
                p.entry_price,
                p.entry_ts,
                p.entry_fee,
                p.stop_price,
                p.highest_close,
                p.side.value,
            )
            for p in portfolio.positions.values()
        ],
    )
    conn.commit()
