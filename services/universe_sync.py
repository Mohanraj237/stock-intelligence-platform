from __future__ import annotations
import logging
import time
from io import StringIO
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

import pandas as pd
import requests

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept-Language": "en-IN,en;q=0.9",
}

INDEX_URLS = {
    "NIFTY 50": "https://archives.nseindia.com/content/indices/ind_nifty50list.csv",
    "NIFTY NEXT 50": "https://archives.nseindia.com/content/indices/ind_niftynext50list.csv",
    "NIFTY 100": "https://archives.nseindia.com/content/indices/ind_nifty100list.csv",
    "NIFTY 200": "https://archives.nseindia.com/content/indices/ind_nifty200list.csv",
    "NIFTY 500": "https://archives.nseindia.com/content/indices/ind_nifty500list.csv",
    "NIFTY MIDCAP 150": "https://archives.nseindia.com/content/indices/ind_niftymidcap150list.csv",
    "NIFTY SMALLCAP 250": "https://archives.nseindia.com/content/indices/ind_niftysmallcap250list.csv",
    "NIFTY BANK": "https://archives.nseindia.com/content/indices/ind_niftybanklist.csv",
    "NIFTY IT": "https://archives.nseindia.com/content/indices/ind_niftyitlist.csv",
    "NIFTY PHARMA": "https://archives.nseindia.com/content/indices/ind_niftypharmalist.csv",
    "NIFTY AUTO": "https://archives.nseindia.com/content/indices/ind_niftyautolist.csv",
    "NIFTY FMCG": "https://archives.nseindia.com/content/indices/ind_niftyfmcglist.csv",
    "NIFTY PSU BANK": "https://archives.nseindia.com/content/indices/ind_niftypsubanklist.csv",
    "NIFTY ENERGY": "https://archives.nseindia.com/content/indices/ind_niftyenergylist.csv",
    "NIFTY REALTY": "https://archives.nseindia.com/content/indices/ind_niftyrealtylist.csv",
    "NIFTY INFRA": "https://archives.nseindia.com/content/indices/ind_niftyinfralist.csv",
    "NIFTY METAL": "https://archives.nseindia.com/content/indices/ind_niftymetallist.csv",
    "NIFTY MEDIA": "https://archives.nseindia.com/content/indices/ind_niftymedialist.csv",
}

EQUITY_MASTER_URL = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"

SEGMENT_MAP = {
    "NIFTY 50": "NIFTY 50",
    "BLUE CHIP": "NIFTY 50",
    "NIFTY NEXT 50": "NIFTY NEXT 50",
    "NIFTY 100": "NIFTY 100",
    "LARGE CAP": "NIFTY 100",
    "LARGECAP": "NIFTY 100",
    "NIFTY 200": "NIFTY 200",
    "NIFTY 500": "NIFTY 500",
    "NIFTY MIDCAP 150": "NIFTY MIDCAP 150",
    "MID CAP": "NIFTY MIDCAP 150",
    "MIDCAP": "NIFTY MIDCAP 150",
    "NIFTY SMALLCAP 250": "NIFTY SMALLCAP 250",
    "SMALL CAP": "NIFTY SMALLCAP 250",
    "SMALLCAP": "NIFTY SMALLCAP 250",
    "NIFTY BANK": "NIFTY BANK",
    "BANK": "NIFTY BANK",
    "NIFTY IT": "NIFTY IT",
    "IT": "NIFTY IT",
    "NIFTY PHARMA": "NIFTY PHARMA",
    "PHARMA": "NIFTY PHARMA",
    "NIFTY AUTO": "NIFTY AUTO",
    "AUTO": "NIFTY AUTO",
    "NIFTY FMCG": "NIFTY FMCG",
    "FMCG": "NIFTY FMCG",
    "NIFTY PSU BANK": "NIFTY PSU BANK",
    "PSU": "NIFTY PSU BANK",
    "PSU BANK": "NIFTY PSU BANK",
    "NIFTY ENERGY": "NIFTY ENERGY",
    "ENERGY": "NIFTY ENERGY",
    "NIFTY METAL": "NIFTY METAL",
    "METAL": "NIFTY METAL",
    "NIFTY REALTY": "NIFTY REALTY",
    "REALTY": "NIFTY REALTY",
}

