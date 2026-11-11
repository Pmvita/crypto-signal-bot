import pytest

from csb.backtest import max_drawdown_pct, run_backtest
from csb.models import Candle
from csb.risk import RiskLimits
from csb.strategy import StrategyParams

BAR_MS = 15 * 60_000
T0 = 1_700_006_400_000
P = StrategyParams(ema_fast=3, ema_slow=6, breakout_bars=3, atr_period=3)
LIMITS = RiskLimits()

# Flat at 100 for 8 bars, +2 per bar for 12 bars (to 124), then -4 per bar for 10 bars.
CLOSES = [100.0] * 8 + [100.0 + 2 * i for i in range(1, 13)] + [124.0 - 4 * i for i in range(1, 11)]
SIGNAL_BAR = 8  # first rising bar: closes above the flat 3-bar high while EMA3 > EMA6


def bars_from(closes, t0=T0):
    out, prev = [], closes[0]
    for i, close in enumerate(closes):
        out.append(Candle(t0 + i * BAR_MS, prev, max(prev, close) + 0.5, min(prev, close) - 0.5, close, 1.0))
        prev = close
    return out


BARS = bars_from(CLOSES)


def run(bars=BARS, fee_bps=40.0, slippage_bps=5.0, limits=LIMITS, symbols=("BTC/USD",)):
    return run_backtest({s: bars for s in symbols}, P, limits, 10_000.0, fee_bps, slippage_bps, bar_ms=BAR_MS)


def test_fills_at_next_bar_open_not_signal_bar_close():
    trade = next(t for t in run().trade_list if t["side"] == "long")
    assert trade["entry_ts"] == BARS[SIGNAL_BAR + 1].ts
    assert trade["entry_price"] == pytest.approx(BARS[SIGNAL_BAR + 1].open * 1.0005)


def test_round_trip_exits_at_next_open_after_exit_signal_with_slippage():
    result = run()
    longs = [t for t in result.trade_list if t["side"] == "long"]
    assert len(longs) >= 1
    trade = longs[0]
    exit_bar = next(b for b in BARS if b.ts == trade["exit_ts"])
    assert trade["exit_price"] == pytest.approx(exit_bar.open * 0.9995)
    assert trade["pnl"] > 0


def test_final_equity_equals_cash_flows_of_the_trade():
    result = run()
    closed = sum(t["pnl"] for t in result.trade_list)
    open_upnl = sum(p["unrealized_pnl"] for p in result.open_positions)
    assert result.final_equity == pytest.approx(10_000 + closed + open_upnl)
    assert result.total_return_pct == pytest.approx((closed + open_upnl) / 100)


def test_fees_and_slippage_reduce_return():
    free = run(fee_bps=0, slippage_bps=0)
    paid = run()
    assert free.total_fees == 0
    assert paid.total_fees > 0
    assert paid.final_equity < free.final_equity


def test_flat_market_makes_no_trades_and_zero_return():
    result = run(bars=bars_from([100.0] * 40))
    assert result.trades == 0 and result.trade_list == []
    assert result.final_equity == 10_000 and result.total_return_pct == 0
    assert result.max_drawdown_pct == 0
    assert result.win_rate_pct is None and result.profit_factor is None


def test_max_drawdown_is_peak_to_trough():
    assert max_drawdown_pct([100, 120, 90, 130]) == pytest.approx(25.0)
    assert max_drawdown_pct([100, 110, 120]) == 0
    assert max_drawdown_pct([]) == 0


def test_reported_drawdown_matches_the_equity_curve():
    result = run()
    assert result.max_drawdown_pct == pytest.approx(max_drawdown_pct([e for _, e in result.equity_curve]))
    assert result.max_drawdown_pct > 0  # the position gave back gains before the exit


def test_signal_on_last_bar_is_not_executed():
    result = run(bars=BARS[: SIGNAL_BAR + 1])
    assert result.trades == 0 and result.open_positions == []
    assert result.final_equity == 10_000


def test_position_open_at_the_end_is_marked_to_last_close_and_not_counted_as_a_trade():
    bars = BARS[:15]
    result = run(bars=bars)
    assert result.trades == 0
    assert len(result.open_positions) == 1
    pos = result.open_positions[0]
    cost = pos["qty"] * pos["entry_price"] * 1.004
    assert result.final_equity == pytest.approx(10_000 - cost + pos["qty"] * bars[-1].close)


def test_no_lookahead_entry_is_identical_on_truncated_history():
    full_trade = next(t for t in run().trade_list if t["side"] == "long")
    truncated = run(bars=BARS[:15]).open_positions[0]
    assert truncated["entry_ts"] == full_trade["entry_ts"]
    assert truncated["entry_price"] == pytest.approx(full_trade["entry_price"])
    assert truncated["qty"] == pytest.approx(full_trade["qty"])


def test_position_size_risks_one_percent_of_equity_at_the_initial_stop():
    trade = next(t for t in run().trade_list if t["side"] == "long")
    # ATR3 on the signal bar: flat bars have true range 1, the signal bar 3 -> (1*2 + 3) / 3
    atr_value = (1 * 2 + 3) / 3
    assert trade["qty"] == pytest.approx(10_000 * 0.01 / (3 * atr_value))


def test_result_is_marked_price_only():
    result = run()
    assert result.news_included is False
    assert result.to_dict()["news_included"] is False


def test_max_open_positions_limit_applies_in_backtest():
    limits = RiskLimits(max_position_pct=25, max_open_positions=1, daily_loss_limit_pct=50)
    result = run(limits=limits, symbols=("BTC/USD", "ETH/USD"))
    assert {t["symbol"] for t in result.trade_list} == {"BTC/USD"}
    assert result.rejected_orders >= 1


def test_period_starts_at_first_bar_with_complete_indicators_and_reports_buy_and_hold():
    result = run()
    assert result.data_start == BARS[0].ts
    assert result.period_start == BARS[5].ts  # EMA6 is first available on the sixth bar
    assert result.period_end == BARS[-1].ts + BAR_MS
    assert result.buy_hold_return_pct == pytest.approx((BARS[-1].close / BARS[5].close - 1) * 100)


def test_to_dict_is_json_ready_and_caps_the_equity_curve():
    data = run(bars=bars_from([100.0] * 2_000)).to_dict()
    assert len(data["equity_curve"]) <= 600
    assert set(data["equity_curve"][0]) == {"ts", "equity"}


def test_downtrend_breakdown_produces_a_short_trade():
    # Flat, then break down while EMA3 < EMA6, then bounce enough to exit on trend flip / trail.
    closes = [100.0] * 8 + [100.0 - 2 * i for i in range(1, 10)] + [82.0 + i for i in range(1, 12)]
    result = run(bars=bars_from(closes))
    assert result.trades >= 1
    assert any(t.get("side") == "short" for t in result.trade_list)
