import pytest

from csb.models import Action, Candle, NewsState, NewsView, Position
from csb.strategy import Snapshot, StrategyParams, build_snapshots, decide, news_state_for, position_size

P = StrategyParams()
OFF = NewsView(NewsState.OFF, None, [])


def snap(close, prior_high=120.0, atr=2.0, ema_fast=110.0, ema_slow=100.0):
    return Snapshot(ts=0, close=close, ema_fast=ema_fast, ema_slow=ema_slow, prior_high=prior_high, atr=atr)


def position(stop, highest):
    return Position("BTC/USD", 1.0, 100.0, 0, stop_price=stop, highest_close=highest)


def test_default_parameters_match_the_spec():
    assert (P.ema_fast, P.ema_slow, P.breakout_bars, P.atr_period) == (50, 200, 20, 14)
    assert (P.stop_atr_mult, P.risk_per_trade) == (3.0, 0.01)
    assert (P.news_veto, P.news_boost, P.news_boost_mult) == (-0.30, 0.30, 1.25)


def test_enters_on_breakout_in_uptrend_with_initial_stop_three_atr_below_close():
    d = decide(snap(121.0), None, OFF, P)
    assert d.action is Action.ENTER
    assert d.stop_price == pytest.approx(121.0 - 6.0)
    assert d.highest_close == 121.0
    assert d.size_multiplier == 1.0


def test_no_entry_when_trend_is_down_even_on_breakout():
    d = decide(snap(121.0, ema_fast=90.0), None, OFF, P)
    assert d.action is Action.HOLD
    assert any("trend" in r.lower() for r in d.reasons)


def test_no_entry_without_breakout():
    d = decide(snap(119.0), None, OFF, P)
    assert d.action is Action.HOLD
    assert any("20-bar high" in r for r in d.reasons)


def test_close_equal_to_prior_high_is_not_a_breakout():
    assert decide(snap(120.0), None, OFF, P).action is Action.HOLD


def test_bearish_news_vetoes_entry():
    d = decide(snap(121.0), None, NewsView(NewsState.VETO, -0.5, []), P)
    assert d.action is Action.HOLD
    assert any("news" in r.lower() for r in d.reasons)


def test_bullish_news_boosts_size_but_does_not_create_entry():
    boost = NewsView(NewsState.BOOST, 0.6, [])
    assert decide(snap(121.0), None, boost, P).size_multiplier == 1.25
    assert decide(snap(119.0), None, boost, P).action is Action.HOLD


def test_bearish_news_alone_does_not_exit_a_position():
    d = decide(snap(119.0), position(stop=90.0, highest=118.0), NewsView(NewsState.VETO, -0.9, []), P)
    assert d.action is Action.HOLD


def test_exits_when_close_falls_below_stop():
    d = decide(snap(114.0), position(stop=115.0, highest=125.0), OFF, P)
    assert d.action is Action.EXIT
    assert any("stop" in r.lower() for r in d.reasons)


def test_exits_when_trend_turns_down():
    d = decide(snap(119.0, ema_fast=99.0), position(stop=90.0, highest=119.0), OFF, P)
    assert d.action is Action.EXIT
    assert any("trend" in r.lower() for r in d.reasons)


def test_trailing_stop_ratchets_up_on_new_high():
    d = decide(snap(120.0), position(stop=100.0, highest=110.0), OFF, P)
    assert d.action is Action.HOLD
    assert d.highest_close == 120.0
    assert d.stop_price == pytest.approx(114.0)


def test_trailing_stop_never_moves_down_when_volatility_expands():
    d = decide(snap(118.0, atr=5.0), position(stop=114.0, highest=120.0), OFF, P)
    assert d.action is Action.HOLD
    assert d.stop_price == pytest.approx(114.0)
    assert d.highest_close == 120.0


def test_position_size_risks_one_percent_at_three_atr():
    assert position_size(10_000, 2.0, 1.0, P) == pytest.approx(100 / 6.0)


def test_position_size_scales_with_news_multiplier_and_is_zero_without_volatility():
    assert position_size(10_000, 2.0, 1.25, P) == pytest.approx(125 / 6.0)
    assert position_size(10_000, 0.0, 1.0, P) == 0.0


def test_news_state_thresholds():
    assert news_state_for(None, False, P) is NewsState.OFF
    assert news_state_for(0.9, False, P) is NewsState.OFF
    assert news_state_for(None, True, P) is NewsState.NO_HEADLINES
    assert news_state_for(-0.30, True, P) is NewsState.VETO
    assert news_state_for(-0.29, True, P) is NewsState.NEUTRAL
    assert news_state_for(0.30, True, P) is NewsState.BOOST


def test_build_snapshots_is_none_until_slow_ema_is_seeded():
    small = StrategyParams(ema_fast=2, ema_slow=4, breakout_bars=3, atr_period=2)
    candles = [Candle(i, 10 + i, 11 + i, 9 + i, 10 + i, 1.0) for i in range(6)]
    snaps = build_snapshots(candles, small)
    assert snaps[:3] == [None, None, None]
    assert snaps[3] is not None
    assert snaps[3].ts == 3 and snaps[3].close == 13
    assert snaps[5].prior_high == 15  # highs of bars 2, 3, 4 are 13, 14, 15