FALLBACK_SYMBOLS = {
    "NIFTY 50": ["RELIANCE","TCS","HDFCBANK","ICICIBANK","INFY","HINDUNILVR","ITC","SBIN","BHARTIARTL","BAJFINANCE","KOTAKBANK","HCLTECH","LT","AXISBANK","ASIANPAINT","MARUTI","SUNPHARMA","TATAMOTORS","M&M","NTPC","POWERGRID","ULTRACEMCO","TITAN","WIPRO","BAJAJFINSV","ADANIENT","ONGC","JSWSTEEL","TATASTEEL","TECHM","NESTLEIND","HINDALCO","DIVISLAB","DRREDDY","CIPLA","BPCL","COALINDIA","GRASIM","HDFCLIFE","BRITANNIA","INDUSINDBK","SBILIFE","EICHERMOT","TATACONSUM","APOLLOHOSP","HEROMOTOCO","BAJAJ-AUTO","SHREECEM","JIOFIN","MAXHEALTH"],
    "NIFTY BANK": ["HDFCBANK","ICICIBANK","SBIN","KOTAKBANK","AXISBANK","BANKBARODA","PNB","CANBK","FEDERALBNK","IDFCFIRSTB","INDUSINDBK","BANDHANBNK"],
    "NIFTY IT": ["TCS","INFY","HCLTECH","WIPRO","TECHM","LTIM","PERSISTENT","MPHASIS","COFORGE","OFSS"],
    "NIFTY PHARMA": ["SUNPHARMA","DRREDDY","CIPLA","DIVISLAB","LUPIN","TORNTPHARM","ALKEM","BIOCON","AUROPHARMA","IPCA"],
    "NIFTY AUTO": ["MARUTI","TATAMOTORS","M&M","EICHERMOT","BAJAJ-AUTO","HEROMOTOCO","ASHOKLEY","BHARATFORG","MOTHERSON","MRF"],
    "NIFTY FMCG": ["HINDUNILVR","ITC","NESTLEIND","BRITANNIA","DABUR","GODREJCP","EMAMILTD","COLPAL","MARICO","TATACONSUM"],
    "NIFTY MIDCAP 150": ["DIXON","COFORGE","PERSISTENT","MPHASIS","FEDERALBNK","IDFCFIRSTB","BANDHANBNK","CHOLAFIN","BAJAJHLDNG","AUROPHARMA","LUPIN","TORNTPHARM","ASHOKLEY","BHARATFORG","CUMMINSIND","BALKRISIND","ANGELONE","MGL","IGL","PIIND"],
    "NIFTY SMALLCAP 250": ["AARTIIND","CAMS","CDSL","IEX","MCX","KFINTECH","KARURVYSYA","MANAPPURAM","GESHIP","FIVESTAR"],
    "NIFTY ENERGY": ["RELIANCE","ONGC","BPCL","POWERGRID","NTPC","ADANIENT","TATAPOWER","COALINDIA","GAIL","IOC"],
    "NIFTY PSU BANK": ["SBIN","BANKBARODA","PNB","CANBK","UNIONBANK","INDIANB","UCOBANK","CENTRALBK"],
    "NIFTY METAL": ["TATASTEEL","JSWSTEEL","HINDALCO","SAIL","NMDC","VEDL","APLAPOLLO","HDFCBANK"],
}

BASE_DIR = Path(__file__).resolve().parents[1]
UNIVERSE_DIR = BASE_DIR / "storage" / "universe"

def _read_csv_url(url: str, timeout: int = 20) -> pd.DataFrame:
    resp = requests.get(url, headers=HEADERS, timeout=timeout)
    resp.raise_for_status()
    return pd.read_csv(StringIO(resp.text))

def _extract_symbols(df: pd.DataFrame) -> list[str]:
    for col in ("Symbol", "SYMBOL", "Symbols"):
        if col in df.columns:
            return df[col].astype(str).str.upper().str.strip().tolist()
    return df.iloc[:, 0].astype(str).str.upper().str.strip().tolist()

def _extract_companies(df: pd.DataFrame) -> list[str]:
    for col in ("Company Name", "Company", "NAME OF COMPANY"):
        if col in df.columns:
            return df[col].astype(str).str.strip().tolist()
    return [""] * len(df)

def _universe_path(name: str) -> Path:
    safe = name.replace(" ", "_").replace("/", "_")
    return UNIVERSE_DIR / f"{safe}.json"

def fetch_and_cache_universe(name: str) -> dict:
    import json
    UNIVERSE_DIR.mkdir(parents=True, exist_ok=True)
    url = INDEX_URLS.get(name)
    path = _universe_path(name)
    try:
        df = _read_csv_url(url)
        symbols = _extract_symbols(df)
        companies = _extract_companies(df)
        data = {
            "name": name,
            "symbols": symbols,
            "companies": dict(zip(symbols, companies)),
            "count": len(symbols),
            "synced_at": time.time(),
        }
    except Exception as e:
        fallback = FALLBACK_SYMBOLS.get(name, [])
        # Don't clobber a better existing cache with an inferior fallback. This
        # runs on every backend startup (see startup_sync); NSE's archive
        # endpoints have become unreliable (403/503), so blindly overwriting
        # on every failed attempt would degrade the cache a little more each
        # restart instead of leaving already-good data alone.
        if path.exists():
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
                if len(existing.get("symbols", [])) >= len(fallback):
                    logger.warning(
                        f"Failed to fetch {name} from NSE: {e}. "
                        f"Keeping existing cache ({len(existing.get('symbols', []))} symbols)."
                    )
                    return existing
            except Exception:
                pass
        logger.warning(f"Failed to fetch {name} from NSE: {e}. Using fallback.")
        data = {
            "name": name,
            "symbols": fallback,
            "companies": {s: s for s in fallback},
            "count": len(fallback),
            "synced_at": time.time(),
            "fallback": True,
        }
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return data

