import pytest

from csb.db import connect, init_schema
from csb.models import PositionSide, Side
from csb.risk import MemoryRiskStore, RiskLimits, RiskManager, SqliteRiskStore

DAY1 = 1_700_006_400_000 + 3_600_000  # 2023-11-15 01:00 UTC
DAY2 = DAY1 + 24 * 3_600_000


def manager():
    return RiskManager(MemoryRiskStore())


def buy(rm, qty=1.0, price=100.0, equity=10_000.0, cash=10_000.0, open_positions=0, has_position=False, fee=0.0):
    return rm.check_order(
        Side.BUY, qty, price, equity, cash, open_positions, has_position, fee, position_side=PositionSide.LONG
    )


def sell(
    rm,
    qty=1.0,
    price=100.0,
    equity=10_000.0,
    cash=0.0,
    open_positions=1,
    has_position=True,
    position_side: PositionSide | None = None,
):
    side = position_side if position_side is not None else (PositionSide.LONG if has_position else PositionSide.SHORT)
    return rm.check_order(Side.SELL, qty, price, equity, cash, open_positions, has_position, 0.0, position_side=side)


def short_entry(rm, qty=1.0, price=100.0, equity=10_000.0, cash=10_000.0, open_positions=0):
    return rm.check_order(
        Side.SELL, qty, price, equity, cash, open_positions, False, 0.0, position_side=PositionSide.SHORT
    )


def cover(rm, qty=1.0, price=100.0, equity=10_000.0, cash=10_000.0, fee=0.0):
    return rm.check_order(
        Side.BUY, qty, price, equity, cash, 1, True, fee, position_side=PositionSide.SHORT
    )


def test_defaults_match_the_spec():
    limits = manager().limits
    assert (limits.max_position_pct, limits.max_open_positions, limits.daily_loss_limit_pct) == (25.0, 3, 3.0)
    assert manager().state.kill_switch is False


def test_normal_entry_is_approved_unchanged():
    d = buy(manager())
    assert d.approved and d.qty == 1.0 and d.reason is None


def test_kill_switch_rejects_buys_and_sells():
    rm = manager()
    rm.set_kill_switch(True)
    for decision in (buy(rm), sell(rm)):
        assert not decision.approved
        assert "kill switch" in decision.reason.lower()
        assert decision.qty == 0.0


def test_releasing_kill_switch_allows_orders_again():
    rm = manager()
    rm.set_kill_switch(True)
    rm.set_kill_switch(False)
    assert buy(rm).approved


def test_daily_loss_limit_halts_entries_but_allows_exits():
    rm = manager()
    rm.update_equity(10_000, DAY1)
    assert not rm.state.halted
    rm.update_equity(9_690, DAY1 + 60_000)  # -3.1% on the day
    assert rm.state.halted and rm.state.halted_at == DAY1 + 60_000
    rejected = buy(rm, equity=9_690, cash=9_690)
    assert not rejected.approved and "daily loss" in rejected.reason.lower()
    assert sell(rm, equity=9_690).approved


def test_loss_just_inside_the_limit_does_not_halt():
    rm = manager()
    rm.update_equity(10_000, DAY1)
    rm.update_equity(9_701, DAY1 + 60_000)  # -2.99%
    assert not rm.state.halted


def test_halt_stays_for_the_rest_of_the_day_even_if_equity_recovers():
    rm = manager()
    rm.update_equity(10_000, DAY1)
    rm.update_equity(9_600, DAY1 + 60_000)
    rm.update_equity(10_500, DAY1 + 120_000)
    assert rm.state.halted


def test_halt_clears_on_next_utc_day_and_day_start_resets():
    rm = manager()
    rm.update_equity(10_000, DAY1)
    rm.update_equity(9_600, DAY1 + 60_000)
    state = rm.update_equity(9_600, DAY2)
    assert not state.halted and state.halted_at is None
    assert state.day == "2023-11-16" and state.day_start_equity == 9_600
    assert buy(rm, equity=9_600, cash=9_600).approved


def test_entry_is_clamped_to_max_position_size():
    d = buy(manager(), qty=100, price=100)
    assert d.approved
    assert d.qty == pytest.approx(25.0)  # 25% of 10,000 at price 100
    assert any("max position" in n.lower() for n in d.notes)


def test_entry_is_clamped_to_available_cash_including_fee():
    d = buy(manager(), qty=20, price=100, equity=10_000, cash=1_000, fee=0.01)
    assert d.approved
    assert d.qty == pytest.approx(1_000 / 101)
    assert d.qty * 100 * 1.01 <= 1_000 + 1e-9


