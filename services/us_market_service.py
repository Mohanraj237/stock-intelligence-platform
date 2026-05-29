"""
US Market Service — Yahoo Finance based (authenticated session)

Uses a persistent session with Yahoo Finance cookie+crumb auth so the
v7/quote and v10/quoteSummary endpoints are accessible.

Auth flow (same as yfinance internals):
  1. GET https://fc.yahoo.com  → sets A3 cookie
  2. GET /v1/test/getcrumb     → returns crumb string
  3. Pass crumb= on all v7/v10 requests; session carries cookies

Falls back to v8/chart for single-symbol lookups (no auth needed).
"""
from __future__ import annotations
import logging
import time
import threading
from typing import Optional

import requests

logger = logging.getLogger(__name__)

_YF_BASE   = "https://query2.finance.yahoo.com"
_YF_BASE1  = "https://query1.finance.yahoo.com"
_AGENT     = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# ── Authenticated session (module-level singleton) ────────────────────────────

_SESSION: Optional[requests.Session] = None
_CRUMB:   Optional[str] = None
_CRUMB_AT: float = 0.0
_CRUMB_TTL_S = 55 * 60   # refresh crumb every 55 min
_LOCK = threading.Lock()


def _make_session() -> tuple[requests.Session, str]:
    """Create a fresh Yahoo Finance session and return (session, crumb)."""
    s = requests.Session()
    s.headers.update({
        "User-Agent": _AGENT,
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
    })
    try:
        s.get("https://fc.yahoo.com", timeout=10)
    except Exception:
        pass
    crumb_r = s.get(
        f"{_YF_BASE}/v1/test/getcrumb",
        timeout=10,
        headers={"Referer": "https://finance.yahoo.com/"},
    )
    crumb = crumb_r.text.strip() if crumb_r.status_code == 200 else ""
    if "{" in crumb:
        crumb = ""
    return s, crumb


def _get_session() -> tuple[requests.Session, str]:
    global _SESSION, _CRUMB, _CRUMB_AT
    with _LOCK:
        now = time.time()
        if _SESSION is None or not _CRUMB or (now - _CRUMB_AT) > _CRUMB_TTL_S:
            try:
                _SESSION, _CRUMB = _make_session()
                _CRUMB_AT = now
                logger.info("YF session refreshed, crumb=%s…", _CRUMB[:6] if _CRUMB else "NONE")
            except Exception as e:
                logger.warning("YF session init failed: %s", e)
                if _SESSION is None:
                    _SESSION = requests.Session()
                    _SESSION.headers["User-Agent"] = _AGENT
                _CRUMB = ""
        return _SESSION, _CRUMB


def _refresh_session() -> tuple[requests.Session, str]:
    global _SESSION, _CRUMB, _CRUMB_AT
    with _LOCK:
        try:
            _SESSION, _CRUMB = _make_session()
            _CRUMB_AT = time.time()
        except Exception as e:
            logger.warning("YF session refresh failed: %s", e)
    return _SESSION, _CRUMB


# ── Core fetch helpers ─────────────────────────────────────────────────────────

def _chart_single(symbol: str, period: str = "5d", interval: str = "1d") -> Optional[dict]:
    """Fetch chart meta for one symbol via v8/chart (no auth needed)."""
    s, _ = _get_session()
    url = f"{_YF_BASE}/v8/finance/chart/{symbol}"
    try:
        r = s.get(url, params={"interval": interval, "range": period}, timeout=12)
        if r.status_code == 200:
            results = r.json().get("chart", {}).get("result") or []
            return results[0].get("meta") if results else None
    except Exception as e:
        logger.debug("v8 chart %s failed: %s", symbol, e)
    return None


