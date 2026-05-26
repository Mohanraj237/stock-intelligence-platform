from __future__ import annotations
import time
import logging
import threading
import urllib.parse
from typing import Any, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests

logger = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com",
    "Connection": "keep-alive",
}

# NSE API index name map  (internal name → NSE API param)
NSE_INDEX_MAP = {
    "NIFTY 50":          "NIFTY 50",
    "NIFTY NEXT 50":     "NIFTY NEXT 50",
    "NIFTY 100":         "NIFTY 100",
    "NIFTY 200":         "NIFTY 200",
    "NIFTY 500":         "NIFTY 500",
    "NIFTY MIDCAP 50":   "NIFTY MIDCAP 50",
    "NIFTY MIDCAP 100":  "NIFTY MIDCAP 100",
    "NIFTY MIDCAP 150":  "NIFTY MIDCAP 150",
    "NIFTY MIDCAP SELECT": "NIFTY MIDCAP SELECT",
    "NIFTY SMALLCAP 50":  "NIFTY SMALLCAP 50",
    "NIFTY SMALLCAP 100": "NIFTY SMALLCAP 100",
    "NIFTY SMALLCAP 250": "NIFTY SMALLCAP 250",
    "NIFTY BANK":        "NIFTY BANK",
    "NIFTY IT":          "NIFTY IT",
    "NIFTY PHARMA":      "NIFTY PHARMA",
    "NIFTY AUTO":        "NIFTY AUTO",
    "NIFTY FMCG":        "NIFTY FMCG",
    "NIFTY METAL":       "NIFTY METAL",
    "NIFTY ENERGY":      "NIFTY ENERGY",
    "NIFTY PSU BANK":    "NIFTY PSU BANK",
    "NIFTY REALTY":      "NIFTY REALTY",
    "NIFTY MEDIA":       "NIFTY MEDIA",
    "NIFTY INFRA":       "NIFTY INFRA",
    "NIFTY CONSUMPTION": "NIFTY INDIA CONSUMPTION",
    "NIFTY MNC":         "NIFTY MNC",
}

_SESSION: Optional[requests.Session] = None
_SESSION_TS: float = 0
_SESSION_TTL = 300  # refresh session every 5 min
_SESSION_LOCK = threading.Lock()


def _get_session() -> requests.Session:
    global _SESSION, _SESSION_TS
    with _SESSION_LOCK:
        if _SESSION is None or (time.time() - _SESSION_TS) > _SESSION_TTL:
            sess = requests.Session()
            sess.headers.update(_HEADERS)
            try:
                sess.get("https://www.nseindia.com", timeout=8)
            except Exception:
                pass
            _SESSION = sess
            _SESSION_TS = time.time()
        return _SESSION


def _api_get(path: str, params: dict = None, timeout: int = 15) -> Optional[Any]:
    sess = _get_session()
    url = f"https://www.nseindia.com{path}"
    try:
        resp = sess.get(url, params=params, timeout=timeout)
        if resp.status_code == 200:
            return resp.json()
        logger.warning(f"NSE API {path} → {resp.status_code}")
    except Exception as e:
        logger.warning(f"NSE API {path} failed: {e}")
    return None


def get_market_status() -> dict:
    """Return current market open/close status."""
    data = _api_get("/api/marketStatus")
    if not data:
        return {"status": "unknown", "nifty": None, "change": None, "pct": None}
    states = data.get("marketState", [])
    cap = data.get("marketcap", {})
    nifty_state = next((s for s in states if s.get("market") == "Capital Market"), {})
    indicative = data.get("indicativenifty50", {})
    return {
        "status": nifty_state.get("marketStatus", "unknown"),
        "message": nifty_state.get("marketStatusMessage", ""),
        "trade_date": nifty_state.get("tradeDate", ""),
        "nifty": nifty_state.get("last"),
        "change": nifty_state.get("variation"),
        "pct": nifty_state.get("percentChange"),
        "market_cap_lakh_cr": cap.get("marketCapinLACCRRupees"),
        "gift_nifty": data.get("giftnifty", {}).get("LASTPRICE"),
        "gift_nifty_change_pct": data.get("giftnifty", {}).get("PERCHANGE"),
    }


