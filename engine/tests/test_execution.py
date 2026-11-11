import pytest

from csb.broker import PaperBroker
from csb.execution import OrderRouter
from csb.models import OrderRequest, Quote, Side
from csb.portfolio import Portfolio
from csb.risk import MemoryRiskStore, RiskManager

QUOTE = Quote("BTC/USD", bid=99.0, ask=100.0, last=99.5, ts=0)


class RecordingBroker(PaperBroker):
    def __init__(self):
        super().__init__(fee_bps=40, slippage_bps=5)
        self.calls = []

    def market_order(self, symbol, side, qty, quote, ts_ms):
        self.calls.append((symbol, side, qty))
        return super().market_order(symbol, side, qty, quote, ts_ms)


def setup():
    broker = RecordingBroker()
    risk = RiskManager(MemoryRiskStore())
    portfolio = Portfolio(cash=10_000, starting_cash=10_000, positions={})
    records = []
    router = OrderRouter(
        risk, broker, portfolio, fee_bps=40, slippage_bps=5, recorder=lambda *args: records.append(args)
    )
    return router, broker, risk, portfolio, records


def test_router_does_not_call_broker_when_risk_rejects():
    router, broker, risk, portfolio, records = setup()
    risk.set_kill_switch(True)
    result = router.submit(OrderRequest("BTC/USD", Side.BUY, 1), QUOTE, equity=10_000, ts_ms=0)
    assert result.status == "rejected"
    assert "kill switch" in result.reason.lower()
    assert result.fill is None
    assert broker.calls == []
    assert portfolio.cash == 10_000 and portfolio.positions == {}
    assert len(records) == 1  # rejections are recorded too


def test_router_fills_approved_buy_and_applies_it_to_the_portfolio():
    router, broker, _, portfolio, records = setup()
    result = router.submit(
        OrderRequest("BTC/USD", Side.BUY, 2, signal_id=7), QUOTE, 10_000, ts_ms=42, stop_price=94, highest_close=99
    )
    assert result.status == "filled" and result.qty == 2
    assert result.fill.price == pytest.approx(100 * 1.0005)
    pos = portfolio.positions["BTC/USD"]
    assert pos.qty == 2 and pos.stop_price == 94 and pos.highest_close == 99 and pos.entry_ts == 42
    assert portfolio.cash == pytest.approx(10_000 - 2 * 100.05 * 1.004)
    assert records[0][0].signal_id == 7


def test_router_reports_quantity_clamped_by_risk_limits():
    router, broker, _, portfolio, _ = setup()
    result = router.submit(OrderRequest("BTC/USD", Side.BUY, 1_000), QUOTE, 10_000, ts_ms=0, stop_price=94)
    assert result.status == "filled"
    assert result.requested_qty == 1_000
    assert result.qty == pytest.approx(2_500 / 100.05)
    assert broker.calls[0][2] == pytest.approx(2_500 / 100.05)
    assert portfolio.cash >= 0


def test_buy_sized_to_all_cash_never_overdraws_after_fee_and_slippage():
    router, _, risk, portfolio, _ = setup()
    portfolio.cash = 1_000
    result = router.submit(OrderRequest("BTC/USD", Side.BUY, 50), QUOTE, 10_000, ts_ms=0, stop_price=94)
    assert result.status == "filled"
    assert portfolio.cash >= -1e-9
    assert portfolio.cash < 0.01  # everything affordable was spent


def test_router_sells_the_whole_position_and_reports_realised_pnl():
    router, _, _, portfolio, _ = setup()
    router.submit(OrderRequest("BTC/USD", Side.BUY, 2), QUOTE, 10_000, ts_ms=0, stop_price=94, highest_close=99)
    higher = Quote("BTC/USD", bid=110.0, ask=111.0, last=110.5, ts=1)
    result = router.submit(OrderRequest("BTC/USD", Side.SELL, 2), higher, 10_020, ts_ms=1)
    assert result.status == "filled"
    assert portfolio.positions == {}
    buy_price, sell_price = 100 * 1.0005, 110 * 0.9995
    expected = 2 * (sell_price - buy_price) - 2 * buy_price * 0.004 - 2 * sell_price * 0.004
    assert result.realized_pnl == pytest.approx(expected)


def test_router_rejects_sell_without_position():
    router, broker, _, _, _ = setup()
    result = router.submit(OrderRequest("BTC/USD", Side.SELL, 1), QUOTE, 10_000, ts_ms=0)
    assert result.status == "rejected" and broker.calls == []
