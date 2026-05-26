"""
News feed service for Indian markets.

Sources (all free, no API key required):
  - Moneycontrol RSS (markets, business, top news)
  - Economic Times RSS (markets, stocks, economy)
  - Business Standard RSS (markets)
  - LiveMint RSS (markets, money)
  - NSE corporate announcements (per-stock disclosures)

Public API:
  - get_market_news(limit=50) -> aggregated market news
  - get_stock_news(symbol, limit=20) -> per-stock news (filtered + announcements)
  - get_nse_announcements(symbol=None) -> raw NSE corporate announcements
  - classify_sentiment(text) -> {"label": "POSITIVE|NEUTRAL|NEGATIVE", "score": int}
"""
from __future__ import annotations
import logging
import re
import time
import threading
from datetime import datetime
from typing import Optional, List, Dict
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# RSS feeds
# ─────────────────────────────────────────────────────────────────────────────
RSS_FEEDS = {
    "Moneycontrol — Markets":   "https://www.moneycontrol.com/rss/marketreports.xml",
    "Moneycontrol — Business":  "https://www.moneycontrol.com/rss/business.xml",
    "Moneycontrol — Top News":  "https://www.moneycontrol.com/rss/MCtopnews.xml",
    "Economic Times — Markets": "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
    "Economic Times — Stocks":  "https://economictimes.indiatimes.com/markets/stocks/rssfeeds/2146842.cms",
    "Economic Times — Economy": "https://economictimes.indiatimes.com/news/economy/rssfeeds/1373380680.cms",
    "Business Standard — Markets": "https://www.business-standard.com/rss/markets-106.rss",
    "LiveMint — Markets":       "https://www.livemint.com/rss/markets",
    "LiveMint — Money":         "https://www.livemint.com/rss/money",
}


# ─────────────────────────────────────────────────────────────────────────────
# NSE session (corporate announcements)
# ─────────────────────────────────────────────────────────────────────────────
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com",
}

_NSE_SESSION: Optional[requests.Session] = None
_NSE_TS: float = 0
_NSE_LOCK = threading.Lock()


def _nse_session() -> requests.Session:
    global _NSE_SESSION, _NSE_TS
    with _NSE_LOCK:
        if _NSE_SESSION is None or (time.time() - _NSE_TS) > 300:
            s = requests.Session()
            s.headers.update(_HEADERS)
            try:
                s.get("https://www.nseindia.com", timeout=8)
            except Exception:
                pass
            _NSE_SESSION = s
            _NSE_TS = time.time()
        return _NSE_SESSION


# ─────────────────────────────────────────────────────────────────────────────
# Sentiment (lightweight keyword-based; works for headlines)
# ─────────────────────────────────────────────────────────────────────────────
_POSITIVE_KW = {
    "surge", "rally", "jump", "soar", "rise", "gain", "high", "record", "beat",
    "outperform", "upgrade", "buy", "bullish", "strong", "growth", "profit",
    "expand", "win", "deal", "acquisition", "approval", "approved", "launch",
    "breakout", "all-time", "lifetime", "boom", "rebound", "recovery",
}
_NEGATIVE_KW = {
    "fall", "drop", "decline", "plunge", "tumble", "crash", "loss", "weak",
    "downgrade", "sell", "bearish", "miss", "warn", "warning", "cut", "slash",
    "scam", "fraud", "probe", "raid", "fine", "penalty", "default", "lawsuit",
    "delist", "suspend", "halted", "breakdown", "low", "underperform",
    "concerns", "risk", "challenge",
}


def classify_sentiment(text: str) -> Dict:
    """Lightweight headline sentiment using keyword scoring."""
    if not text:
        return {"label": "NEUTRAL", "score": 0, "color": "neutral"}
    t = text.lower()
    pos = sum(1 for kw in _POSITIVE_KW if kw in t)
    neg = sum(1 for kw in _NEGATIVE_KW if kw in t)
    score = pos - neg
    if score >= 2:    label, color = "POSITIVE", "bullish"
    elif score == 1:  label, color = "MILDLY POSITIVE", "bullish"
    elif score == -1: label, color = "MILDLY NEGATIVE", "bearish"
    elif score <= -2: label, color = "NEGATIVE", "bearish"
    else:             label, color = "NEUTRAL", "neutral"
    return {"label": label, "score": score, "color": color}