def get_index_quotes(index_name: str) -> list[dict]:
    """
    Return all constituent stocks of a NSE index with live prices.
    One API call → entire index. Returns list of stock dicts.
    """
    api_name = NSE_INDEX_MAP.get(index_name, index_name)
    data = _api_get("/api/equity-stockIndices", {"index": api_name})
    if not data:
        return []

    stocks = []
    for item in data.get("data", []):
        sym = item.get("symbol", "")
        # Skip the index row itself (e.g. "NIFTY 50" appears as first row)
        if not sym or sym.startswith("NIFTY") or sym.startswith("SENSEX"):
            continue
        stocks.append({
            "symbol": sym,
            "name": item.get("identifier", sym),
            "price": item.get("lastPrice"),
            "prev_close": item.get("previousClose"),
            "open": item.get("open"),
            "high": item.get("dayHigh"),
            "low": item.get("dayLow"),
            "change": item.get("change"),
            "change_pct": item.get("pChange"),
            "volume": item.get("totalTradedVolume"),
            "turnover": item.get("totalTradedValue"),
            "year_high": item.get("yearHigh"),
            "year_low": item.get("yearLow"),
            "near_52w_high": item.get("nearWKH"),
            "near_52w_low": item.get("nearWKL"),
            "return_30d": item.get("perChange30d"),
            "return_365d": item.get("perChange365d"),
            "ffmc": item.get("ffmc"),
            "last_update": item.get("lastUpdateTime"),
            "source": "NSE India",
        })
    return stocks


def get_quote(symbol: str) -> Optional[dict]:
    """Fetch detailed quote for a single NSE symbol."""
    clean = symbol.upper().strip().replace(".NS", "").replace("-EQ", "")
    data = _api_get("/api/quote-equity", {"symbol": clean})
    if not data:
        return None

    price_info = data.get("priceInfo", {})
    info = data.get("info", {})
    industry_info = data.get("industryInfo", {})
    sec_info = data.get("securityInfo", {})
    metadata = data.get("metadata", {})

    intrinsic = price_info.get("intrinsicValue")
    close = price_info.get("lastPrice") or price_info.get("close")
    prev = price_info.get("previousClose")

    return {
        "symbol": clean,
        "name": info.get("companyName", ""),
        "isin": info.get("isin", ""),
        "industry": industry_info.get("basicIndustry", ""),
        "sector": industry_info.get("sector", ""),
        "macro": industry_info.get("macroSector", ""),
        "price": close,
        "prev_close": prev,
        "open": price_info.get("open"),
        "high": price_info.get("intraDayHighLow", {}).get("max"),
        "low": price_info.get("intraDayHighLow", {}).get("min"),
        "change": price_info.get("change"),
        "change_pct": price_info.get("pChange"),
        "year_high": price_info.get("weekHighLow", {}).get("max"),
        "year_low": price_info.get("weekHighLow", {}).get("min"),
        "vwap": price_info.get("vwap"),
        "lower_circuit": price_info.get("lowerCP"),
        "upper_circuit": price_info.get("upperCP"),
        "face_value": sec_info.get("faceValue"),
        "issued_size": sec_info.get("issuedSize"),
        "market_lot": sec_info.get("tradingStatus"),
        "listing_date": metadata.get("listingDate"),
        "source": "NSE India",
        "fetched_at": time.time(),
    }


def get_bulk_quotes(symbols: list[str], max_workers: int = 10) -> dict[str, dict]:
    """Parallel quote fetch for multiple symbols."""
    results = {}
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(get_quote, sym): sym for sym in symbols}
        for future in as_completed(futures):
            sym = futures[future]
            try:
                data = future.result()
                if data:
                    results[sym] = data
            except Exception as e:
                logger.debug(f"NSE quote failed {sym}: {e}")
    return results


def _safe_pct(metadata: dict) -> Optional[float]:
    """Compute percentChange — fall back to change/previousClose when NSE returns None/missing."""
    pct = metadata.get("percentChange")
    if pct is not None:
        try:
            return float(pct)
        except Exception:
            pass
    chg = metadata.get("change")
    last = metadata.get("last")
    try:
        chg_f, last_f = float(chg), float(last)
        prev = last_f - chg_f
        if prev > 0:
            return chg_f / prev * 100
    except Exception:
        pass
    return None


