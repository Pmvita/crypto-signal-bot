import httpx

from csb.news_feeds import FEEDS, Feed, fetch_feeds, parse_feed

RSS = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>Example</title>
<item>
  <title>Bitcoin   ETF sees record &amp; inflows</title>
  <link>https://example.com/a</link>
  <pubDate>Tue, 10 Nov 2026 20:36:33 +0000</pubDate>
</item>
<item>
  <title><![CDATA[<b>Solana</b> outage resolved]]></title>
  <link>https://example.com/b</link>
  <pubDate>Tue, 10 Nov 2026 15:36:33 -0500</pubDate>
</item>
<item><title>No link here</title><pubDate>Tue, 10 Nov 2026 20:36:33 +0000</pubDate></item>
<item><title>No date here</title><link>https://example.com/c</link></item>
</channel></rss>"""

FEED = Feed("Example", "news", "https://example.com/rss")
EXPECTED_TS = 1_794_342_993_000  # 2026-11-10 20:36:33 UTC


def test_parse_feed_extracts_title_url_and_utc_published_time():
    headlines = parse_feed(FEED, RSS)
    assert [h.url for h in headlines] == ["https://example.com/a", "https://example.com/b"]
    first = headlines[0]
    assert first.title == "Bitcoin ETF sees record & inflows"
    assert (first.source, first.kind) == ("Example", "news")
    assert first.published_at == EXPECTED_TS


def test_parse_feed_converts_offsets_to_utc_and_strips_markup():
    second = parse_feed(FEED, RSS)[1]
    assert second.published_at == EXPECTED_TS  # 15:36:33 -0500 is the same instant
    assert second.title == "Solana outage resolved"


def test_parse_feed_skips_entries_without_link_or_date():
    assert len(parse_feed(FEED, RSS)) == 2


def test_fetch_feeds_reports_failure_per_source_without_stopping():
    ok, forbidden, junk = (
        Feed("Good", "news", "https://good.example/rss"),
        Feed("Blocked", "exchange", "https://blocked.example/rss"),
        Feed("Junk", "news", "https://junk.example/rss"),
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "good.example":
            return httpx.Response(200, content=RSS)
        if request.url.host == "junk.example":
            return httpx.Response(200, content=b"<html><body>not a feed</body></html>")
        return httpx.Response(403)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    results = fetch_feeds(client, (ok, forbidden, junk))
    assert [r.feed.name for r in results] == ["Good", "Blocked", "Junk"]
    assert results[0].error is None and len(results[0].headlines) == 2
    assert results[1].headlines == [] and "403" in results[1].error
    assert results[2].headlines == [] and results[2].error


def test_configured_feeds_cover_news_and_exchange_sources_over_https():
    assert {f.kind for f in FEEDS} == {"news", "exchange"}
    assert all(f.url.startswith("https://") for f in FEEDS)
    assert len({f.name for f in FEEDS}) == len(FEEDS)
