import pytest

from csb.indicators import atr, ema, prior_highest, prior_lowest
from csb.models import Candle


def test_ema_seeds_with_simple_average_then_smooths():
    out = ema([1, 2, 3, 4, 5], 3)
    assert out[:2] == [None, None]
    assert out[2] == pytest.approx(2.0)  # SMA of 1, 2, 3
    assert out[3] == pytest.approx(3.0)  # 2 + 0.5 * (4 - 2)
    assert out[4] == pytest.approx(4.0)


def test_ema_is_all_none_when_series_shorter_than_period():
    assert ema([1, 2], 3) == [None, None]


def test_ema_is_causal():
    """A value at index i must not change when later data is appended."""
    short = ema([5, 7, 6, 9, 8], 3)
    long = ema([5, 7, 6, 9, 8, 100, 1], 3)
    assert long[:5] == short


def test_prior_highest_excludes_current_bar():
    assert prior_highest([1, 5, 2, 9], 2) == [None, None, 5, 5]


def test_prior_lowest_excludes_current_bar():
    assert prior_lowest([4, 1, 3, 0], 2) == [None, None, 1, 1]


def test_atr_uses_true_range_including_gaps():
    cs = [Candle(0, 10, 11, 9, 10, 0), Candle(1, 10, 12, 10, 11, 0), Candle(2, 14, 15, 13, 14, 0)]
    out = atr(cs, 2)
    assert out[:2] == [None, None]
    assert out[2] == pytest.approx((2 + 4) / 2)  # TR1 = 12-10 = 2, TR2 = 15-11 = 4 (gap up)


def test_atr_wilder_smoothing_after_seed():
    cs = [
        Candle(0, 10, 11, 9, 10, 0),
        Candle(1, 10, 12, 10, 11, 0),  # TR 2
        Candle(2, 11, 15, 11, 14, 0),  # TR 4
        Candle(3, 14, 15, 13, 14, 0),  # TR 2
    ]
    out = atr(cs, 2)
    assert out[2] == pytest.approx(3.0)
    assert out[3] == pytest.approx((3.0 * 1 + 2) / 2)
