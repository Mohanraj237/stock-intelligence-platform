"""
US Market Universe Sync

Sources:
  - Wikipedia HTML tables for S&P 500 and NASDAQ 100
  - Hardcoded fallbacks for DOW 30 and sector universes

Universe files stored in storage/universe/US_{name}.json to avoid
collisions with Indian universe files.
"""
from __future__ import annotations
import json
import logging
import time
from io import StringIO
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

import requests
import pandas as pd

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parents[1]
UNIVERSE_DIR = BASE_DIR / "storage" / "universe"

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

# ── Fallback symbol lists (used when Wikipedia fetch fails) ───────────────────
DOW_30 = [
    "AAPL", "AMGN", "AXP", "BA", "CAT", "CRM", "CSCO", "CVX", "DIS", "DOW",
    "GS", "HD", "HON", "IBM", "JNJ", "JPM", "KO", "MCD", "MMM", "MRK",
    "MSFT", "NKE", "PG", "TRV", "UNH", "V", "VZ", "WBA", "WMT", "XOM",
]

SP500_FALLBACK = [
    "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "GOOG", "BRK-B", "TSLA", "LLY",
    "JPM", "UNH", "XOM", "V", "AVGO", "MA", "JNJ", "PG", "COST", "MRK",
    "HD", "ORCL", "CVX", "ABBV", "BAC", "NFLX", "CRM", "ADBE", "AMD", "TMO",
    "PEP", "CSCO", "WMT", "KO", "ABT", "MCD", "DIS", "ACN", "INTC", "IBM",
    "GE", "CAT", "UBER", "NOW", "INTU", "AMAT", "QCOM", "SPGI", "GS", "LOW",
    "AXP", "T", "RTX", "BKNG", "AMGN", "DHR", "SYK", "MS", "TXN", "PFE",
    "C", "NEE", "PANW", "ADP", "COP", "ISRG", "DE", "BMY", "ETN", "SCHW",
    "VRTX", "REGN", "CI", "CB", "BX", "ADI", "LRCX", "MDT", "KLAC", "MMC",
    "CEG", "SHW", "UPS", "PLD", "TJX", "HCA", "ICE", "GILD", "ELV", "NKE",
    "SBUX", "SO", "CME", "WM", "MO", "FI", "DUK", "FCX", "MCO", "WELL",
]

NASDAQ100_FALLBACK = [
    "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "GOOG", "TSLA", "AVGO", "COST",
    "NFLX", "AMD", "ADBE", "QCOM", "PEP", "CSCO", "TXN", "INTU", "AMAT", "MU",
    "INTC", "LRCX", "ADP", "PANW", "SBUX", "ADI", "KLAC", "MRVL", "SNPS", "CDNS",
    "REGN", "MDLZ", "PYPL", "GILD", "MELI", "CEG", "CTAS", "MAR", "NXPI", "CRWD",
    "KDP", "FTNT", "ABNB", "TEAM", "ORLY", "DXCM", "CPRT", "IDXX", "PAYX", "FAST",
    "ODFL", "AEP", "ON", "EXC", "CHTR", "XEL", "ROP", "SGEN", "GEHC", "BIIB",
    "ILMN", "MNST", "ROST", "VRSK", "CSX", "FANG", "WDAY", "GFS", "TTD", "ZS",
    "DLTR", "ANSS", "PCAR", "CDW", "LULU", "ENPH", "DDOG", "SPLK", "WBD", "EBAY",
    "WBA", "HON", "AMGN", "CMCSA", "MCHP", "ASML", "PDD", "BIDU", "JD", "NTES",
    "SIEGY", "TSMC", "ZM", "DOCU", "ROKU", "PINS", "SNAP", "LYFT", "MTCH", "EA",
]

