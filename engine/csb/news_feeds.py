"""News sources: public RSS feeds that need no key. Each was checked for reachability on 2026-11-10."""

from __future__ import annotations

import calendar
import html
import re
from collections.abc import Sequence
from dataclasses import dataclass

import feedparser
import httpx

from csb.models import Headline

USER_AGENT = "crypto-signal-bot/0.1 (local paper-trading research bot)"
MAX_TITLE_CHARS = 300
_TAG = re.compile(r"<[^>]+>")
_SPACE = re.compile(r"\s+")


@dataclass(frozen=True)
class Feed:
    name: str
    kind: str  # "news" or "exchange"
    url: str


FEEDS: tuple[Feed, ...] = (
    Feed("CoinDesk", "news", "https://www.coindesk.com/arc/outboundfeeds/rss/"),
    Feed("Cointelegraph", "news", "https://cointelegraph.com/rss"),
    Feed("Decrypt", "news", "https://decrypt.co/feed"),
    Feed("The Block", "news", "https://www.theblock.co/rss.xml"),
    Feed("Kraken Blog", "exchange", "https://blog.kraken.com/feed"),
    Feed("Bitfinex Blog", "exchange", "https://blog.bitfinex.com/feed/"),
)


@dataclass(frozen=True)
class FeedResult:
    feed: Feed
    headlines: list[Headline]
    error: str | None


def new_http_client() -> httpx.Client:
    return httpx.Client(follow_redirects=True, timeout=20.0, headers={"User-Agent": USER_AGENT})


def _clean(title: str) -> str:
    text = html.unescape(_TAG.sub("", title))
    return _SPACE.sub(" ", text).strip()[:MAX_TITLE_CHARS]


def parse_feed(feed: Feed, content: bytes) -> list[Headline]:
    """Headlines from RSS or Atom bytes. Entries without a title, link or publish date are skipped."""
    parsed = feedparser.parse(content)
    headlines: list[Headline] = []
    for entry in parsed.entries:
        title = _clean(entry.get("title") or "")
        link = (entry.get("link") or "").strip()
        when = entry.get("published_parsed") or entry.get("updated_parsed")
        if not title or not link.startswith(("http://", "https://")) or when is None:
            continue
        headlines.append(Headline(feed.name, feed.kind, title, link, calendar.timegm(when) * 1000))
    return headlines


def fetch_feeds(client: httpx.Client, feeds: Sequence[Feed] = FEEDS) -> list[FeedResult]:
    """Fetch every feed. One failing source never stops the others; its error is returned instead."""
    results: list[FeedResult] = []
    for feed in feeds:
        try:
            response = client.get(feed.url)
            response.raise_for_status()
            headlines = parse_feed(feed, response.content)
            error = None if headlines else "Feed returned no usable entries."
        except httpx.HTTPStatusError as exc:
            headlines, error = [], f"HTTP {exc.response.status_code}"
        except httpx.HTTPError as exc:
            headlines, error = [], f"{type(exc).__name__}: {exc}"[:200]
        results.append(FeedResult(feed, headlines, error))
    return results
