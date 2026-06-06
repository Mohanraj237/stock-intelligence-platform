"""Market-wide endpoints: status, indices, sectors, FII/DII, universe quotes."""
from __future__ import annotations
import json
import logging
import pathlib
from concurrent.futures import ThreadPoolExecutor, as_completed as _as_completed
from typing import List
from fastapi import APIRouter, HTTPException, Query

from backend.deps import run_sync
from backend.schemas import (
    MarketStatus, IndexPerf, SectorPerf, FIIDIIRow, UniverseRow,
)

logger = logging.getLogger(__name__)

_YAHOO_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}

# Resolved once at import time — always correct regardless of CWD
_UNIVERSE_DIR = pathlib.Path(__file__).parent.parent.parent / "storage" / "universe"


def _universe_yf_fallback(name: str) -> list[dict]:
    """Load stored index JSON and parallel-fetch live prices via Yahoo Finance v8 chart API."""
    import requests

    json_name = name.replace(" ", "_").upper()
    json_file = _UNIVERSE_DIR / f"{json_name}.json"
    if not json_file.exists():
        logger.warning("Universe fallback: JSON file not found: %s", json_file)
        return []
    try:
        data = json.loads(json_file.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Universe fallback: failed to parse JSON: %s", exc)
        return []
    symbols: list[str] = data.get("symbols", [])
    companies: dict = data.get("companies", {})
    if not symbols:
        return []

    def _fetch_one(sym: str) -> dict | None:
        try:
            resp = requests.get(
                f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}.NS",
                params={"interval": "1d", "range": "5d"},
                headers=_YAHOO_HEADERS,
                timeout=10,
            )
            if resp.status_code != 200:
                return None
            result = resp.json()["chart"]["result"][0]
            meta = result.get("meta", {})
            q = result["indicators"]["quote"][0]

            price = meta.get("regularMarketPrice")
            prev = meta.get("previousClose") or meta.get("chartPreviousClose")

            def _last(lst: list) -> float | None:
                vals = [v for v in (lst or []) if v is not None]
                return vals[-1] if vals else None

            close = _last(q.get("close", []))
            pct = None
            if price and prev and prev > 0:
                pct = round((price - prev) / prev * 100, 2)

            return {
                "symbol": sym,
                "company": companies.get(sym),
                "price": price or close,
                "change_pct": pct,
                "open": _last(q.get("open", [])),
                "high": _last(q.get("high", [])),
                "low": _last(q.get("low", [])),
                "prev_close": prev,
                "year_high": meta.get("fiftyTwoWeekHigh"),
                "year_low": meta.get("fiftyTwoWeekLow"),
                "volume": _last(q.get("volume", [])),
            }
        except Exception as exc:
            logger.debug("Universe fallback fetch failed for %s: %s", sym, exc)
            return None

    out: list[dict] = []
    with ThreadPoolExecutor(max_workers=15) as ex:
        futures = {ex.submit(_fetch_one, s): s for s in symbols}
        for fut in _as_completed(futures):
            r = fut.result()
            if r:
                out.append(r)

    sym_order = {s: i for i, s in enumerate(symbols)}
    out.sort(key=lambda d: sym_order.get(d["symbol"], 999))
    return out

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
async def market_status(region: str = Query("IN")) -> MarketStatus:
    if region == "US":
        from services.us_market_service import get_market_status as us_status
        raw = await run_sync(us_status)
        raw = raw or {}
        status_str = str(raw.get("status") or "UNKNOWN")
        return MarketStatus(
            status=status_str,
            is_open=(status_str == "OPEN"),
            trade_date=raw.get("trade_date"),
            nifty=raw.get("sp500"),
            nifty_change_pct=raw.get("pct"),
            market_cap_lakh_cr=None,
            gift_nifty=raw.get("nasdaq"),
            gift_nifty_change_pct=raw.get("nasdaq_pct"),
        )
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
async def indices(region: str = Query("IN")) -> List[IndexPerf]:
    if region == "US":
        from services.us_market_service import get_index_performance as us_indices
        raw = await run_sync(us_indices)
        return [_coerce_index_perf(d) for d in (raw or [])]
    from services.nse_service import get_index_performance
    raw = await run_sync(get_index_performance)
    return [_coerce_index_perf(d) for d in (raw or [])]


@router.get("/sectors", response_model=List[SectorPerf])
async def sectors(region: str = Query("IN")) -> List[SectorPerf]:
    if region == "US":
        from services.us_market_service import get_sector_performance as us_sectors
        raw = await run_sync(us_sectors)
        out = []
        for d in (raw or []):
            name = (d.get("sector") or d.get("name") or "").strip()
            if not name:
                continue
            out.append(SectorPerf(
                name=name,
                symbol=d.get("etf") or d.get("symbol") or name,
                last_price=d.get("last") or d.get("last_price") or d.get("price"),
                change_pct=float(d.get("pct") or d.get("change_pct") or 0),
                advances=int(d.get("advances") or 0),
                declines=int(d.get("declines") or 0),
                unchanged=int(d.get("unchanged") or 0),
            ))
        return out
    from services.nse_service import get_sector_performance
    raw = await run_sync(get_sector_performance)
    out = []
    for d in (raw or []):
        name = (d.get("index") or d.get("sector") or d.get("name") or d.get("indexName") or "").strip()
        if not name:
            continue
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
async def universe_quotes(name: str, region: str = Query("IN")) -> List[UniverseRow]:
    if region == "US":
        from services.us_market_service import get_index_quotes as us_quotes
        try:
            raw = await run_sync(us_quotes, name)
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"US market fetch failed: {e}") from e
        out: List[UniverseRow] = []
        for d in (raw or []):
            out.append(UniverseRow(
                symbol=d.get("symbol") or "",
                company=d.get("name") or d.get("company") or d.get("shortName"),
                last_price=d.get("price") or d.get("last_price") or d.get("regularMarketPrice"),
                change_pct=d.get("change_pct") or d.get("regularMarketChangePercent"),
                open=d.get("open"),
                high=d.get("high"),
                low=d.get("low"),
                prev_close=d.get("prev_close"),
                week52_high=d.get("year_high") or d.get("week52_high"),
                week52_low=d.get("year_low") or d.get("week52_low"),
                volume=d.get("volume"),
            ))
        return out
    from services.nse_service import get_index_quotes
    try:
        raw = await run_sync(get_index_quotes, name)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"NSE fetch failed: {e}") from e

    if not raw:
        raw = await run_sync(_universe_yf_fallback, name)

    out = []
    for d in (raw or []):
        out.append(UniverseRow(
            symbol=d.get("symbol") or d.get("Symbol") or "",
            company=d.get("company") or d.get("companyName"),
            last_price=d.get("lastPrice") or d.get("last_price") or d.get("last") or d.get("price"),
            change_pct=d.get("pChange") or d.get("change_pct"),
            open=d.get("open"),
            high=d.get("dayHigh") or d.get("high"),
            low=d.get("dayLow") or d.get("low"),
            prev_close=d.get("previousClose") or d.get("prev_close"),
            week52_high=d.get("yearHigh") or d.get("week52_high") or d.get("year_high"),
            week52_low=d.get("yearLow") or d.get("week52_low") or d.get("year_low"),
            volume=d.get("totalTradedVolume") or d.get("volume"),
            return_30d=d.get("perChange30d") or d.get("return_30d"),
            return_1y=d.get("perChange365d") or d.get("return_1y"),
        ))
    return out
