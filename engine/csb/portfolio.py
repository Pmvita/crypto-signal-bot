"""Cash and position ledger. Used unchanged by paper trading (persisted) and the backtester (in memory)."""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass

from csb.models import Fill, Position, Side

CASH_TOLERANCE = 1e-6


@dataclass
class Portfolio:
    cash: float
    starting_cash: float
    positions: dict[str, Position]
    realized_pnl: float = 0.0
    fees_paid: float = 0.0

    def apply_fill(
        self, fill: Fill, stop_price: float | None = None, highest_close: float | None = None
    ) -> float | None:
        """Apply a fill. Returns realised P&L (net of entry and exit fees) for sells, None for buys."""
        notional = fill.qty * fill.price
        if fill.side is Side.BUY:
            if fill.symbol in self.positions:
                raise ValueError(f"position already open for {fill.symbol}")
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
            )
            return None

        position = self.positions.get(fill.symbol)
        if position is None:
            raise ValueError(f"no position to sell for {fill.symbol}")
        if abs(fill.qty - position.qty) > 1e-9 * max(1.0, position.qty):
            raise ValueError("partial exits are not supported")
        del self.positions[fill.symbol]
        self.cash += notional - fill.fee
        self.fees_paid += fill.fee
        pnl = (fill.price - position.entry_price) * fill.qty - fill.fee - position.entry_fee
        self.realized_pnl += pnl
        return pnl

    def equity(self, prices: Mapping[str, float]) -> float:
        """Cash plus positions valued at `prices`. Raises KeyError if an open position has no price."""
        return self.cash + sum(p.qty * prices[symbol] for symbol, p in self.positions.items())


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
        "insert into positions (symbol, qty, entry_price, entry_ts, entry_fee, stop_price, highest_close)"
        " values (?, ?, ?, ?, ?, ?, ?)",
        [
            (p.symbol, p.qty, p.entry_price, p.entry_ts, p.entry_fee, p.stop_price, p.highest_close)
            for p in portfolio.positions.values()
        ],
    )
    conn.commit()