def test_entry_rejected_when_clamps_leave_less_than_minimum_notional():
    d = buy(manager(), qty=1, price=100, cash=5)
    assert not d.approved and "minimum" in d.reason.lower()


def test_entry_rejected_at_max_open_positions():
    d = buy(manager(), open_positions=3)
    assert not d.approved and "open positions" in d.reason.lower()


def test_entry_rejected_when_symbol_already_has_a_position():
    assert not buy(manager(), open_positions=1, has_position=True).approved


def test_sell_without_long_opens_short_when_position_side_is_short():
    d = short_entry(manager())
    assert d.approved and d.qty == 1.0


def test_sell_marked_as_long_exit_without_position_is_rejected():
    assert not sell(manager(), has_position=False, position_side=PositionSide.LONG).approved


def test_short_entry_respects_max_position_size():
    d = short_entry(manager(), qty=100, price=100)
    assert d.approved
    assert d.qty == pytest.approx(25.0)


def test_cover_short_is_allowed_during_daily_halt():
    rm = manager()
    rm.update_equity(10_000, DAY1)
    rm.update_equity(9_600, DAY1 + 60_000)
    assert rm.state.halted
    assert cover(rm, equity=9_600, cash=9_600).approved


def test_sell_is_not_blocked_by_position_limits():
    rm = manager()
    rm.update_limits(RiskLimits(max_position_pct=1, max_open_positions=1, daily_loss_limit_pct=3))
    assert sell(rm, qty=50, open_positions=5).approved


def test_non_positive_quantity_or_price_is_rejected():
    assert not buy(manager(), qty=0).approved
    assert not buy(manager(), price=0).approved


@pytest.mark.parametrize(
    "limits",
    [
        RiskLimits(max_position_pct=0, max_open_positions=3, daily_loss_limit_pct=3),
        RiskLimits(max_position_pct=101, max_open_positions=3, daily_loss_limit_pct=3),
        RiskLimits(max_position_pct=25, max_open_positions=0, daily_loss_limit_pct=3),
        RiskLimits(max_position_pct=25, max_open_positions=21, daily_loss_limit_pct=3),
        RiskLimits(max_position_pct=25, max_open_positions=3, daily_loss_limit_pct=0.1),
        RiskLimits(max_position_pct=25, max_open_positions=3, daily_loss_limit_pct=51),
    ],
)
def test_invalid_limits_are_rejected_and_not_saved(limits):
    rm = manager()
    with pytest.raises(ValueError):
        rm.update_limits(limits)
    assert rm.limits == RiskLimits()


def test_limits_kill_switch_and_halt_survive_restart(tmp_path):
    path = tmp_path / "risk.sqlite3"
    conn = connect(path)
    init_schema(conn)
    rm = RiskManager(SqliteRiskStore(conn))
    rm.update_limits(RiskLimits(max_position_pct=10, max_open_positions=2, daily_loss_limit_pct=5))
    rm.set_kill_switch(True)
    rm.update_equity(10_000, DAY1)
    rm.update_equity(9_000, DAY1 + 60_000)
    conn.close()

    conn2 = connect(path)
    init_schema(conn2)
    restarted = RiskManager(SqliteRiskStore(conn2))
    assert restarted.limits == RiskLimits(max_position_pct=10, max_open_positions=2, daily_loss_limit_pct=5)
    assert restarted.state.kill_switch is True
    assert restarted.state.halted is True
    assert restarted.state.day == "2023-11-15" and restarted.state.day_start_equity == 10_000
    # Still the same UTC day after the restart: the halt must hold.
    restarted.set_kill_switch(False)
    restarted.update_equity(9_000, DAY1 + 120_000)
    assert not buy(restarted, equity=9_000, cash=9_000).approved


def test_equity_updates_do_not_overwrite_a_kill_switch_set_through_another_connection(tmp_path):
    path = tmp_path / "risk.sqlite3"
    loop_conn, api_conn = connect(path), connect(path)
    init_schema(loop_conn)
    loop_rm, api_rm = RiskManager(SqliteRiskStore(loop_conn)), RiskManager(SqliteRiskStore(api_conn))
    loop_rm.update_equity(10_000, DAY1)
    api_rm.set_kill_switch(True)
    loop_rm.update_equity(10_010, DAY1 + 60_000)
    assert loop_rm.state.kill_switch is True
    assert not buy(loop_rm).approved
