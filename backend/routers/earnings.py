"""Earnings calendar + per-stock earnings history."""
from __future__ import annotations
from typing import List
from fastapi import APIRouter, Query

from backend.deps import run_sync
from backend.schemas import EarningsItem, UpcomingResult
from backend.schemas.news import Sentiment

router = APIRouter(prefix="/api/earnings", tags=["earnings"])


@router.get("/upcoming", response_model=List[UpcomingResult])
async def upcoming(days_ahead: int = Query(14, ge=1, le=90)) -> List[UpcomingResult]:
    from services.earnings_service import get_upcoming_results
    raw = await run_sync(get_upcoming_results, days_ahead)
    out: list[UpcomingResult] = []
    for d in (raw or []):
        out.append(UpcomingResult(
            symbol=d.get("symbol", ""),
            company=d.get("company") or d.get("companyName"),
            meeting_date=str(d.get("meeting_date") or d.get("date") or ""),
            purpose=d.get("purpose"),
            agenda=d.get("agenda") or d.get("subject"),
        ))
    return out


@router.get("/recent/{symbol}", response_model=List[EarningsItem])
async def recent(symbol: str, n: int = Query(4, ge=1, le=12)) -> List[EarningsItem]:
    from services.earnings_service import get_recent_earnings, classify_earnings
    raw = await run_sync(get_recent_earnings, symbol, n)
    out: list[EarningsItem] = []
    for d in (raw or []):
        sent_label = await run_sync(classify_earnings, d.get("sales_growth_pct"), d.get("profit_growth_pct"))
        try:
            sent = Sentiment(str(sent_label).upper().replace(" ", "_"))
        except Exception:
            sent = Sentiment.NEUTRAL
        out.append(EarningsItem(
            symbol=symbol.upper(), period=str(d.get("period", "")),
            sales=d.get("sales"), net_profit=d.get("net_profit"),
            opm_pct=d.get("opm_pct"),
            sales_yoy_pct=d.get("sales_growth_pct"),
            profit_yoy_pct=d.get("profit_growth_pct"),
            sentiment=sent,
        ))
    return out
