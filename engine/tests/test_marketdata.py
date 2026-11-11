import pytest

from csb.candles import BAR_MS, HOUR_MS, load_candles
from csb.db import connect, init_schema
from csb.marketdata import WARMUP_DAYS, MarketData, create_exchange

NOW = 1_700_006_400_000 + 10 * 60_000  # 00:10 UTC: the 00:00 15m candle is still forming


class FakeExchange:
    """Serves 15m candles from `first_ts` up to and including the forming one, like a real exchange."""

    def __init__(self, first_ts, now, ignore_since=False, page_cap=1000):
        self.first_ts = first_ts
        self.now = now
        self.ignore_since = ignore_since
        self.page_cap = page_cap
        self.calls = []

    def _all(self):
        out, ts = [], self.first_ts
        while ts <= self.now:
            price = 100.0 + (ts - self.first_ts) / BAR_MS
            out.append([ts, price, price + 1, price - 1, price + 0.5, 5.0])
            ts += BAR_MS
        return out

    def fetch_ohlcv(self, symbol, timeframe, since=None, limit=None):
        self.calls.append((symbol, timeframe, since, limit))
        rows = self._all()
        size = min(limit or self.page_cap, self.page_cap)
        if self.ignore_since or since is None:
            return rows[-size:]
        return [r for r in rows if r[0] >= since][:size]

    def fetch_ticker(self, symbol):
        return {"symbol": symbol, "bid": 99.5, "ask": 100.5, "last": 100.0, "timestamp": self.now}


@pytest.fixture
def conn(tmp_path):
    c = connect(tmp_path / "m.sqlite3")
    init_schema(c)
    return c


def test_backfill_pages_until_present_and_stores_only_closed_candles(conn):
    first = NOW - 10 * 60_000 - 1000 * BAR_MS  # 1000 closed 15m candles before the forming one
    exchange = FakeExchange(first, NOW)
    md = MarketData(exchange, "fake", conn, clock=lambda: NOW)
    stored = md.backfill("BTC/USD", days=60)
    candles = load_candles(conn, "fake", "BTC/USD", "15m")
    assert stored == len(candles) == 1000
    assert candles[0].ts == first
    assert candles[-1].ts + BAR_MS <= NOW  # the forming candle is not stored
    assert len(exchange.calls) >= 4  # 300 per page
    assert all(call[1] == "15m" for call in exchange.calls)


def test_backfill_starts_at_requested_window_not_at_listing_date(conn):
    exchange = FakeExchange(NOW - 5000 * BAR_MS, NOW)
    md = MarketData(exchange, "fake", conn, clock=lambda: NOW)
    md.backfill("BTC/USD", days=2)
    candles = load_candles(conn, "fake", "BTC/USD", "15m")
    # ~2 days of 15m bars = 192; allow a little slack for alignment
    assert 180 <= len(candles) <= 200
    assert candles[0].ts >= NOW - 2 * 24 * HOUR_MS - BAR_MS


def test_backfill_stops_when_exchange_ignores_since(conn):
    """Kraken's public OHLC endpoint returns the same most recent page whatever `since` is."""
    exchange = FakeExchange(NOW - 5000 * BAR_MS, NOW, ignore_since=True, page_cap=720)
    md = MarketData(exchange, "fake", conn, clock=lambda: NOW)
    md.backfill("BTC/USD", days=365)
    assert len(exchange.calls) <= 3
    assert 1 <= len(load_candles(conn, "fake", "BTC/USD", "15m")) <= 720


def test_update_fetches_only_after_latest_stored_ts(conn):
    exchange = FakeExchange(NOW - 10 * 60_000 - 100 * BAR_MS, NOW)
    md = MarketData(exchange, "fake", conn, clock=lambda: NOW)
    md.backfill("BTC/USD", days=10)
    before = load_candles(conn, "fake", "BTC/USD", "15m")
    exchange.calls.clear()

    later = NOW + 2 * BAR_MS
    exchange.now = later
    md2 = MarketData(exchange, "fake", conn, clock=lambda: later)
    added = md2.update("BTC/USD")
    after = load_candles(conn, "fake", "BTC/USD", "15m")
    assert added == 2 and len(after) == len(before) + 2
    assert exchange.calls[0][2] == before[-1].ts + BAR_MS


def test_update_with_empty_database_backfills_enough_for_indicator_warmup(conn):
    exchange = FakeExchange(NOW - 20_000 * BAR_MS, NOW)
    md = MarketData(exchange, "fake", conn, clock=lambda: NOW)
    md.update("BTC/USD")
    # WARMUP_DAYS of 15m bars should cover EMA200 with headroom
    assert len(load_candles(conn, "fake", "BTC/USD", "15m")) >= 200 + 24
    assert WARMUP_DAYS >= 30


def test_quote_maps_ticker_fields(conn):
    md = MarketData(FakeExchange(NOW - BAR_MS, NOW), "fake", conn, clock=lambda: NOW)
    q = md.quote("BTC/USD")
    assert (q.symbol, q.bid, q.ask, q.last, q.ts) == ("BTC/USD", 99.5, 100.5, 100.0, NOW)


def test_quote_without_a_last_price_raises(conn):
    exchange = FakeExchange(NOW - BAR_MS, NOW)
    exchange.fetch_ticker = lambda symbol: {"symbol": symbol, "bid": None, "ask": None, "last": None}
    with pytest.raises(ValueError):
        MarketData(exchange, "fake", conn, clock=lambda: NOW).quote("BTC/USD")


def test_create_exchange_rejects_unknown_id_and_uses_no_credentials():
    with pytest.raises(ValueError):
        create_exchange("not-an-exchange")
    exchange = create_exchange("kraken")
    assert not exchange.apiKey and not exchange.secret
