"""News + corporate announcements."""
from __future__ import annotations
from typing import List, Optional
from fastapi import APIRouter, Query

from backend.deps import run_sync
from backend.schemas import NewsItem, AnnouncementItem
from backend.schemas.news import Sentiment

router = APIRouter(prefix="/api/news", tags=["news"])


def _sent(text: str) -> Sentiment:
    from services.news_service import classify_sentiment
    s = classify_sentiment(text or "") or {}
    label = (s.get("label") or s.get("sentiment") or "NEUTRAL").upper().replace(" ", "_")
    try:
        return Sentiment(label)
    except Exception:
        return Sentiment.NEUTRAL


def _to_news(d: dict) -> NewsItem:
    title = d.get("title") or ""
    summary = d.get("summary") or ""
    return NewsItem(
        title=title, summary=summary,
        url=d.get("url") or d.get("link"),
        published=d.get("published") or d.get("date"),
        source=d.get("source") or "Unknown",
        sentiment=_sent(f"{title} {summary}"),
    )


@router.get("/market", response_model=List[NewsItem])
async def market_news(limit: int = Query(60, ge=1, le=200)) -> List[NewsItem]:
    from services.news_service import get_market_news
    raw = await run_sync(get_market_news, limit, None)
    return [_to_news(d) for d in (raw or [])]


@router.get("/stock/{symbol}", response_model=List[NewsItem])
async def stock_news(symbol: str, limit: int = Query(20, ge=1, le=100)) -> List[NewsItem]:
    from services.news_service import get_stock_news
    raw = await run_sync(get_stock_news, symbol, limit)
    return [_to_news(d) for d in (raw or [])]


@router.get("/announcements", response_model=List[AnnouncementItem])
async def announcements(symbol: Optional[str] = None) -> List[AnnouncementItem]:
    from services.news_service import get_nse_announcements
    raw = await run_sync(get_nse_announcements, symbol)
    out: list[AnnouncementItem] = []
    for d in (raw or []):
        subj = d.get("subject") or d.get("subjectName") or ""
        out.append(AnnouncementItem(
            symbol=d.get("symbol") or symbol or "",
            subject=subj,
            desc=d.get("desc") or d.get("description"),
            date=d.get("date") or d.get("an_dt"),
            attachment_url=d.get("attachment") or d.get("attchmntFile"),
            sentiment=_sent(subj),
        ))
    return out
