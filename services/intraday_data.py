"""
Market data fetcher for the F&O Live Scanner.

Uses the Yahoo Finance REST API directly with a fresh requests.Session() per
call — the exact same approach as market_data_service.get_ohlcv_history(),
which works reliably for the equity scanner without rate limiting.

The yfinance *library* was problematic because it reuses a shared persistent
session across concurrent workers, causing Yahoo Finance to flag the traffic.
A fresh Session per request avoids that entirely.
"""
from __future__ import annotations

import logging
import threading
import time as _time
from typing import Optional

import pandas as pd
import requests as _req

log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Yahoo Finance REST config
# ─────────────────────────────────────────────────────────────────────────────

# Both endpoints serve the same data; query2 is a fallback when query1 returns 404
_YF_BASES = [
    "https://query1.finance.yahoo.com/v8/finance/chart",
    "https://query2.finance.yahoo.com/v8/finance/chart",
]
_YF_HDRS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}

# Lookback range per interval — enough bars for EMA-50 warmup + pattern detection
_YF_RANGE: dict[str, str] = {
    "1m":  "1d",
    "5m":  "5d",
    "15m": "15d",
    "30m": "20d",
    "1h":  "60d",
    "4h":  "200d",
    "1d":  "1y",
    "1wk": "5y",
    "1mo": "5y",   # ~60 monthly bars — enough for EMA-50 warmup
}

# NSE/BSE symbol → Yahoo Finance ticker
# All tickers confirmed working as of 2026-06-09 (WS-4 verification)
_INDEX_MAP: dict[str, str] = {
    # NSE/BSE indices (India)
    "NIFTY":      "^NSEI",
    "BANKNIFTY":  "^NSEBANK",
    "FINNIFTY":   "NIFTY_FIN_SERVICE.NS",
    "SENSEX":     "^BSESN",
    "MIDCPNIFTY": "NIFTY_MID_SELECT.NS",
    "BANKEX":     "BSE-BANK.BO",
    "INDIAVIX":   "^INDIAVIX",
    # US major indices
    "SP500":      "^GSPC",    # S&P 500
    "NASDAQ100":  "^NDX",     # NASDAQ 100
    "DOW":        "^DJI",     # Dow Jones Industrial Average
    "RUSSELL2000":"^RUT",     # Russell 2000 (small-cap)
    "NASDAQ":     "^IXIC",    # NASDAQ Composite
}

# Equity symbols whose YF ticker does not follow the {SYMBOL}.NS convention
# Key = NSE symbol (as used in the platform), Value = Yahoo Finance ticker
_EQUITY_TICKER_OVERRIDE: dict[str, str] = {
    "TATAMOTORS": "TMCV.NS",    # Tata Motors Ltd — YF uses TMCV.NS (WS-4)
    "ETERNAL":    "ETERNAL.NS", # formerly ZOMATO; company renamed to Eternal Ltd 2025
}

# ─────────────────────────────────────────────────────────────────────────────
# US equity universes
# Tickers are passed as-is to Yahoo Finance (no .NS suffix)
# ─────────────────────────────────────────────────────────────────────────────

# Top 30 US stocks by market cap (2026)
_US_EQUITY_TOP30: list[str] = [
    "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN",
    "META", "TSLA", "AVGO", "JPM", "WMT",
    "LLY",  "ORCL", "V",    "UNH",  "XOM",
    "MA",   "HD",   "PG",   "COST", "JNJ",
    "BAC",  "ABBV", "KO",   "NFLX", "AMD",
    "PM",   "CRM",  "GE",   "ADBE", "MCD",
]

# Top US technology stocks
_US_EQUITY_TECH: list[str] = [
    "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META",
    "TSLA", "AVGO", "ORCL", "AMD",   "ADBE", "CRM",
    "INTC", "QCOM", "TXN",  "MU",    "AMAT", "PANW",
    "CRWD", "SNOW", "PLTR", "INTU",  "NOW",  "FTNT",
    "DDOG", "ZS",   "TEAM", "SHOP",
]

# US indices — symbol names mapped in _INDEX_MAP above
_US_INDICES: list[str] = ["SP500", "NASDAQ100", "DOW", "RUSSELL2000"]

# All US tickers — eagerly loads every US universe JSON at import time so
# _ticker() never appends .NS to any symbol fetched from a US file.
#
# The glob is US_*.json **plus** ALL_US_LISTED.json: the latter does not match
# the US_ prefix, so a symbol living only in that file used to be resolved as
# {SYMBOL}.NS and silently fail to fetch.
_US_UNIVERSE_GLOBS: tuple[str, ...] = ("US_*.json", "ALL_US_LISTED.json")