def _v7_quote(symbols: list[str], fields: str | None = None) -> list[dict]:
    """Bulk Yahoo Finance v7 quote (requires crumb)."""
    if not symbols:
        return []
    s, crumb = _get_session()
    default_fields = (
        "shortName,longName,regularMarketPrice,regularMarketChange,"
        "regularMarketChangePercent,regularMarketVolume,"
        "regularMarketOpen,regularMarketDayHigh,regularMarketDayLow,"
        "regularMarketPreviousClose,fiftyTwoWeekHigh,fiftyTwoWeekLow,"
        "marketCap,sector,industry,marketState,"
        "fiftyDayAverage,twoHundredDayAverage,"
        "trailingPE,priceToBook,trailingAnnualDividendYield"
    )
    results = []
    chunk_size = 100
    for i in range(0, len(symbols), chunk_size):
        batch = symbols[i : i + chunk_size]
        params = {
            "symbols": ",".join(batch),
            "fields": fields or default_fields,
            "crumb": crumb,
            "lang": "en-US",
        }
        try:
            r = s.get(f"{_YF_BASE}/v7/finance/quote", params=params, timeout=20)
            if r.status_code == 401:
                s, crumb = _refresh_session()
                params["crumb"] = crumb
                r = s.get(f"{_YF_BASE}/v7/finance/quote", params=params, timeout=20)
            if r.status_code == 200:
                results.extend(r.json().get("quoteResponse", {}).get("result") or [])
        except Exception as e:
            logger.warning("v7 quote batch failed: %s", e)
    return results


def _quotesummary(symbol: str) -> dict:
    """Fetch Yahoo Finance quoteSummary for fundamentals (requires crumb)."""
    s, crumb = _get_session()
    url = f"{_YF_BASE}/v10/finance/quoteSummary/{symbol.upper()}"
    params = {
        "modules": "financialData,defaultKeyStatistics,summaryDetail,assetProfile",
        "crumb": crumb,
    }
    try:
        r = s.get(url, params=params, timeout=15)
        if r.status_code == 401:
            s, crumb = _refresh_session()
            params["crumb"] = crumb
            r = s.get(url, params=params, timeout=15)
        if r.status_code == 200:
            result = (r.json().get("quoteSummary", {}).get("result") or [{}])[0]
            return result
    except Exception as e:
        logger.warning("quoteSummary %s failed: %s", symbol, e)
    return {}


# ── Normalise raw quote dicts ──────────────────────────────────────────────────

def _parse_v7(q: dict) -> dict:
    pct = q.get("regularMarketChangePercent")
    return {
        "symbol":       q.get("symbol", ""),
        "name":         q.get("shortName") or q.get("longName") or q.get("symbol", ""),
        "price":        q.get("regularMarketPrice"),
        "prev_close":   q.get("regularMarketPreviousClose"),
        "open":         q.get("regularMarketOpen"),
        "high":         q.get("regularMarketDayHigh"),
        "low":          q.get("regularMarketDayLow"),
        "change":       q.get("regularMarketChange"),
        "change_pct":   pct,
        "volume":       q.get("regularMarketVolume"),
        "year_high":    q.get("fiftyTwoWeekHigh"),
        "year_low":     q.get("fiftyTwoWeekLow"),
        "market_cap":   q.get("marketCap"),
        "sector":       q.get("sector", ""),
        "industry":     q.get("industry", ""),
        "pe":           q.get("trailingPE"),
        "pb":           q.get("priceToBook"),
        "div_yield":    q.get("trailingAnnualDividendYield"),
        "sma50":        q.get("fiftyDayAverage"),
        "sma200":       q.get("twoHundredDayAverage"),
        "market_state": q.get("marketState", ""),
        "source":       "Yahoo Finance",
    }


def _parse_chart_meta(m: dict, symbol: str = "") -> dict:
    """Parse v8 chart meta into the same shape as _parse_v7."""
    price = m.get("regularMarketPrice")
    prev  = m.get("chartPreviousClose")
    change = (price - prev) if (price and prev) else None
    pct    = (change / prev * 100) if (change is not None and prev) else None
    return {
        "symbol":       m.get("symbol") or symbol.upper(),
        "name":         m.get("shortName") or m.get("longName") or symbol.upper(),
        "price":        price,
        "prev_close":   prev,
        "open":         None,
        "high":         m.get("regularMarketDayHigh"),
        "low":          m.get("regularMarketDayLow"),
        "change":       change,
        "change_pct":   pct,
        "volume":       m.get("regularMarketVolume"),
        "year_high":    m.get("fiftyTwoWeekHigh"),
        "year_low":     m.get("fiftyTwoWeekLow"),
        "market_cap":   None,
        "sector":       "",
        "industry":     "",
        "pe":           None,
        "pb":           None,
        "div_yield":    None,
        "sma50":        None,
        "sma200":       None,
        "market_state": m.get("exchangeName", ""),
        "source":       "Yahoo Finance",
    }