def get_index_performance() -> list[dict]:
    """Fetch top-level performance of major indices from market status."""
    indices = ["NIFTY 50", "NIFTY BANK", "NIFTY IT", "NIFTY PHARMA",
               "NIFTY MIDCAP 150", "NIFTY SMALLCAP 250"]
    results = []
    for idx in indices:
        api_name = NSE_INDEX_MAP.get(idx, idx)
        data = _api_get("/api/equity-stockIndices", {"index": api_name})
        if data:
            metadata = data.get("metadata", {})
            results.append({
                "index": idx,
                "last": metadata.get("last"),
                "change": metadata.get("change"),
                "pct": _safe_pct(metadata),
                "open": metadata.get("open"),
                "high": metadata.get("high"),
                "low": metadata.get("low"),
                "timestamp": data.get("timestamp"),
            })
    return results


def get_sector_performance() -> list[dict]:
    """Fetch performance of all major sector indices."""
    sector_indices = [
        "NIFTY BANK", "NIFTY IT", "NIFTY PHARMA", "NIFTY AUTO",
        "NIFTY FMCG", "NIFTY METAL", "NIFTY ENERGY", "NIFTY PSU BANK",
        "NIFTY REALTY", "NIFTY MEDIA", "NIFTY INFRA",
    ]
    results = []
    for idx in sector_indices:
        api_name = NSE_INDEX_MAP.get(idx, idx)
        data = _api_get("/api/equity-stockIndices", {"index": api_name})
        if data:
            meta = data.get("metadata", {})
            stocks = data.get("data", [])
            adv = sum(1 for s in stocks if (s.get("pChange") or 0) > 0)
            dec = sum(1 for s in stocks if (s.get("pChange") or 0) < 0)
            results.append({
                "sector": idx.replace("NIFTY ", ""),
                "index": idx,
                "last": meta.get("last"),
                "pct": _safe_pct(meta),
                "change": meta.get("change"),
                "advancing": adv,
                "declining": dec,
                "stocks": len(stocks),
            })
    return results


def _coerce_num(v) -> Optional[float]:
    if v is None:
        return None
    try:
        if isinstance(v, str):
            v = v.replace(",", "").replace("Cr", "").replace("Rs", "").strip()
            if not v or v in ("-", "—"):
                return None
        return float(v)
    except Exception:
        return None


def get_fii_dii_data() -> list[dict]:
    """
    Fetch recent FII/DII cash-segment activity from NSE.

    NSE returns one row per category per date:
      [{"category":"DII","date":"24-Apr-2026","buyValue":"x","sellValue":"y","netValue":"z"},
       {"category":"FII/FPI","date":"24-Apr-2026", ...}]

    We group by date and merge into one dict per date.
    """
    data = _api_get("/api/fiidiiTradeReact")
    if not data:
        return []
    items = data if isinstance(data, list) else (data.get("data") if isinstance(data, dict) else [])
    if not items:
        return []

    # Group by date
    by_date: dict = {}
    for it in items:
        d = it.get("date") or it.get("reportDate") or ""
        cat = (it.get("category") or "").upper()
        bv = _coerce_num(it.get("buyValue"))
        sv = _coerce_num(it.get("sellValue"))
        nv = _coerce_num(it.get("netValue"))
        row = by_date.setdefault(d, {"date": d,
                                      "fii_buy": None, "fii_sell": None, "fii_net": None,
                                      "dii_buy": None, "dii_sell": None, "dii_net": None})
        if "FII" in cat or "FPI" in cat:
            row["fii_buy"]  = bv
            row["fii_sell"] = sv
            row["fii_net"]  = nv
        elif "DII" in cat:
            row["dii_buy"]  = bv
            row["dii_sell"] = sv
            row["dii_net"]  = nv

    # Sort newest first (date string format DD-MMM-YYYY)
    from datetime import datetime as _dt
    def _key(r):
        try:
            return _dt.strptime(r["date"], "%d-%b-%Y")
        except Exception:
            return _dt.min
    return sorted(by_date.values(), key=_key, reverse=True)
