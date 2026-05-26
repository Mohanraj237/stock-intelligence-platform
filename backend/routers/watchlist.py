"""Watchlist CRUD + live refresh."""
from __future__ import annotations
import asyncio
from datetime import datetime, timezone
from typing import List
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.deps import run_sync
from backend.schemas import WatchlistRow

router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])


def _load() -> list[dict]:
    from storage.file_store import get_watchlist
    # Storage returns list[str]; we shape into list[dict] for API consistency
    return [{"symbol": s} for s in (get_watchlist() or [])]


def _save(items: list[dict]) -> None:
    from storage.file_store import save_watchlist
    save_watchlist([i.get("symbol") for i in items if i.get("symbol")])


@router.get("", response_model=List[WatchlistRow])
async def get_watchlist() -> List[WatchlistRow]:
    from services.nse_service import get_quote
    from services.market_data_service import get_ohlcv_history
    from services.chart_analysis_service import compute_indicators_from_ohlcv
    items = await run_sync(_load)

    async def _enrich(it: dict) -> WatchlistRow:
        sym = it.get("symbol", "")
        try:
            q = await run_sync(get_quote, sym)
        except Exception:
            q = None
        df = await run_sync(get_ohlcv_history, sym, "6mo", "1d")
        ind = await run_sync(compute_indicators_from_ohlcv, df) if df is not None else {}
        return WatchlistRow(
            symbol=sym,
            company=q.get("companyName") if q else None,
            last_price=q.get("lastPrice") if q else ind.get("close"),
            change_pct=q.get("pChange") if q else ind.get("change_pct"),
            rsi=ind.get("rsi"),
            macd_hist=ind.get("macd_hist"),
            sma50=ind.get("sma50"),
            sma200=ind.get("sma200"),
            volume=q.get("totalTradedVolume") if q else None,
            added_at=it.get("added_at"),
        )

    return await asyncio.gather(*[_enrich(it) for it in items])


class AddReq(BaseModel):
    symbol: str
    note: str | None = None


@router.post("/add")
async def add(req: AddReq) -> dict:
    items = await run_sync(_load)
    if any(i.get("symbol", "").upper() == req.symbol.upper() for i in items):
        return {"already_present": True, "symbol": req.symbol}
    items.append({
        "symbol": req.symbol.upper(),
        "added_at": datetime.now(timezone.utc).isoformat(),
        "note": req.note,
    })
    await run_sync(_save, items)
    return {"added": req.symbol.upper(), "count": len(items)}


@router.delete("/{symbol}")
async def remove(symbol: str) -> dict:
    items = await run_sync(_load)
    new_items = [i for i in items if i.get("symbol", "").upper() != symbol.upper()]
    if len(new_items) == len(items):
        raise HTTPException(status_code=404, detail="Symbol not in watchlist")
    await run_sync(_save, new_items)
    return {"removed": symbol, "remaining": len(new_items)}
