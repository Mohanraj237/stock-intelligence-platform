"""Market-wide endpoints: status, indices, sectors, FII/DII, universe quotes."""
from __future__ import annotations
from typing import List
from fastapi import APIRouter, HTTPException

from backend.deps import run_sync
from backend.schemas import (
    MarketStatus, IndexPerf, SectorPerf, FIIDIIRow, UniverseRow,
)

router = APIRouter(prefix="/api/market", tags=["market"])


def _coerce_index_perf(d: dict) -> IndexPerf:
    name = d.get("index") or d.get("name") or d.get("indexName") or d.get("symbol", "")
    return IndexPerf(
        symbol=d.get("symbol") or d.get("indexSymbol") or name,
        name=name,
        last_price=float(d.get("last") or d.get("lastPrice") or d.get("last_price") or 0),
        change=float(d.get("change") or 0),
        change_pct=float(d.get("pct") or d.get("change_pct") or d.get("pChange") or d.get("percentChange") or 0),
        open=d.get("open"),
        high=d.get("high") or d.get("dayHigh"),
        low=d.get("low") or d.get("dayLow"),
        prev_close=d.get("prev_close") or d.get("previousClose"),
    )


@router.get("/status", response_model=MarketStatus)
async def market_status() -> MarketStatus:
    from services.nse_service import get_market_status
    raw = await run_sync(get_market_status)
    raw = raw or {}
    return MarketStatus(
        status=str(raw.get("marketStatus") or raw.get("status") or "UNKNOWN"),
        is_open=bool(raw.get("is_open") or (str(raw.get("marketStatus") or "").lower() == "open")),
        trade_date=raw.get("tradeDate") or raw.get("trade_date"),
        nifty=raw.get("nifty") or raw.get("last"),
        nifty_change_pct=raw.get("nifty_change_pct") or raw.get("pChange"),
        market_cap_lakh_cr=raw.get("market_cap_lakh_cr") or raw.get("marketCap"),
        gift_nifty=raw.get("gift_nifty"),
        gift_nifty_change_pct=raw.get("gift_nifty_change_pct"),
    )


@router.get("/indices", response_model=List[IndexPerf])
async def indices() -> List[IndexPerf]:
    from services.nse_service import get_index_performance
    raw = await run_sync(get_index_performance)
    return [_coerce_index_perf(d) for d in (raw or [])]


@router.get("/sectors", response_model=List[SectorPerf])
async def sectors() -> List[SectorPerf]:
    from services.nse_service import get_sector_performance
    raw = await run_sync(get_sector_performance)
    out = []
    for d in (raw or []):
        # NSE service returns: index, sector, last, pct, change, advancing, declining, stocks
        name = (d.get("index") or d.get("sector") or d.get("name") or d.get("indexName") or "").strip()
        if not name:
            continue  # Skip malformed entries — would otherwise cause duplicate empty React keys
        out.append(SectorPerf(
            name=name,
            symbol=(d.get("symbol") or d.get("indexSymbol") or name),
            last_price=d.get("last") or d.get("lastPrice"),
            change_pct=float(d.get("pct") or d.get("change_pct") or d.get("pChange") or 0),
            advances=int(d.get("advancing") or d.get("advances") or 0),
            declines=int(d.get("declining") or d.get("declines") or 0),
            unchanged=int(d.get("unchanged") or 0),
        ))
    return out


@router.get("/fii-dii", response_model=List[FIIDIIRow])
async def fii_dii() -> List[FIIDIIRow]:
    from services.nse_service import get_fii_dii_data
    raw = await run_sync(get_fii_dii_data)
    out = []
    for d in (raw or []):
        out.append(FIIDIIRow(
            date=str(d.get("date") or ""),
            fii_buy=float(d.get("fii_buy") or 0),
            fii_sell=float(d.get("fii_sell") or 0),
            fii_net=float(d.get("fii_net") or 0),
            dii_buy=float(d.get("dii_buy") or 0),
            dii_sell=float(d.get("dii_sell") or 0),
            dii_net=float(d.get("dii_net") or 0),
        ))
    return out


@router.get("/universe/{name}/quotes", response_model=List[UniverseRow])
async def universe_quotes(name: str) -> List[UniverseRow]:
    from services.nse_service import get_index_quotes
    try:
        raw = await run_sync(get_index_quotes, name)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"NSE fetch failed: {e}") from e
    out: List[UniverseRow] = []
    for d in (raw or []):
        out.append(UniverseRow(
            symbol=d.get("symbol") or d.get("Symbol") or "",
            company=d.get("company") or d.get("companyName"),
            last_price=d.get("lastPrice") or d.get("last_price") or d.get("last"),
            change_pct=d.get("pChange") or d.get("change_pct"),
            open=d.get("open"),
            high=d.get("dayHigh") or d.get("high"),
            low=d.get("dayLow") or d.get("low"),
            prev_close=d.get("previousClose") or d.get("prev_close"),
            week52_high=d.get("yearHigh") or d.get("week52_high"),
            week52_low=d.get("yearLow") or d.get("week52_low"),
            volume=d.get("totalTradedVolume") or d.get("volume"),
            return_30d=d.get("perChange30d") or d.get("return_30d"),
            return_1y=d.get("perChange365d") or d.get("return_1y"),
        ))
    return out
