"""Risk limits. Every order, live or backtest, passes through RiskManager.check_order.

Settings and state live in a store (SQLite in the service, memory in backtests and tests) and are read
fresh on every call, so a change made through the API is seen by the trading loop on its next order.

  kill switch        rejects every order, exits included
  daily loss limit   once hit, rejects entries until the next UTC day; exits stay allowed
  max open positions rejects entries beyond the limit
  max position size  shrinks an entry so its notional stays within the limit
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Protocol

from csb.db import now_ms
from csb.models import PositionSide, Side

MIN_NOTIONAL = 10.0


@dataclass(frozen=True)
class RiskLimits:
    max_position_pct: float = 25.0
    max_open_positions: int = 3
    daily_loss_limit_pct: float = 3.0

    def validate(self) -> None:
        if not 1 <= self.max_position_pct <= 100:
            raise ValueError("max_position_pct must be between 1 and 100")
        if not 1 <= self.max_open_positions <= 20:
            raise ValueError("max_open_positions must be between 1 and 20")
        if not 0.5 <= self.daily_loss_limit_pct <= 50:
            raise ValueError("daily_loss_limit_pct must be between 0.5 and 50")


@dataclass(frozen=True)
class RiskState:
    kill_switch: bool = False
    day: str | None = None
    day_start_equity: float | None = None
    halted: bool = False
    halted_at: int | None = None


@dataclass(frozen=True)
class RiskDecision:
    approved: bool
    qty: float
    reason: str | None = None
    notes: list[str] = field(default_factory=list)


class RiskStore(Protocol):
    def load_limits(self) -> RiskLimits: ...
    def save_limits(self, limits: RiskLimits) -> None: ...
    def load_state(self) -> RiskState: ...
    def save_kill_switch(self, engaged: bool) -> None: ...
    def save_day(self, day: str, day_start_equity: float, halted: bool, halted_at: int | None) -> None: ...


class MemoryRiskStore:
    def __init__(self, limits: RiskLimits | None = None) -> None:
        self._limits = limits or RiskLimits()
        self._state = RiskState()

    def load_limits(self) -> RiskLimits:
        return self._limits

    def save_limits(self, limits: RiskLimits) -> None:
        self._limits = limits

    def load_state(self) -> RiskState:
        return self._state

    def save_kill_switch(self, engaged: bool) -> None:
        self._state = replace(self._state, kill_switch=engaged)

    def save_day(self, day: str, day_start_equity: float, halted: bool, halted_at: int | None) -> None:
        self._state = replace(
            self._state, day=day, day_start_equity=day_start_equity, halted=halted, halted_at=halted_at
        )


class SqliteRiskStore:
    """Persists limits and state. Writes touch only their own columns, so the API thread setting the kill
    switch and the loop thread updating the daily state cannot overwrite each other."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        defaults = RiskLimits()
        conn.execute(
            "insert or ignore into risk_settings (id, max_position_pct, max_open_positions, daily_loss_limit_pct,"
            " updated_at) values (1, ?, ?, ?, ?)",
            (defaults.max_position_pct, defaults.max_open_positions, defaults.daily_loss_limit_pct, now_ms()),
        )
        conn.execute("insert or ignore into risk_state (id, kill_switch, halted) values (1, 0, 0)")
        conn.commit()

    def load_limits(self) -> RiskLimits:
        row = self._conn.execute("select * from risk_settings where id = 1").fetchone()
        return RiskLimits(row["max_position_pct"], row["max_open_positions"], row["daily_loss_limit_pct"])

    def save_limits(self, limits: RiskLimits) -> None:
        self._conn.execute(
            "update risk_settings set max_position_pct = ?, max_open_positions = ?, daily_loss_limit_pct = ?,"
            " updated_at = ? where id = 1",
            (limits.max_position_pct, limits.max_open_positions, limits.daily_loss_limit_pct, now_ms()),
        )
        self._conn.commit()

    def load_state(self) -> RiskState:
        row = self._conn.execute("select * from risk_state where id = 1").fetchone()
        return RiskState(
            kill_switch=bool(row["kill_switch"]),
            day=row["day"],
            day_start_equity=row["day_start_equity"],
            halted=bool(row["halted"]),
            halted_at=row["halted_at"],
        )

    def save_kill_switch(self, engaged: bool) -> None:
        self._conn.execute("update risk_state set kill_switch = ? where id = 1", (int(engaged),))
        self._conn.commit()

    def save_day(self, day: str, day_start_equity: float, halted: bool, halted_at: int | None) -> None:
        self._conn.execute(
            "update risk_state set day = ?, day_start_equity = ?, halted = ?, halted_at = ? where id = 1",
            (day, day_start_equity, int(halted), halted_at),
        )
        self._conn.commit()