def _build_us_symbols() -> frozenset[str]:
    import json as _json
    from pathlib import Path as _Path
    base = _Path(__file__).resolve().parent.parent / "storage" / "universe"
    syms: set[str] = set(_US_EQUITY_TOP30 + _US_EQUITY_TECH + _US_INDICES)
    seen: set[_Path] = set()
    for pattern in _US_UNIVERSE_GLOBS:
        for f in base.glob(pattern):
            if f in seen:
                continue
            seen.add(f)
            try:
                data = _json.loads(f.read_text(encoding="utf-8"))
                syms.update(s.strip().upper() for s in data.get("symbols", []) if isinstance(s, str) and s.strip())
            except Exception:
                pass
    return frozenset(syms)

_ALL_US_SYMBOLS: frozenset[str] = _build_us_symbols()


def is_us_symbol(symbol: str) -> bool:
    """True when the symbol resolves to a US ticker (no .NS suffix)."""
    return symbol.upper() in _ALL_US_SYMBOLS


def exchange_tz(symbol: str) -> str:
    """
    IANA timezone of the exchange the symbol trades on. Used to group intraday
    bars into sessions — grouping a US session by IST calendar date splits it
    across IST midnight.
    """
    return "America/New_York" if is_us_symbol(symbol) else "Asia/Kolkata"


def assert_no_us_symbol_maps_to_ns(symbols: list[str]) -> list[str]:
    """
    Startup guard: no symbol from a US universe may resolve to a `.NS` ticker.
    Returns the offending symbols (empty when healthy).
    """
    return [s for s in symbols if _ticker(s).endswith(".NS")]

# ─────────────────────────────────────────────────────────────────────────────
# India equity universes
# ─────────────────────────────────────────────────────────────────────────────

_INDIA_NIFTY50: list[str] = [
    "ADANIENT",   "ADANIPORTS",  "APOLLOHOSP",  "ASIANPAINT",  "AXISBANK",
    "BAJAJ-AUTO", "BAJFINANCE",  "BAJAJFINSV",  "BEL",         "BHARTIARTL",
    "CIPLA",      "COALINDIA",   "DIVISLAB",    "DRREDDY",     "EICHERMOT",
    "ETERNAL",    "GRASIM",      "HCLTECH",     "HDFCBANK",    "HDFCLIFE",
    "HINDALCO",   "HINDUNILVR",  "ICICIBANK",   "INDUSINDBK",  "INFY",
    "ITC",        "JIOFIN",      "JSWSTEEL",    "KOTAKBANK",   "LT",
    "M&M",        "MARUTI",      "NESTLEIND",   "NTPC",        "ONGC",
    "POWERGRID",  "RELIANCE",    "SBILIFE",     "SBIN",        "SHRIRAMFIN",
    "SUNPHARMA",  "TATAMOTORS",  "TATACONSUM",  "TATASTEEL",   "TCS",
    "TECHM",      "TITAN",       "TRENT",       "ULTRACEMCO",  "WIPRO",
]

# Nifty Next 50 — combines with Nifty 50 to form Nifty 100
_INDIA_NIFTY_NEXT50: list[str] = [
    "ABB",        "AMBUJACEM",   "ATGL",        "BERGEPAINT",  "BOSCHLTD",
    "CGPOWER",    "CHOLAFIN",    "CUMMINSIND",  "DLF",         "GODREJCP",
    "HDFCAMC",    "HAL",         "HYUNDAI",     "INDHOTEL",    "INDIGO",
    "IOC",        "IRFC",        "JINDALSTEL",  "LODHA",       "MAXHEALTH",
    "MAZDOCK",    "MUTHOOTFIN",  "NAUKRI",      "PERSISTENT",  "PIDILITIND",
    "PFC",        "PNB",         "RECLTD",      "MOTHERSON",   "SHREECEM",
    "SIEMENS",    "SOLARINDS",   "TATACAP",     "TATAPOWER",   "TORNTPHARM",
    "TVSMOTOR",   "UNIONBANK",   "VBL",         "VEDL",        "ZYDUSLIFE",
    "ADANIENSOL", "ADANIGREEN",  "ADANIPOWER",  "BANKBARODA",  "COLPAL",
    "DABUR",      "HINDPETRO",   "PIIND",       "UNITDSPR",    "ASTRAL",
]