def get_universe(name: str, force_refresh: bool = False) -> dict:
    import json
    norm = SEGMENT_MAP.get(name.upper(), name.upper())
    path = _universe_path(norm)
    if not force_refresh and path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            age = time.time() - data.get("synced_at", 0)
            # Empty fallback data retries every hour; non-empty live data caches for 24 hours
            is_fallback = data.get("fallback") or data.get("count", 0) == 0
            ttl = 3600 if is_fallback else 86400
            if age < ttl:
                return data
        except Exception:
            pass
    return fetch_and_cache_universe(norm)

ALL_NSE_KEY = "ALL NSE"

def get_universe_symbols(name: str, limit: Optional[int] = None, force_refresh: bool = False) -> list[str]:
    if name == ALL_NSE_KEY:
        symbols = get_all_nse_symbols()
    else:
        data = get_universe(name, force_refresh)
        symbols = data.get("symbols", [])
    return symbols[:limit] if limit else symbols

def get_all_nse_symbols(limit: Optional[int] = None) -> list[str]:
    import json
    cache_path = BASE_DIR / "storage" / "data" / "nse_equity_master.json"
    (BASE_DIR / "storage" / "data").mkdir(parents=True, exist_ok=True)
    if cache_path.exists():
        try:
            data = json.loads(cache_path.read_text(encoding="utf-8"))
            age = time.time() - data.get("synced_at", 0)
            if age < 86400:
                symbols = data.get("symbols", [])
                return symbols[:limit] if limit else symbols
        except Exception:
            pass
    try:
        df = _read_csv_url(EQUITY_MASTER_URL)
        for col in ("SERIES", "Series"):
            if col in df.columns:
                df = df[df[col].astype(str).str.upper() == "EQ"]
                break
        symbols = _extract_symbols(df)
        data = {"symbols": symbols, "synced_at": time.time(), "count": len(symbols)}
        cache_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception as e:
        logger.error(f"NSE equity master fetch failed: {e}")
        symbols = FALLBACK_SYMBOLS.get("NIFTY 50", [])
    return symbols[:limit] if limit else symbols

def startup_sync(parallel: bool = True) -> dict:
    """Sync all major universes on app startup. Returns status dict."""
    names = list(INDEX_URLS.keys())
    results = {}
    if parallel:
        with ThreadPoolExecutor(max_workers=4) as ex:
            futures = {ex.submit(fetch_and_cache_universe, n): n for n in names}
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
                data = fetch_and_cache_universe(n)
                results[n] = {"count": data["count"], "ok": True}
            except Exception as e:
                results[n] = {"ok": False, "error": str(e)}
    return results

def universe_sync_status() -> dict:
    import json, time as _time
    status = {}
    for name in INDEX_URLS:
        path = _universe_path(name)
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                age_h = (_time.time() - data.get("synced_at", 0)) / 3600
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

def get_all_universe_names() -> list[str]:
    return [
        ALL_NSE_KEY,
        "NIFTY 50", "NIFTY NEXT 50", "NIFTY 100", "NIFTY 200", "NIFTY 500",
        "NIFTY MIDCAP 150", "NIFTY SMALLCAP 250",
        "NIFTY BANK", "NIFTY IT", "NIFTY PHARMA", "NIFTY AUTO", "NIFTY FMCG",
        "NIFTY PSU BANK", "NIFTY ENERGY", "NIFTY METAL", "NIFTY REALTY",
    ]

def universe_display_map() -> dict[str, str]:
    return {
        ALL_NSE_KEY:          "All NSE Stocks (2000+)",
        "NIFTY 50":           "NIFTY 50 (Large Cap, Blue Chip)",
        "NIFTY NEXT 50":      "NIFTY NEXT 50 (Emerging Large Cap)",
        "NIFTY 100":          "NIFTY 100 (Top 100)",
        "NIFTY 200":          "NIFTY 200 (Top 200)",
        "NIFTY 500":          "NIFTY 500 (Broad Market)",
        "NIFTY MIDCAP 150":   "NIFTY MIDCAP 150 (Mid Cap)",
        "NIFTY SMALLCAP 250": "NIFTY SMALLCAP 250 (Small Cap)",
        "NIFTY BANK":         "NIFTY BANK (Banking)",
        "NIFTY IT":           "NIFTY IT (Technology)",
        "NIFTY PHARMA":       "NIFTY PHARMA (Pharmaceuticals)",
        "NIFTY AUTO":         "NIFTY AUTO (Automobiles)",
        "NIFTY FMCG":         "NIFTY FMCG (Consumer Goods)",
        "NIFTY PSU BANK":     "NIFTY PSU BANK (Public Sector Banks)",
        "NIFTY ENERGY":       "NIFTY ENERGY (Energy Sector)",
        "NIFTY METAL":        "NIFTY METAL (Metals & Mining)",
        "NIFTY REALTY":       "NIFTY REALTY (Real Estate)",
    }