def utc_day(ts_ms: int) -> str:
    return datetime.fromtimestamp(ts_ms / 1000, tz=UTC).strftime("%Y-%m-%d")


def _is_exit(side: Side, position_side: PositionSide | None) -> bool:
    if position_side is None:
        return False
    if side is Side.SELL and position_side is PositionSide.LONG:
        return True
    if side is Side.BUY and position_side is PositionSide.SHORT:
        return True
    return False


class RiskManager:
    def __init__(self, store: RiskStore) -> None:
        self._store = store

    @property
    def limits(self) -> RiskLimits:
        return self._store.load_limits()

    @property
    def state(self) -> RiskState:
        return self._store.load_state()

    def update_limits(self, limits: RiskLimits) -> None:
        limits.validate()
        self._store.save_limits(limits)

    def set_kill_switch(self, engaged: bool) -> None:
        self._store.save_kill_switch(engaged)

    def update_equity(self, equity: float, ts_ms: int) -> RiskState:
        """Record current equity. Starts a new UTC day when the date changes and trips the daily halt."""
        state = self._store.load_state()
        day = utc_day(ts_ms)
        if state.day != day or state.day_start_equity is None:
            self._store.save_day(day, equity, False, None)
        elif not state.halted:
            floor = state.day_start_equity * (1 - self._store.load_limits().daily_loss_limit_pct / 100)
            if state.day_start_equity > 0 and equity <= floor:
                self._store.save_day(day, state.day_start_equity, True, ts_ms)
        return self._store.load_state()

    def check_order(
        self,
        side: Side,
        qty: float,
        price: float,
        equity: float,
        cash: float,
        open_positions: int,
        has_position: bool,
        fee_rate: float,
        position_side: PositionSide | None = None,
    ) -> RiskDecision:
        """Approve, shrink or reject one order. `price` is the expected fill price."""
        if qty <= 0 or price <= 0:
            return RiskDecision(False, 0.0, "Invalid order: quantity and price must be positive.")

        state = self._store.load_state()
        if state.kill_switch:
            return RiskDecision(False, 0.0, "Kill switch engaged: no orders are placed.")

        if _is_exit(side, position_side):
            if not has_position:
                return RiskDecision(False, 0.0, "No open position to close.")
            if side is Side.BUY:
                # Covering a short spends cash; clamp to what is affordable so paper stays solvent.
                affordable = cash / (price * (1 + fee_rate)) if price * (1 + fee_rate) > 0 else 0.0
                if qty > affordable + 1e-12:
                    return RiskDecision(
                        False,
                        0.0,
                        f"Insufficient cash to cover short: need {qty * price * (1 + fee_rate):.2f}, have {cash:.2f}.",
                    )
            return RiskDecision(True, qty)

        # Entry path: BUY opens long, SELL opens short.
        if has_position:
            return RiskDecision(False, 0.0, "A position is already open for this symbol.")
        if side is Side.SELL and position_side is PositionSide.LONG:
            return RiskDecision(False, 0.0, "No open position to sell.")
        if side is Side.BUY and position_side is PositionSide.SHORT:
            return RiskDecision(False, 0.0, "No open short to cover.")

        limits = self._store.load_limits()
        if state.halted:
            return RiskDecision(
                False,
                0.0,
                f"Daily loss limit of {limits.daily_loss_limit_pct:g}% hit: entries halted until the next UTC day.",
            )
        if open_positions >= limits.max_open_positions:
            return RiskDecision(False, 0.0, f"Max open positions ({limits.max_open_positions}) reached.")

        notes: list[str] = []
        max_notional = equity * limits.max_position_pct / 100
        if qty * price > max_notional:
            qty = max_notional / price
            notes.append(f"Reduced to max position size ({limits.max_position_pct:g}% of equity).")

        if side is Side.BUY:
            affordable = cash / (price * (1 + fee_rate))
            if qty > affordable:
                qty = max(affordable, 0.0)
                notes.append("Reduced to available cash.")

        if qty * price < MIN_NOTIONAL:
            return RiskDecision(
                False, 0.0, f"Order is below the minimum notional of {MIN_NOTIONAL:g} USD after limits.", notes
            )
        return RiskDecision(True, qty, None, notes)