def _load_universe_json(filename: str) -> list[str]:
    """Load symbol list from storage/universe/{filename}. Returns [] on any error."""
    import json
    from pathlib import Path
    try:
        p = Path(__file__).resolve().parent.parent / "storage" / "universe" / filename
        data = json.loads(p.read_text(encoding="utf-8"))
        return [s.strip() for s in data.get("symbols", []) if isinstance(s, str) and s.strip()]
    except Exception as exc:
        log.debug("Failed to load universe %s: %s", filename, exc)
        return []


def get_india_nifty200() -> list[str]:
    """Load Nifty 200 from JSON; fallback to Nifty 100 on error."""
    syms = _load_universe_json("NIFTY_200.json")
    return syms if len(syms) >= 100 else (_INDIA_NIFTY50 + _INDIA_NIFTY_NEXT50)


def get_us_sp100() -> list[str]:
    """First 100 symbols from S&P 500 JSON; fallback to top-30."""
    syms = _load_universe_json("US_SANDP_500.json")
    return syms[:100] if len(syms) >= 50 else _US_EQUITY_TOP30


# ── India broader & sector universes ──────────────────────────────────────────

def get_india_nifty500() -> list[str]:
    syms = _load_universe_json("NIFTY_500.json")
    return syms if len(syms) >= 100 else get_india_nifty200()

def get_india_midcap150() -> list[str]:
    return _load_universe_json("NIFTY_MIDCAP_150.json") or get_india_nifty200()

def get_india_smallcap250() -> list[str]:
    return _load_universe_json("NIFTY_SMALLCAP_250.json") or get_india_nifty200()

def get_india_sector(filename: str) -> list[str]:
    return _load_universe_json(filename)

# Sector shorthands
def get_india_bank()     -> list[str]: return _load_universe_json("NIFTY_BANK.json")
def get_india_it()       -> list[str]: return _load_universe_json("NIFTY_IT.json")
def get_india_pharma()   -> list[str]: return _load_universe_json("NIFTY_PHARMA.json")
def get_india_auto()     -> list[str]: return _load_universe_json("NIFTY_AUTO.json")
def get_india_fmcg()     -> list[str]: return _load_universe_json("NIFTY_FMCG.json")
def get_india_metal()    -> list[str]: return _load_universe_json("NIFTY_METAL.json")
def get_india_energy()   -> list[str]: return _load_universe_json("NIFTY_ENERGY.json")
def get_india_infra()    -> list[str]: return _load_universe_json("NIFTY_INFRA.json")
def get_india_realty()   -> list[str]: return _load_universe_json("NIFTY_REALTY.json")
def get_india_media()    -> list[str]: return _load_universe_json("NIFTY_MEDIA.json")
def get_india_psu_bank() -> list[str]: return _load_universe_json("NIFTY_PSU_BANK.json")

# ── US broader & sector universes ─────────────────────────────────────────────

def get_us_nasdaq100() -> list[str]:
    syms = _load_universe_json("US_NASDAQ_100.json")
    return syms if len(syms) >= 50 else _US_EQUITY_TECH

def get_us_dow30() -> list[str]:
    syms = _load_universe_json("US_DOW_30.json")
    return syms if len(syms) >= 20 else _US_EQUITY_TOP30[:30]

def get_us_sp500() -> list[str]:
    syms = _load_universe_json("US_SANDP_500.json")
    return syms if len(syms) >= 100 else get_us_sp100()