# ─────────────────────────────────────────────────────────────────────────────
# RSS fetching
# ─────────────────────────────────────────────────────────────────────────────
def _parse_rss(url: str, source_name: str, timeout: int = 10) -> List[Dict]:
    try:
        import feedparser
    except ImportError:
        logger.error("feedparser not installed. Run: pip install feedparser")
        return []
    try:
        d = feedparser.parse(url)
        items: List[Dict] = []
        for entry in d.entries[:50]:
            title = entry.get("title", "")
            summary = entry.get("summary", entry.get("description", ""))
            # Clean HTML tags from summary
            summary = re.sub(r"<[^>]+>", "", summary).strip()
            link = entry.get("link", "")
            published = entry.get("published", entry.get("updated", ""))
            try:
                ts = time.mktime(entry.published_parsed)
            except Exception:
                ts = 0
            sentiment = classify_sentiment(f"{title} {summary[:200]}")
            items.append({
                "title": title,
                "summary": summary[:400],
                "link": link,
                "published": published,
                "ts": ts,
                "source": source_name,
                "sentiment": sentiment["label"],
                "sentiment_color": sentiment["color"],
                "sentiment_score": sentiment["score"],
            })
        return items
    except Exception as e:
        logger.warning(f"RSS parse failed for {source_name}: {e}")
        return []


def get_market_news(limit: int = 60, sources: Optional[List[str]] = None) -> List[Dict]:
    """Aggregate market news from all RSS feeds in parallel."""
    feeds = RSS_FEEDS
    if sources:
        feeds = {k: v for k, v in RSS_FEEDS.items() if k in sources}

    all_items: List[Dict] = []
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(_parse_rss, url, name): name for name, url in feeds.items()}
        for f in as_completed(futs):
            try:
                all_items.extend(f.result())
            except Exception as e:
                logger.debug(f"news fetch failed: {e}")

    # De-dupe by title
    seen = set()
    deduped = []
    for it in sorted(all_items, key=lambda x: x.get("ts", 0), reverse=True):
        key = it["title"][:80].lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(it)
        if len(deduped) >= limit:
            break
    return deduped


def get_stock_news(symbol: str, limit: int = 20) -> List[Dict]:
    """Filter aggregated news for headlines mentioning this symbol or its variants."""
    sym = symbol.upper().strip().replace(".NS", "").replace(".BO", "")
    all_news = get_market_news(limit=200)
    matched = []
    for it in all_news:
        text = f"{it['title']} {it.get('summary','')}".upper()
        # Match symbol as a whole word, or short company-name patterns
        if re.search(rf"\b{re.escape(sym)}\b", text):
            matched.append(it)
        if len(matched) >= limit:
            break
    return matched


# ─────────────────────────────────────────────────────────────────────────────
# NSE corporate announcements
# ─────────────────────────────────────────────────────────────────────────────
def get_nse_announcements(symbol: Optional[str] = None,
                          days_back: int = 7) -> List[Dict]:
    """Pull NSE corporate-announcements API. If symbol set, filter to that stock."""
    sess = _nse_session()
    url = "https://www.nseindia.com/api/corporate-announcements"
    params: Dict = {"index": "equities"}
    if symbol:
        params["symbol"] = symbol.upper().strip()
    try:
        resp = sess.get(url, params=params, timeout=15)
        if resp.status_code != 200:
            logger.warning(f"NSE announcements → {resp.status_code}")
            return []
        data = resp.json()
    except Exception as e:
        logger.warning(f"NSE announcements failed: {e}")
        return []

    rows = data if isinstance(data, list) else data.get("data", [])
    out: List[Dict] = []
    for r in rows[:100]:
        title = (r.get("desc") or r.get("subject") or r.get("attchmntText") or "").strip()
        sentiment = classify_sentiment(title)
        out.append({
            "symbol":   r.get("symbol", ""),
            "company":  r.get("sm_name", ""),
            "title":    title[:300],
            "subject":  (r.get("subject") or "")[:200],
            "date":     r.get("an_dt") or r.get("dissemDT") or "",
            "attachment": r.get("attchmntFile") or "",
            "sentiment": sentiment["label"],
            "sentiment_color": sentiment["color"],
        })
    return out
