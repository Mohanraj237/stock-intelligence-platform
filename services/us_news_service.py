"""
US News Service — RSS-based market and stock news for US region.
Fetches from Yahoo Finance RSS and Google News RSS (no API key needed).
"""
from __future__ import annotations
import logging
import time
import xml.etree.ElementTree as ET
from typing import Optional

import requests

logger = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
}

_MARKET_RSS_FEEDS = [
    ("https://feeds.finance.yahoo.com/rss/2.0/headline?s=%5EGSPC&region=US&lang=en-US", "Yahoo Finance"),
    ("https://finance.yahoo.com/news/rssindex", "Yahoo Finance"),
    ("https://feeds.finance.yahoo.com/rss/2.0/headline?s=%5EIXIC&region=US&lang=en-US", "Yahoo Finance"),
]


def _parse_rss(xml_text: str, source: str) -> list[dict]:
    """Parse an RSS feed into a list of news dicts."""
    items = []
    try:
        root = ET.fromstring(xml_text)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        channel = root.find("channel")
        entries = channel.findall("item") if channel is not None else root.findall(".//item")
        for item in entries:
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            pub = (item.findtext("pubDate") or "").strip()
            desc = (item.findtext("description") or "").strip()
            if not title:
                continue
            items.append({
                "title":     title,
                "url":       link or None,
                "published": pub or None,
                "summary":   desc[:300] if desc else None,
                "source":    source,
            })
    except Exception as e:
        logger.debug(f"RSS parse error ({source}): {e}")
    return items


def _fetch_rss(url: str, source: str, timeout: int = 10) -> list[dict]:
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=timeout)
        if resp.status_code == 200:
            return _parse_rss(resp.text, source)
    except Exception as e:
        logger.debug(f"RSS fetch failed {url}: {e}")
    return []


def get_us_market_news(limit: int = 60) -> list[dict]:
    """Fetch US market news from Yahoo Finance RSS feeds."""
    items: list[dict] = []
    seen_titles: set[str] = set()
    for url, source in _MARKET_RSS_FEEDS:
        if len(items) >= limit:
            break
        for item in _fetch_rss(url, source):
            t = item["title"]
            if t not in seen_titles:
                seen_titles.add(t)
                items.append(item)
    return items[:limit]


def get_us_stock_news(symbol: str, limit: int = 25) -> list[dict]:
    """Fetch news for a specific US stock via Yahoo Finance RSS."""
    clean = symbol.upper().strip()
    url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={clean}&region=US&lang=en-US"
    items = _fetch_rss(url, "Yahoo Finance")
    if not items:
        url2 = f"https://news.google.com/rss/search?q={clean}+stock&hl=en-US&gl=US&ceid=US:en"
        items = _fetch_rss(url2, "Google News")
    return items[:limit]