def _save_universe_json(filename: str, name: str, symbols: list[str]) -> None:
    """Write symbol list to storage/universe/{filename}."""
    import json as _json
    from pathlib import Path as _Path
    try:
        p = _Path(__file__).resolve().parent.parent / "storage" / "universe" / filename
        data = {
            "name": name,
            "symbols": symbols,
            "count": len(symbols),
            "synced_at": _time.time(),
            "fallback": False,
        }
        p.write_text(_json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        log.info("Saved %d symbols → %s", len(symbols), filename)
    except Exception as exc:
        log.warning("Failed to save %s: %s", filename, exc)


_KITE_INSTRUMENTS_URL = "https://api.kite.trade/instruments"


def _fetch_nse_equity_list_from_kite() -> list[str]:
    """
    Zerodha Kite Connect's public instrument master — a free, no-API-key CSV
    dump of every tradeable instrument across exchanges (~120k rows). Used as
    the primary source for the full NSE equity list since NSE's own archive
    endpoints (archives.nseindia.com) return 403/503 from this environment.

    Filters the raw NSE/EQ rows down to main-board equity shares that are
    actually fetchable from Yahoo Finance (this app's only OHLCV source):
      - drops symbols starting with a digit (state dev. loans / T-bills, e.g. "656KA30-SG")
      - drops any "-SUFFIX" series marker (SME/BE/ST/T2T/etc.) — Yahoo doesn't
        resolve these hyphenated NSE series tickers (verified empirically: 0/20
        sampled suffixed symbols returned data), so keeping them would only
        waste a fetch attempt on every scan
      - drops "...INAV" symbols (ETF Indicative NAV quotes, not real stocks)
    Lands close to NSE's own ~2,300 main-board count.
    """
    from io import StringIO

    resp = _req.get(_KITE_INSTRUMENTS_URL, timeout=30, headers=_YF_HDRS)
    resp.raise_for_status()
    df = pd.read_csv(StringIO(resp.text))
    eq = df[(df["exchange"] == "NSE") & (df["segment"] == "NSE") & (df["instrument_type"] == "EQ")]
    sym = eq["tradingsymbol"].astype(str)
    eq = eq[~sym.str.match(r"^\d") & ~sym.str.contains("-", regex=False) & ~sym.str.endswith("INAV")]
    return sorted({s.strip().upper() for s in eq["tradingsymbol"].tolist() if isinstance(s, str) and s.strip()})


def get_all_nse() -> list[str]:
    """
    All NSE main-board equity stocks (~2300-2400).
    Priority: ALL_NSE.json (if populated) → Kite instrument master → nselib equity_list → merged NIFTY/sector JSONs.
    """
    # 1. Pre-populated JSON
    syms = _load_universe_json("ALL_NSE.json")
    if len(syms) >= 100:
        return syms

    # 2. Live fetch via Zerodha Kite's public instrument master
    try:
        fetched = _fetch_nse_equity_list_from_kite()
        if len(fetched) >= 1000:
            _save_universe_json("ALL_NSE.json", "ALL NSE", fetched)
            return fetched
    except Exception as exc:
        log.debug("Kite instruments fetch failed: %s", exc)

    # 3. Live fetch via nselib
    try:
        from nselib.capital_market import equity_list as _nse_equity_list
        df = _nse_equity_list()
        if df is not None and not df.empty:
            col = next((c for c in df.columns if c.lower() in ("symbol", "symt")), None)
            if col:
                fetched = sorted({s.strip() for s in df[col].tolist() if isinstance(s, str) and s.strip()})
                if len(fetched) >= 100:
                    _save_universe_json("ALL_NSE.json", "ALL NSE", fetched)
                    return fetched
    except Exception as exc:
        log.debug("nselib equity_list failed: %s", exc)

    # 4. Fallback: merge all available India JSON files (dedup)
    all_syms: set[str] = set()
    for fname in [
        "NIFTY_500.json", "NIFTY_MIDCAP_150.json", "NIFTY_SMALLCAP_250.json",
        "NIFTY_50.json", "NIFTY_NEXT_50.json",
        "NIFTY_BANK.json", "NIFTY_IT.json", "NIFTY_PHARMA.json", "NIFTY_AUTO.json",
        "NIFTY_FMCG.json", "NIFTY_METAL.json", "NIFTY_ENERGY.json", "NIFTY_INFRA.json",
        "NIFTY_REALTY.json", "NIFTY_PSU_BANK.json", "NIFTY_MEDIA.json",
    ]:
        all_syms.update(_load_universe_json(fname))
    return sorted(all_syms)


def refresh_all_nse() -> list[str]:
    """Force re-fetch (bypassing the cached JSON) and write to ALL_NSE.json. Returns updated list."""
    try:
        fetched = _fetch_nse_equity_list_from_kite()
        if len(fetched) >= 1000:
            _save_universe_json("ALL_NSE.json", "ALL NSE", fetched)
            return fetched
    except Exception as exc:
        log.warning("Kite instruments refresh failed: %s", exc)

    try:
        from nselib.capital_market import equity_list as _nse_equity_list
        df = _nse_equity_list()
        if df is not None and not df.empty:
            col = next((c for c in df.columns if c.lower() in ("symbol", "symt")), None)
            if col:
                fetched = sorted({s.strip() for s in df[col].tolist() if isinstance(s, str) and s.strip()})
                if len(fetched) >= 100:
                    _save_universe_json("ALL_NSE.json", "ALL NSE", fetched)
                    return fetched
    except Exception as exc:
        log.warning("nselib refresh failed: %s", exc)
    return get_all_nse()


def get_all_us_listed() -> list[str]:
    """
    Comprehensive US stock list (~600 unique).
    Merges S&P 500 + NASDAQ 100 + DOW 30 + all US sector files, deduplicated.
    """
    all_syms: set[str] = set()
    for fname in [
        "US_SANDP_500.json", "US_NASDAQ_100.json", "US_DOW_30.json",
        "US_US_TECHNOLOGY.json", "US_US_FINANCIALS.json", "US_US_HEALTHCARE.json",
        "US_US_ENERGY.json", "US_US_CONSUMER_DISC.json", "US_US_COMMUNICATION.json",
        "US_US_INDUSTRIALS.json", "US_US_CONSUMER_STAPLES.json",
    ]:
        all_syms.update(_load_universe_json(fname))
    # Also include hardcoded top30 in case JSON is partially missing
    all_syms.update(_US_EQUITY_TOP30)
    return sorted(all_syms)

# US sector shorthands
def get_us_technology()       -> list[str]: return _load_universe_json("US_US_TECHNOLOGY.json")
def get_us_financials()       -> list[str]: return _load_universe_json("US_US_FINANCIALS.json")
def get_us_healthcare()       -> list[str]: return _load_universe_json("US_US_HEALTHCARE.json")
def get_us_energy_sector()    -> list[str]: return _load_universe_json("US_US_ENERGY.json")
def get_us_consumer_disc()    -> list[str]: return _load_universe_json("US_US_CONSUMER_DISC.json")
def get_us_communication()    -> list[str]: return _load_universe_json("US_US_COMMUNICATION.json")
def get_us_industrials()      -> list[str]: return _load_universe_json("US_US_INDUSTRIALS.json")
def get_us_consumer_staples() -> list[str]: return _load_universe_json("US_US_CONSUMER_STAPLES.json")


def _ticker(symbol: str) -> str:
    s = symbol.upper()
    # Index symbols have explicit YF ticker mappings
    if s in _INDEX_MAP:
        return _INDEX_MAP[s]
    # Equity symbols with non-standard YF tickers
    if s in _EQUITY_TICKER_OVERRIDE:
        return _EQUITY_TICKER_OVERRIDE[s]
    # US equities — use ticker as-is (no .NS suffix)
    if s in _ALL_US_SYMBOLS:
        return s
    # Default: append .NS for NSE equities
    return f"{s}.NS"


# ─────────────────────────────────────────────────────────────────────────────
# Bar cache
#
# Every scan used to re-fetch every symbol/timeframe from Yahoo. A 503-symbol
# S&P 500 scan across 3 timeframes is ~1,500 HTTP requests. The cache is keyed
# on (symbol, interval, range) and holds the *fetched frame*, never a score, so
# a cache hit and a live fetch produce identical results.
# ─────────────────────────────────────────────────────────────────────────────

# TTL in seconds per interval.
_CACHE_TTL: dict[str, float] = {
    "1m":   60,
    "5m":   60,
    "15m":  60,
    "30m":  300,
    "1h":   300,
    "4h":   900,
    "1d":   900,      # during market hours; outside them → until the next open
    "1wk":  6 * 3600,
    "1mo":  6 * 3600,
}
_DEFAULT_TTL = 900.0

_bar_cache: dict[tuple[str, str, str], tuple[float, pd.DataFrame]] = {}
_bar_cache_lock = threading.Lock()
_cache_stats = {"hits": 0, "misses": 0}


def _ist_now() -> pd.Timestamp:
    return pd.Timestamp.now(tz="Asia/Kolkata")


def _market_is_open_ist(now: pd.Timestamp | None = None) -> bool:
    """NSE cash session, 09:15–15:30 IST, Mon–Fri. Holidays are not modelled."""
    now = now or _ist_now()
    if now.weekday() >= 5:
        return False
    minutes = now.hour * 60 + now.minute
    return 9 * 60 + 15 <= minutes < 15 * 60 + 30


def _seconds_until_next_open(now: pd.Timestamp | None = None) -> float:
    """Seconds from `now` to the next 09:15 IST weekday open."""
    now = now or _ist_now()
    nxt = now.normalize() + pd.Timedelta(hours=9, minutes=15)
    if nxt <= now:
        nxt += pd.Timedelta(days=1)
    while nxt.weekday() >= 5:
        nxt += pd.Timedelta(days=1)
    return max(60.0, (nxt - now).total_seconds())


def _ttl_for(interval: str) -> float:
    if interval == "1d" and not _market_is_open_ist():
        # Closed: the last daily bar cannot change until the next session opens.
        return _seconds_until_next_open()
    return _CACHE_TTL.get(interval, _DEFAULT_TTL)


def cache_stats() -> dict:
    """Snapshot of cache counters plus the derived hit rate."""
    with _bar_cache_lock:
        hits, misses = _cache_stats["hits"], _cache_stats["misses"]
    total = hits + misses
    return {
        "hits":     hits,
        "misses":   misses,
        "hit_rate": round(hits / total, 3) if total else 0.0,
        "entries":  len(_bar_cache),
    }


def reset_cache_stats() -> None:
    with _bar_cache_lock:
        _cache_stats["hits"] = 0
        _cache_stats["misses"] = 0


def clear_bar_cache() -> None:
    with _bar_cache_lock:
        _bar_cache.clear()


# ─────────────────────────────────────────────────────────────────────────────
# Core fetch — one symbol, one interval, fresh Session every time
# ─────────────────────────────────────────────────────────────────────────────

# Yahoo `range` values, longest-first, used to honour a caller's `period`.
_PERIOD_ORDER = ["1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "max"]


def get_ohlcv(symbol: str, interval: str = "1d", period: str | None = None) -> pd.DataFrame:
    """
    Fetch OHLCV from Yahoo Finance REST API.
    Fresh requests.Session() per call — avoids shared-session rate limiting.
    Tries query1 first; falls back to query2 on 404.

    period: Yahoo `range` override (e.g. "6mo"). Defaults to the per-interval
    range in _YF_RANGE. Results are cached per (symbol, interval, range).
    """
    ticker   = _ticker(symbol.upper())
    yf_range = period if period in _PERIOD_ORDER else _YF_RANGE.get(interval, "1y")
    params   = {"interval": interval, "range": yf_range}

    key = (ticker, interval, yf_range)
    ttl = _ttl_for(interval)
    now = _time.time()
    with _bar_cache_lock:
        hit = _bar_cache.get(key)
        if hit is not None and now - hit[0] < ttl:
            _cache_stats["hits"] += 1
            return hit[1].copy()
        _cache_stats["misses"] += 1

    for base in _YF_BASES:
        try:
            sess = _req.Session()
            sess.headers.update(_YF_HDRS)
            resp = sess.get(f"{base}/{ticker}", params=params, timeout=15)
            if resp.status_code == 404:
                continue          # try the next base URL
            resp.raise_for_status()
            data   = resp.json()
            result = data["chart"]["result"][0]
            ts     = result["timestamp"]
            quote  = result["indicators"]["quote"][0]
            dates  = (
                pd.to_datetime(ts, unit="s", utc=True)
                .tz_convert("Asia/Kolkata")
                .tz_localize(None)
            )
            df = pd.DataFrame(
                {
                    "open":   quote.get("open",   []),
                    "high":   quote.get("high",   []),
                    "low":    quote.get("low",    []),
                    "close":  quote.get("close",  []),
                    "volume": quote.get("volume", []),
                },
                index=dates,
            )
            df.index.name = "datetime"
            df = df.dropna(subset=["close"])
            df = _drop_incomplete_trailing_bar(df, interval)
            with _bar_cache_lock:
                _bar_cache[key] = (_time.time(), df)
            return df.copy()
        except Exception as exc:
            log.debug("YF REST %s/%s (%s): %s", symbol, interval, base, exc)
            continue

    log.warning("YF REST %s/%s: all endpoints failed", symbol, interval)
    return pd.DataFrame()


def _drop_incomplete_trailing_bar(df: pd.DataFrame, interval: str) -> pd.DataFrame:
    """
    Drop a trailing bar that doesn't represent a fully-closed period — pattern
    detectors (NR7, Doji, Inside Bar, etc.) key off the "last" bar and get
    systematically fooled by an incomplete one:

    1. Intraday stub candle: Yahoo sometimes appends a placeholder bar at/after
       the exact market-close timestamp with volume=0 and open==high==low==close
       (no real trading occurred). This trivially looks like the narrowest/most
       neutral bar possible, so any "is the last bar unusually quiet" detector
       (NR7 above all) fires on it almost every time it's present.
    2. Still-forming 1wk/1mo bar: the "current week/month" candle is stamped
       immediately once the period starts, so scanning mid-week/mid-month
       compares a partial period's range against fully-closed prior periods —
       it's naturally narrower simply for having fewer elapsed trading days,
       not because of real range compression. Detected generically (no calendar
       assumptions) by comparing time-since-last-bar to the typical inter-bar
       gap seen earlier in the same series.
    """
    if df.empty:
        return df

    last = df.iloc[-1]
    is_stub = (
        float(last["volume"]) == 0.0
        and last["open"] == last["high"] == last["low"] == last["close"]
    )
    if is_stub:
        df = df.iloc[:-1]

    if interval in ("1wk", "1mo") and len(df) >= 3:
        typical_gap = df.index[-2] - df.index[-3]
        elapsed     = pd.Timestamp.now() - df.index[-1]
        if typical_gap.total_seconds() > 0 and elapsed < typical_gap * 0.9:
            df = df.iloc[:-1]

    return df


# ─────────────────────────────────────────────────────────────────────────────
# Per-symbol multi-timeframe fetcher  (used by the scanner)
# ─────────────────────────────────────────────────────────────────────────────

_ALL_TIMEFRAMES = ["5m", "15m", "30m", "1h", "4h", "1d", "1wk", "1mo"]


# NSE cash session open, IST. get_ohlcv() returns tz-naive IST timestamps.
SESSION_OPEN_HOUR   = 9
SESSION_OPEN_MINUTE = 15


def resample_to_4h(
    df_1h: pd.DataFrame,
    session_open_hour: int = SESSION_OPEN_HOUR,
    session_open_minute: int = SESSION_OPEN_MINUTE,
) -> pd.DataFrame:
    """
    Derive 4h candles from 1h bars — Yahoo Finance has no native 4h interval.

    Buckets are anchored to the **session open**, not to calendar midnight, so
    on NSE they run 09:15–13:15 and 13:15–15:30 (the final bucket is short).
    Plain `resample("4h")` produced 00:00/04:00/08:00/12:00/16:00 buckets, which
    straddle the open and the close, so every 4h pattern was detected on bars
    that never existed as a tradeable period.

    4h divides 24h exactly, so a single origin at the first session's open
    repeats the same boundaries every day.
    """
    if df_1h.empty:
        return df_1h
    agg = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    origin = (pd.Timestamp(df_1h.index[0]).normalize()
              + pd.Timedelta(hours=session_open_hour, minutes=session_open_minute))
    if origin > df_1h.index[0]:
        origin -= pd.Timedelta(days=1)
    out = df_1h.resample("4h", origin=origin).agg(agg).dropna(subset=["close"])
    out.index.name = "datetime"
    return out


def fetch_symbol_all_tfs(symbol: str) -> dict[str, pd.DataFrame]:
    """
    Fetch all 8 F&O timeframes (5m/15m/30m/1h/4h/1d/1wk/1mo) for ONE symbol.
    "4h" is derived from the already-fetched "1h" bars rather than requested
    from Yahoo directly (not a valid Yahoo interval).
    Returns dict[timeframe → DataFrame].
    Sleeps removed — concurrency is managed by the caller's semaphore.
    """
    result: dict[str, pd.DataFrame] = {}
    for tf in _ALL_TIMEFRAMES:
        if tf == "4h":
            continue
        df = get_ohlcv(symbol, interval=tf)
        if not df.empty:
            result[tf] = df
    if "1h" in result:
        df_4h = resample_to_4h(result["1h"])
        if not df_4h.empty:
            result["4h"] = df_4h
    return result


def fetch_symbol_equity_tfs(symbol: str) -> dict[str, pd.DataFrame]:
    """
    Fetch Daily / Weekly / Monthly for the equity scanner (positional analysis).
    Returns dict[timeframe → DataFrame].
    Sleeps removed — concurrency is managed by the caller's semaphore.
    """
    result: dict[str, pd.DataFrame] = {}
    for tf in EQUITY_TFS:
        df = get_ohlcv(symbol, interval=tf)
        if not df.empty:
            result[tf] = df
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Universe definitions
# ─────────────────────────────────────────────────────────────────────────────

# Index derivatives with confirmed working Yahoo Finance tickers (WS-4 verified)
_ALL_INDICES: list[str] = [
    "NIFTY", "BANKNIFTY", "FINNIFTY", "SENSEX",
    "MIDCPNIFTY",  # NIFTY_MID_SELECT.NS — now working
    "BANKEX",      # BSE-BANK.BO — now working
]

# Equity F&O universe — symbols confirmed to have YF data (WS-4 updates)
# TATAMOTORS re-enabled (ticker: TMCV.NS)
# ETERNAL added (formerly ZOMATO; renamed to Eternal Ltd Feb 2025; ticker: ETERNAL.NS)
_ALL_FNO_EQUITY: list[str] = [
    # Large-cap / Nifty 50
    "RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK", "AXISBANK",
    "KOTAKBANK", "SBIN", "BAJFINANCE", "BAJAJFINSV", "WIPRO", "LT",
    "MARUTI", "TATAMOTORS", "TATASTEEL", "SUNPHARMA", "DRREDDY", "CIPLA",
    "DIVISLAB", "HCLTECH", "TECHM", "NTPC", "POWERGRID", "ONGC", "BPCL",
    "COALINDIA", "NESTLEIND", "ASIANPAINT", "HINDUNILVR", "TITAN",
    "ULTRACEMCO", "GRASIM", "HEROMOTOCO", "EICHERMOT", "APOLLOHOSP",
    "ADANIENT", "ADANIPORTS", "JSWSTEEL", "M&M", "BHARTIARTL",
    "INDUSINDBK", "HINDPETRO", "IOC", "VEDL", "SAIL", "PNB",
    "BANKBARODA", "CANBK", "IDFCFIRSTB", "FEDERALBNK",
    "HAL", "BEL", "BHEL", "HDFCLIFE", "SBILIFE", "ITC", "IRCTC",
    "LICI", "DMART", "TATACONSUM", "BRITANNIA", "UPL", "BAJAJ-AUTO",
    "ETERNAL",    # formerly ZOMATO — renamed Feb 2025
    # Additional liquid F&O stocks (including RBLBANK and others often missed)
    "RBLBANK", "AUBANK", "ABCAPITAL", "MFSL", "PERSISTENT",
    "APLAPOLLO", "360ONE", "POLICYBZR", "NAUKRI",
    "PIIND", "DEEPAKNTR", "AARTIIND", "GMRAIRPORT", "CANBK",
    "ASTRAL", "TATAPOWER", "NHPC", "RECLTD", "PFC", "RVNL",
    "IRFC", "SJVN", "HUDCO", "NBCC", "BHEL",
]

UNIVERSE_PRESETS: dict[str, list[str]] = {
    # F&O scanner universes (unchanged)
    "indices":         _ALL_INDICES,
    "stocks":          _ALL_FNO_EQUITY,
    # Equity scanner — India broad
    "india_indices":   _ALL_INDICES,
    "india_nifty50":   _INDIA_NIFTY50,
    "india_nifty100":  _INDIA_NIFTY50 + _INDIA_NIFTY_NEXT50,
    # Equity scanner — US broad
    "us_indices":      _US_INDICES,
    "us_top30":        _US_EQUITY_TOP30,
    "us_tech":         _US_EQUITY_TECH,
}
# Larger / JSON-backed universes are resolved lazily via getter functions in equity_scanner.py

SCAN_UNIVERSE: list[str] = UNIVERSE_PRESETS["stocks"]
INTRADAY_TFS:  list[str] = ["5m", "15m", "30m", "1h", "4h"]

# Equity scanner uses positional timeframes only
EQUITY_TFS: list[str] = ["1d", "1wk", "1mo"]
DAILY_TF:      str       = "1d"

# Kept for compatibility with other modules that import _AUTO_PERIOD
_AUTO_PERIOD: dict[str, str] = _YF_RANGE


def get_nse_stocks() -> list[str]:
    """
    Return the complete live NSE F&O eligible equity list (equities only, no indices).

    Primary  : nselib.capital_market.fno_equity_list() — full 200+ symbol list
    Fallback1: fno_data_service.get_fno_symbols()      — NSE REST + LOT_SIZES
    Fallback2: static _ALL_FNO_EQUITY                   — minimal hardcoded list
    """
    # Primary: nselib (complete NSE F&O list)
    try:
        from nselib.capital_market import fno_equity_list
        df = fno_equity_list()
        syms = [s for s in df["symbol"].tolist() if isinstance(s, str) and s.strip()]
        if len(syms) > 50:
            log.debug("NSE F&O stocks via nselib: %d symbols", len(syms))
            return syms
    except Exception as e:
        log.debug("nselib fno_equity_list failed: %s", e)

    # Fallback 1: fno_data_service REST + LOT_SIZES
    try:
        from services.fno_data_service import get_fno_symbols
        syms = get_fno_symbols()
        if syms and len(syms) > 10:
            log.debug("NSE F&O stocks via fno_data_service: %d symbols", len(syms))
            return syms
    except Exception as e:
        log.debug("fno_data_service fallback failed: %s", e)

    # Fallback 2: hardcoded list (includes RBLBANK and other known stocks)
    return _ALL_FNO_EQUITY


def get_dynamic_universe() -> list[str]:
    """Legacy alias — kept for compatibility."""
    return _ALL_INDICES + get_nse_stocks()


def get_daily(symbol: str, period: str = "1y") -> pd.DataFrame:
    """
    Daily OHLCV. `period` is a Yahoo `range` value and is honoured — it used to
    be accepted and silently ignored, so callers asking for "6mo" got 1y.
    """
    return get_ohlcv(symbol, interval="1d", period=period)