# Sector universe symbol lists
SECTOR_SYMBOLS = {
    "US TECHNOLOGY": [
        "AAPL", "MSFT", "NVDA", "AVGO", "ORCL", "AMD", "QCOM", "INTC", "ADBE", "CRM",
        "TXN", "AMAT", "CSCO", "UBER", "IBM", "INTU", "PANW", "KLAC", "LRCX", "ADI",
        "NOW", "SNPS", "CDNS", "MRVL", "FTNT", "ON", "MU", "NXPI", "HPQ", "DELL",
    ],
    "US FINANCIALS": [
        "JPM", "BRK-B", "BAC", "WFC", "GS", "MS", "SPGI", "BLK", "AXP", "C",
        "CB", "CME", "COF", "ICE", "MCO", "SCHW", "USB", "PNC", "TFC", "BK",
        "FI", "MSCI", "MMC", "AFL", "MET", "PRU", "ALL", "RE", "CBOE", "STT",
    ],
    "US HEALTHCARE": [
        "UNH", "LLY", "JNJ", "ABBV", "MRK", "TMO", "ABT", "DHR", "PFE", "BMY",
        "AMGN", "ISRG", "MDT", "CI", "ELV", "SYK", "VRTX", "REGN", "HCA", "GILD",
        "BIIB", "DXCM", "IDXX", "ILMN", "ZBH", "BAX", "COO", "VAR", "PKI", "MTD",
    ],
    "US ENERGY": [
        "XOM", "CVX", "COP", "SLB", "EOG", "MPC", "PSX", "VLO", "OXY", "KMI",
        "WMB", "BKR", "DVN", "HAL", "FANG", "HES", "MRO", "APA", "CVI", "PXD",
    ],
    "US CONSUMER DISC": [
        "AMZN", "TSLA", "HD", "MCD", "NKE", "SBUX", "LOW", "TJX", "BKNG", "CMG",
        "ORLY", "AZO", "GM", "F", "DHI", "LEN", "PHM", "NVR", "ROST", "DLTR",
    ],
    "US COMMUNICATION": [
        "META", "GOOGL", "GOOG", "NFLX", "DIS", "T", "VZ", "CMCSA", "CHTR", "WBD",
        "EA", "TTWO", "MTCH", "PINS", "SNAP", "LYFT", "ZM", "PARA", "FOX", "FOXA",
    ],
    "US INDUSTRIALS": [
        "CAT", "BA", "UPS", "HON", "RTX", "DE", "MMM", "GE", "LMT", "ETN",
        "FDX", "PH", "NSC", "CSX", "UNP", "EMR", "ROK", "ODFL", "CTAS", "CMI",
    ],
    "US CONSUMER STAPLES": [
        "WMT", "PG", "KO", "PEP", "COST", "MO", "PM", "MDLZ", "KHC", "GIS",
        "STZ", "HSY", "K", "SJM", "CAG", "MKC", "CPB", "HRL", "TSN", "LW",
    ],
}

ALL_US_KEYS = "ALL US"

US_INDEX_URLS = {
    "S&P 500":    "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
    "NASDAQ 100": "https://en.wikipedia.org/wiki/Nasdaq-100",
}

US_DISPLAY_MAP = {
    ALL_US_KEYS:           "All US Stocks (S&P 500)",
    "S&P 500":             "S&P 500 (Large Cap)",
    "NASDAQ 100":          "NASDAQ 100 (Tech Heavy)",
    "DOW 30":              "DOW 30 (Blue Chip)",
    "US TECHNOLOGY":       "US Technology",
    "US FINANCIALS":       "US Financials",
    "US HEALTHCARE":       "US Healthcare",
    "US ENERGY":           "US Energy",
    "US CONSUMER DISC":    "US Consumer Discretionary",
    "US COMMUNICATION":    "US Communication Services",
    "US INDUSTRIALS":      "US Industrials",
    "US CONSUMER STAPLES": "US Consumer Staples",
}


def _us_universe_path(name: str) -> Path:
    safe = "US_" + name.replace(" ", "_").replace("/", "_").replace("&", "AND")
    return UNIVERSE_DIR / f"{safe}.json"


def _fetch_sp500_wikipedia() -> list[str]:
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    resp = requests.get(url, headers=_HEADERS, timeout=20)
    resp.raise_for_status()
    tables = pd.read_html(StringIO(resp.text))
    df = tables[0]
    for col in ("Symbol", "Ticker symbol", "Ticker"):
        if col in df.columns:
            return df[col].astype(str).str.strip().str.replace(".", "-", regex=False).tolist()
    return df.iloc[:, 0].astype(str).str.strip().tolist()


def _fetch_nasdaq100_wikipedia() -> list[str]:
    url = "https://en.wikipedia.org/wiki/Nasdaq-100"
    resp = requests.get(url, headers=_HEADERS, timeout=20)
    resp.raise_for_status()
    tables = pd.read_html(StringIO(resp.text))
    for df in tables:
        for col in ("Ticker", "Symbol", "Ticker symbol"):
            if col in df.columns:
                syms = df[col].astype(str).str.strip().tolist()
                if len(syms) >= 80:
                    return syms
    return []