# ── Public API ─────────────────────────────────────────────────────────────────

_INDEX_SYMBOLS = {
    "S&P 500":     "^GSPC",
    "NASDAQ 100":  "^NDX",
    "NASDAQ":      "^IXIC",
    "DOW 30":      "^DJI",
    "RUSSELL 2000": "^RUT",
    "VIX":         "^VIX",
}

_SECTOR_ETFS = {
    "XLK":  "Technology",
    "XLF":  "Financials",
    "XLV":  "Healthcare",
    "XLI":  "Industrials",
    "XLC":  "Communication",
    "XLY":  "Consumer Disc.",
    "XLP":  "Consumer Staples",
    "XLE":  "Energy",
    "XLU":  "Utilities",
    "XLRE": "Real Estate",
    "XLB":  "Materials",
}


def get_market_status() -> dict:
    """Return NYSE/NASDAQ market status using v8 chart on ^GSPC."""
    try:
        meta = _chart_single("^GSPC", period="5d")
        if not meta:
            return _fallback_market_status()
        price  = meta.get("regularMarketPrice")
        prev   = meta.get("chartPreviousClose")
        change = (price - prev) if (price and prev) else None
        pct    = (change / prev * 100) if (change is not None and prev) else None
        state  = meta.get("currentTradingPeriod", {}).get("regular", {})
        # Determine if market is open (epoch range)
        now_ts = int(time.time())
        is_open = False
        if state:
            is_open = (state.get("start", 0) <= now_ts <= state.get("end", 0))

        # Grab NASDAQ via chart too
        nasdaq_meta = _chart_single("^IXIC", period="5d")
        nasdaq_prev = nasdaq_meta.get("chartPreviousClose") if nasdaq_meta else None
        nasdaq_price = nasdaq_meta.get("regularMarketPrice") if nasdaq_meta else None
        nasdaq_pct   = ((nasdaq_price - nasdaq_prev) / nasdaq_prev * 100
                        if nasdaq_price and nasdaq_prev else None)

        return {
            "status":    "OPEN" if is_open else "CLOSED",
            "message":   f"NYSE/NASDAQ {'Open' if is_open else 'Closed'}",
            "market_state": "REGULAR" if is_open else "CLOSED",
            "sp500":     price,
            "change":    change,
            "pct":       pct,
            "nasdaq":    nasdaq_price,
            "nasdaq_pct": nasdaq_pct,
            "dow":       None,
            "dow_pct":   None,
            "vix":       None,
            "exchange":  "NYSE / NASDAQ",
        }
    except Exception as e:
        logger.warning("US market status failed: %s", e)
        return _fallback_market_status()


def _fallback_market_status() -> dict:
    import datetime
    utc_now = datetime.datetime.now(datetime.timezone.utc)
    month = utc_now.month
    offset = -4 if 3 <= month <= 11 else -5
    et_now = utc_now + datetime.timedelta(hours=offset)
    hour = et_now.hour + et_now.minute / 60
    is_open = (et_now.weekday() < 5) and (9.5 <= hour < 16.0)
    return {
        "status": "OPEN" if is_open else "CLOSED",
        "message": f"NYSE/NASDAQ {'Open' if is_open else 'Closed'} (estimated)",
        "market_state": "REGULAR" if is_open else "CLOSED",
        "sp500": None, "change": None, "pct": None,
        "exchange": "NYSE / NASDAQ",
    }


def get_quote(symbol: str) -> Optional[dict]:
    """Detailed quote for a single US symbol (v8 chart, no auth needed)."""
    meta = _chart_single(symbol.upper())
    if not meta:
        return None
    result = _parse_chart_meta(meta, symbol)
    # Try to enrich with sector/PE via v7 (best-effort)
    try:
        v7 = _v7_quote([symbol.upper()])
        if v7:
            enriched = _parse_v7(v7[0])
            result.update({k: v for k, v in enriched.items() if v is not None and result.get(k) is None})
    except Exception:
        pass
    return result


