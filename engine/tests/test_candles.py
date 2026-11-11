from csb.candles import HOUR_MS, aggregate, latest_ts, load_candles, upsert_candles
from csb.db import connect, init_schema
from csb.models import Candle

DAY0 = 1_700_006_400_000  # 2023-11-15 00:00:00 UTC, a 4h boundary


def hourly(n, start=DAY0, base=100.0):
    return [Candle(start + i * HOUR_MS, base + i, base + i + 2, base + i - 1, base + i + 1, 10.0) for i in range(n)]


def test_day0_fixture_is_on_a_4h_utc_boundary():
    assert DAY0 % (4 * HOUR_MS) == 0


def test_aggregate_builds_utc_aligned_4h_bars_and_drops_unfinished_bucket():
    bars = aggregate(hourly(6), 4, now_ms=DAY0 + 5 * HOUR_MS + 30 * 60_000)
    assert len(bars) == 1
    bar = bars[0]
    assert bar.ts == DAY0
    assert bar.open == 100.0  # open of the first hour
    assert bar.close == 104.0  # close of the fourth hour
    assert bar.high == 105.0  # highest high of hours 0..3
    assert bar.low == 99.0  # lowest low of hours 0..3
    assert bar.volume == 40.0


def test_aggregate_emits_bucket_exactly_when_its_end_time_is_reached():
    assert aggregate(hourly(4), 4, now_ms=DAY0 + 4 * HOUR_MS - 1) == []
    assert len(aggregate(hourly(4), 4, now_ms=DAY0 + 4 * HOUR_MS)) == 1


def test_aggregate_aligns_to_utc_even_when_data_starts_mid_bucket():
    bars = aggregate(hourly(7, start=DAY0 + HOUR_MS), 4, now_ms=DAY0 + 24 * HOUR_MS)
    assert [b.ts for b in bars] == [DAY0, DAY0 + 4 * HOUR_MS]
    assert bars[0].open == 100.0 and bars[0].close == 103.0  # three hours only: 01, 02, 03


def test_upsert_is_idempotent_and_load_returns_sorted(tmp_path):
    conn = connect(tmp_path / "t.sqlite3")
    init_schema(conn)
    cs = hourly(3)
    upsert_candles(conn, "x", "BTC/USD", "1h", list(reversed(cs)))
    upsert_candles(conn, "x", "BTC/USD", "1h", cs)
    assert load_candles(conn, "x", "BTC/USD", "1h") == cs
    assert latest_ts(conn, "x", "BTC/USD", "1h") == cs[-1].ts
    assert latest_ts(conn, "x", "ETH/USD", "1h") is None


def test_load_candles_filters_by_since_and_keeps_series_separate(tmp_path):
    conn = connect(tmp_path / "t.sqlite3")
    init_schema(conn)
    upsert_candles(conn, "x", "BTC/USD", "1h", hourly(3))
    upsert_candles(conn, "x", "ETH/USD", "1h", hourly(2, base=50.0))
    assert len(load_candles(conn, "x", "BTC/USD", "1h", since_ms=DAY0 + HOUR_MS)) == 2
    assert len(load_candles(conn, "x", "ETH/USD", "1h")) == 2