def fetch_and_cache_us_universe(name: str) -> dict:
    UNIVERSE_DIR.mkdir(parents=True, exist_ok=True)

    if name == "DOW 30":
        symbols = DOW_30[:]
        companies = {s: s for s in symbols}
        fallback = False
    elif name in SECTOR_SYMBOLS:
        symbols = SECTOR_SYMBOLS[name][:]
        companies = {s: s for s in symbols}
        fallback = False
    elif name == "S&P 500":
        try:
            symbols = _fetch_sp500_wikipedia()
            companies = {s: s for s in symbols}
            fallback = False
        except Exception as e:
            logger.warning(f"S&P 500 Wikipedia fetch failed: {e}. Using fallback.")
            symbols = SP500_FALLBACK[:]
            companies = {s: s for s in symbols}
            fallback = True
    elif name == "NASDAQ 100":
        try:
            symbols = _fetch_nasdaq100_wikipedia()
            if not symbols:
                raise ValueError("Empty list from Wikipedia")
            companies = {s: s for s in symbols}
            fallback = False
        except Exception as e:
            logger.warning(f"NASDAQ 100 Wikipedia fetch failed: {e}. Using fallback.")
            symbols = NASDAQ100_FALLBACK[:]
            companies = {s: s for s in symbols}
            fallback = True
    else:
        symbols = []
        companies = {}
        fallback = True

    data = {
        "name": name,
        "symbols": symbols,
        "companies": companies,
        "count": len(symbols),
        "synced_at": time.time(),
        "fallback": fallback,
        "region": "US",
    }
    path = _us_universe_path(name)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return data


def get_us_universe(name: str, force_refresh: bool = False) -> dict:
    if name == ALL_US_KEYS:
        return get_us_universe("S&P 500", force_refresh)
    path = _us_universe_path(name)
    if not force_refresh and path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            age = time.time() - data.get("synced_at", 0)
            if age < 86400:
                return data
        except Exception:
            pass
    return fetch_and_cache_us_universe(name)


def get_us_universe_symbols(name: str, limit: Optional[int] = None, force_refresh: bool = False) -> list[str]:
    data = get_us_universe(name, force_refresh)
    symbols = data.get("symbols", [])
    return symbols[:limit] if limit else symbols


def get_all_us_universe_names() -> list[str]:
    return [
        ALL_US_KEYS,
        "S&P 500", "NASDAQ 100", "DOW 30",
        "US TECHNOLOGY", "US FINANCIALS", "US HEALTHCARE",
        "US ENERGY", "US CONSUMER DISC", "US COMMUNICATION",
        "US INDUSTRIALS", "US CONSUMER STAPLES",
    ]


def us_universe_display_map() -> dict[str, str]:
    return US_DISPLAY_MAP


def us_startup_sync(parallel: bool = True) -> dict:
    """Sync all US universes. Returns status dict."""
    names = ["S&P 500", "NASDAQ 100", "DOW 30"] + list(SECTOR_SYMBOLS.keys())
    results = {}
    if parallel:
        with ThreadPoolExecutor(max_workers=4) as ex:
            futures = {ex.submit(fetch_and_cache_us_universe, n): n for n in names}
            for future in as_completed(futures):
                n = futures[future]
                try:
                    data = future.result()
                    results[n] = {"count": data["count"], "ok": True}
                except Exception as e:
                    results[n] = {"ok": False, "error": str(e)}
    else:
        for n in names:
            try:
                data = fetch_and_cache_us_universe(n)
                results[n] = {"count": data["count"], "ok": True}
            except Exception as e:
                results[n] = {"ok": False, "error": str(e)}
    return results


def us_universe_sync_status() -> dict:
    status = {}
    for name in get_all_us_universe_names():
        if name == ALL_US_KEYS:
            continue
        path = _us_universe_path(name)
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                age_h = (time.time() - data.get("synced_at", 0)) / 3600
                status[name] = {
                    "count": data.get("count", 0),
                    "age_hours": round(age_h, 1),
                    "synced": True,
                    "fallback": data.get("fallback", False),
                }
            except Exception:
                status[name] = {"synced": False}
        else:
            status[name] = {"synced": False}
    return status