def get_bulk_quotes(symbols: list[str]) -> dict[str, dict]:
    """Bulk quote for multiple US symbols via v7 (crumb auth)."""
    raw = _v7_quote(symbols)
    if raw:
        return {q["symbol"]: _parse_v7(q) for q in raw if q.get("symbol")}
    # Fallback: v8 chart one-by-one (slow but always works)
    out: dict[str, dict] = {}
    for sym in symbols:
        try:
            meta = _chart_single(sym)
            if meta:
                out[sym.upper()] = _parse_chart_meta(meta, sym)
        except Exception:
            pass
    return out


def get_index_quotes(index_name: str) -> list[dict]:
    """Return all constituent stocks of a US index with live prices."""
    from services.us_universe_sync import get_us_universe_symbols
    symbols = get_us_universe_symbols(index_name)
    if not symbols:
        return []
    raw = _v7_quote(symbols)
    if raw:
        return [_parse_v7(q) for q in raw if q.get("symbol")]
    # v7 failed — fall back to v8 chart (much slower for large universes)
    out = []
    for sym in symbols[:50]:  # cap at 50 for performance
        try:
            meta = _chart_single(sym)
            if meta:
                out.append(_parse_chart_meta(meta, sym))
        except Exception:
            pass
    return out


def get_index_performance() -> list[dict]:
    """Fetch top-level performance for S&P 500, NASDAQ, DOW 30, Russell 2000."""
    syms = {"^GSPC": "S&P 500", "^NDX": "NASDAQ 100", "^DJI": "DOW 30", "^RUT": "RUSSELL 2000"}
    results = []
    for sym, name in syms.items():
        try:
            meta = _chart_single(sym, period="5d")
            if not meta:
                continue
            price = meta.get("regularMarketPrice")
            prev  = meta.get("chartPreviousClose")
            change = (price - prev) if price and prev else None
            pct    = (change / prev * 100) if change is not None and prev else None
            results.append({
                "index":  name,
                "symbol": sym,
                "last":   price,
                "change": change,
                "pct":    pct,
                "open":   None,
                "high":   meta.get("regularMarketDayHigh"),
                "low":    meta.get("regularMarketDayLow"),
            })
            time.sleep(0.2)  # small delay between chart calls
        except Exception as e:
            logger.debug("index perf %s: %s", sym, e)
    return results


def get_sector_performance() -> list[dict]:
    """Fetch SPDR sector ETF performance via v7 bulk quote."""
    etf_syms = list(_SECTOR_ETFS.keys())
    raw = _v7_quote(etf_syms)
    results = []
    if raw:
        for q in raw:
            sym = q.get("symbol", "")
            pct = q.get("regularMarketChangePercent")
            results.append({
                "sector":  _SECTOR_ETFS.get(sym, sym),
                "etf":     sym,
                "last":    q.get("regularMarketPrice"),
                "pct":     pct,
                "change":  q.get("regularMarketChange"),
                "volume":  q.get("regularMarketVolume"),
            })
    else:
        # Fallback: v8 chart each ETF
        for sym, sector_name in _SECTOR_ETFS.items():
            try:
                meta = _chart_single(sym)
                if meta:
                    price = meta.get("regularMarketPrice")
                    prev  = meta.get("chartPreviousClose")
                    pct   = ((price - prev) / prev * 100) if price and prev else None
                    results.append({
                        "sector": sector_name, "etf": sym,
                        "last": price, "pct": pct,
                        "change": (price - prev) if price and prev else None,
                        "volume": meta.get("regularMarketVolume"),
                    })
                time.sleep(0.15)
            except Exception:
                pass
    return results


