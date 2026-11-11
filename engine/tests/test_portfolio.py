import pytest

from csb.db import connect, init_schema
from csb.models import Fill, Side
from csb.portfolio import Portfolio, load_portfolio, save_portfolio


def fill(side, qty, price, fee, ts=0, symbol="BTC/USD"):
    return Fill(symbol, side, qty, price, fee, ts, "paper")


def test_buy_moves_cash_into_a_position_and_records_fee():
    pf = Portfolio(cash=10_000, starting_cash=10_000, positions={})
    assert pf.apply_fill(fill(Side.BUY, 2, 100, 0.8, ts=5), stop_price=94, highest_close=99) is None
    assert pf.cash == pytest.approx(10_000 - 200 - 0.8)
    pos = pf.positions["BTC/USD"]
    assert (pos.qty, pos.entry_price, pos.entry_ts, pos.stop_price, pos.highest_close, pos.entry_fee) == (
        2,
        100,
        5,
        94,
        99,
        0.8,
    )
    assert pf.fees_paid == pytest.approx(0.8)


def test_round_trip_realised_pnl_is_net_of_both_fees():
    pf = Portfolio(cash=10_000, starting_cash=10_000, positions={})
    pf.apply_fill(fill(Side.BUY, 2, 100, 0.8), stop_price=94, highest_close=100)
    pnl = pf.apply_fill(fill(Side.SELL, 2, 110, 0.88))
    assert pnl == pytest.approx(20 - 0.8 - 0.88)
    assert pf.realized_pnl == pytest.approx(pnl)
    assert pf.cash == pytest.approx(10_000 + pnl)
    assert pf.positions == {}
    assert pf.fees_paid == pytest.approx(1.68)


def test_equity_marks_positions_at_given_prices():
    pf = Portfolio(cash=10_000, starting_cash=10_000, positions={})
    pf.apply_fill(fill(Side.BUY, 2, 100, 0), stop_price=94, highest_close=100)
    assert pf.equity({"BTC/USD": 120.0}) == pytest.approx(9_800 + 240)


def test_equity_requires_a_price_for_every_open_position():
    pf = Portfolio(cash=10_000, starting_cash=10_000, positions={})
    pf.apply_fill(fill(Side.BUY, 2, 100, 0), stop_price=94, highest_close=100)
    with pytest.raises(KeyError):
        pf.equity({})


def test_buy_that_exceeds_cash_is_refused():
    pf = Portfolio(cash=100, starting_cash=100, positions={})
    with pytest.raises(ValueError):
        pf.apply_fill(fill(Side.BUY, 2, 100, 0), stop_price=94, highest_close=100)
    assert pf.cash == 100 and pf.positions == {}


def test_second_buy_of_same_symbol_is_refused():
    pf = Portfolio(cash=10_000, starting_cash=10_000, positions={})
    pf.apply_fill(fill(Side.BUY, 1, 100, 0), stop_price=94, highest_close=100)
    with pytest.raises(ValueError):
        pf.apply_fill(fill(Side.BUY, 1, 100, 0), stop_price=94, highest_close=100)


def test_sell_without_position_is_refused():
    pf = Portfolio(cash=10_000, starting_cash=10_000, positions={})
    with pytest.raises(ValueError):
        pf.apply_fill(fill(Side.SELL, 1, 100, 0))


def test_new_account_starts_with_starting_cash(tmp_path):
    conn = connect(tmp_path / "p.sqlite3")
    init_schema(conn)
    pf = load_portfolio(conn, starting_cash=7_500)
    assert pf.cash == 7_500 and pf.starting_cash == 7_500 and pf.positions == {}


def test_portfolio_round_trips_through_sqlite(tmp_path):
    path = tmp_path / "p.sqlite3"
    conn = connect(path)
    init_schema(conn)
    pf = load_portfolio(conn, starting_cash=10_000)
    pf.apply_fill(fill(Side.BUY, 2, 100, 0.8, ts=5), stop_price=94, highest_close=99)
    pf.apply_fill(fill(Side.BUY, 1, 50, 0.2, ts=6, symbol="ETH/USD"), stop_price=45, highest_close=50)
    pf.apply_fill(fill(Side.SELL, 1, 60, 0.24, ts=7, symbol="ETH/USD"))
    save_portfolio(conn, pf)
    conn.close()

    conn2 = connect(path)
    reloaded = load_portfolio(conn2, starting_cash=99_999)  # ignored: the account already exists
    assert reloaded.cash == pytest.approx(pf.cash)
    assert reloaded.starting_cash == 10_000
    assert reloaded.realized_pnl == pytest.approx(pf.realized_pnl)
    assert reloaded.fees_paid == pytest.approx(pf.fees_paid)
    assert reloaded.positions == pf.positions
