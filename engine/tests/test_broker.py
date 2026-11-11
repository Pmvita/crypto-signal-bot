import pytest

from csb.broker import PaperBroker
from csb.models import Quote, Side

QUOTE = Quote("BTC/USD", bid=99.0, ask=101.0, last=100.0, ts=0)


def test_paper_buy_fills_at_ask_plus_slippage_and_charges_fee():
    fill = PaperBroker(fee_bps=40, slippage_bps=5).market_order("BTC/USD", Side.BUY, 0.5, QUOTE, 123)
    assert fill.price == pytest.approx(101 * 1.0005)
    assert fill.fee == pytest.approx(0.5 * 101 * 1.0005 * 0.004)
    assert (fill.symbol, fill.side, fill.qty, fill.ts, fill.broker) == ("BTC/USD", Side.BUY, 0.5, 123, "paper")


def test_paper_sell_fills_at_bid_minus_slippage():
    fill = PaperBroker(fee_bps=40, slippage_bps=5).market_order("BTC/USD", Side.SELL, 2.0, QUOTE, 0)
    assert fill.price == pytest.approx(99 * 0.9995)
    assert fill.fee == pytest.approx(2.0 * 99 * 0.9995 * 0.004)


def test_paper_falls_back_to_last_when_bid_ask_missing():
    quote = Quote("BTC/USD", bid=None, ask=None, last=100.0, ts=0)
    broker = PaperBroker(fee_bps=0, slippage_bps=10)
    assert broker.market_order("BTC/USD", Side.BUY, 1, quote, 0).price == pytest.approx(100.1)
    assert broker.market_order("BTC/USD", Side.SELL, 1, quote, 0).price == pytest.approx(99.9)


def test_paper_broker_rejects_non_positive_quantity():
    with pytest.raises(ValueError):
        PaperBroker(fee_bps=40, slippage_bps=5).market_order("BTC/USD", Side.BUY, 0, QUOTE, 0)