def get_us_fundamentals(symbol: str) -> dict:
    """
    Fetch fundamental data for a US stock via v10/quoteSummary (crumb auth).
    Returns dict with nested 'ratios', 'sector', 'industry', 'description'.
    """
    clean = symbol.upper().strip()
    try:
        r = _quotesummary(clean)
        if not r:
            return {}

        def _v(d, key):
            val = d.get(key)
            return val.get("raw") if isinstance(val, dict) else val

        ks  = r.get("defaultKeyStatistics") or {}
        fd  = r.get("financialData") or {}
        sd  = r.get("summaryDetail") or {}
        ap  = r.get("assetProfile") or {}

        return {
            "ratios": {
                "pe":               _v(sd, "trailingPE"),
                "forward_pe":       _v(ks, "forwardPE"),
                "pb":               _v(ks, "priceToBook"),
                "ps":               _v(ks, "priceToSalesTrailing12Months"),
                "roe":              _v(fd, "returnOnEquity"),
                "roa":              _v(fd, "returnOnAssets"),
                "profit_margin":    _v(fd, "profitMargins"),
                "gross_margin":     _v(fd, "grossMargins"),
                "operating_margin": _v(fd, "operatingMargins"),
                "revenue_growth":   _v(fd, "revenueGrowth"),
                "earnings_growth":  _v(fd, "earningsGrowth"),
                "debt_equity":      _v(fd, "debtToEquity"),
                "current_ratio":    _v(fd, "currentRatio"),
                "free_cash_flow":   _v(fd, "freeCashflow"),
                "total_revenue":    _v(fd, "totalRevenue"),
                "ebitda":           _v(fd, "ebitda"),
                "target_high":      _v(fd, "targetHighPrice"),
                "target_low":       _v(fd, "targetLowPrice"),
                "target_mean":      _v(fd, "targetMeanPrice"),
                "recommendation":   fd.get("recommendationKey", ""),
                "analyst_count":    _v(fd, "numberOfAnalystOpinions"),
                "beta":             _v(ks, "beta"),
                "short_ratio":      _v(ks, "shortRatio"),
                "peg":              _v(ks, "pegRatio"),
                "eps":              _v(ks, "trailingEps"),
                "book_value":       _v(ks, "bookValue"),
                "shares_out":       _v(ks, "sharesOutstanding"),
                "float_shares":     _v(ks, "floatShares"),
                "insider_pct":      _v(ks, "heldPercentInsiders"),
                "institution_pct":  _v(ks, "heldPercentInstitutions"),
                "div_yield":        _v(sd, "dividendYield"),
                "payout_ratio":     _v(sd, "payoutRatio"),
            },
            "sector":      ap.get("sector", ""),
            "industry":    ap.get("industry", ""),
            "country":     ap.get("country", "US"),
            "employees":   ap.get("fullTimeEmployees"),
            "website":     ap.get("website", ""),
            "description": ap.get("longBusinessSummary", ""),
            "source":      "Yahoo Finance",
        }
    except Exception as e:
        logger.warning("US fundamentals failed for %s: %s", symbol, e)
        return {}


def get_us_peers(symbol: str) -> dict:
    """Return same-sector peers for a US stock using Yahoo Finance sector data."""
    clean = symbol.upper().strip()
    funda = get_us_fundamentals(clean)
    sector   = (funda.get("sector") or "").strip()
    industry = (funda.get("industry") or "").strip()

    try:
        from services.us_universe_sync import get_us_universe_symbols
        all_syms = get_us_universe_symbols("S&P 500") or []
    except Exception:
        all_syms = []

    candidates = [s for s in all_syms if s != clean][:80]
    if not sector or not candidates:
        return {"symbol": clean, "sector": sector or None,
                "industry": industry or None, "source": "us", "peers": []}

    raw_quotes = _v7_quote(candidates)
    peers = []
    for q in raw_quotes:
        if q.get("sector", "") == sector and q.get("symbol") != clean:
            pct = q.get("regularMarketChangePercent")
            peers.append({
                "symbol":     q.get("symbol", ""),
                "company":    q.get("shortName") or q.get("longName") or q.get("symbol", ""),
                "last_price": q.get("regularMarketPrice"),
                "change_pct": pct,
                "market_cap": q.get("marketCap"),
                "pe":         q.get("trailingPE"),
                "sector":     sector,
            })
        if len(peers) >= 12:
            break

    return {
        "symbol":   clean,
        "sector":   sector or None,
        "industry": industry or None,
        "source":   "us_yahoo",
        "peers":    peers,
    }
