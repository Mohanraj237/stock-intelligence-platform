from __future__ import annotations

from functools import lru_cache
from io import StringIO
from pathlib import Path

import pandas as pd
import requests

from backend.stock_universe import DEFAULT_NSE_UNIVERSE


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "en-IN,en;q=0.9",
}

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
EQUITY_MASTER_URL = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"

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
}

FALLBACK_INDEX_SYMBOLS = {
    "NIFTY 50": DEFAULT_NSE_UNIVERSE,
    "NIFTY NEXT 50": ["ABB", "ADANIENSOL", "AMBUJACEM", "BAJAJHLDNG", "BANKBARODA", "BPCL", "BRITANNIA", "CANBK", "CHOLAFIN", "DABUR"],
    "NIFTY MIDCAP 150": ["ANGELONE", "ASHOKLEY", "AUROPHARMA", "BALKRISIND", "BANDHANBNK", "BHARATFORG", "COFORGE", "CUMMINSIND", "DIXON", "FEDERALBNK"],
    "NIFTY SMALLCAP 250": ["AARTIIND", "CAMS", "CDSL", "FIVESTAR", "GESHIP", "IEX", "KARURVYSYA", "KFINTECH", "MANAPPURAM", "MCX"],
    "NIFTY BANK": ["HDFCBANK", "ICICIBANK", "SBIN", "KOTAKBANK", "AXISBANK", "BANKBARODA", "PNB", "CANBK", "FEDERALBNK", "IDFCFIRSTB"],
    "NIFTY IT": ["TCS", "INFY", "HCLTECH", "WIPRO", "TECHM", "LTIM", "PERSISTENT", "MPHASIS", "COFORGE"],
}


def _read_csv_url(url: str, timeout: int = 20) -> pd.DataFrame:
    response = requests.get(url, headers=HEADERS, timeout=timeout)
    response.raise_for_status()
    return pd.read_csv(StringIO(response.text))


@lru_cache(maxsize=1)
def get_all_nse_equities() -> pd.DataFrame:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = DATA_DIR / "nse_equity_master.csv"
    try:
        df = _read_csv_url(EQUITY_MASTER_URL)
        df.to_csv(cache_file, index=False)
    except Exception:
        if cache_file.exists():
            df = pd.read_csv(cache_file)
        else:
            df = pd.DataFrame({"SYMBOL": DEFAULT_NSE_UNIVERSE, "NAME OF COMPANY": DEFAULT_NSE_UNIVERSE, "SERIES": ["EQ"] * len(DEFAULT_NSE_UNIVERSE)})

    symbol_col = "SYMBOL" if "SYMBOL" in df.columns else df.columns[0]
    name_col = "NAME OF COMPANY" if "NAME OF COMPANY" in df.columns else symbol_col
    series_col = "SERIES" if "SERIES" in df.columns else None
    if series_col:
        df = df[df[series_col].astype(str).str.upper().eq("EQ")]
    result = df[[symbol_col, name_col]].rename(columns={symbol_col: "Symbol", name_col: "Company"})
    result["Symbol"] = result["Symbol"].astype(str).str.upper().str.strip()
    result = result.drop_duplicates("Symbol").sort_values("Symbol").reset_index(drop=True)
    return result


@lru_cache(maxsize=32)
def get_index_constituents(index_name: str) -> pd.DataFrame:
    clean_name = index_name.upper()
    url = INDEX_URLS.get(clean_name)
    try:
        if not url:
            raise RuntimeError(f"Unsupported index {index_name}")
        df = _read_csv_url(url)
        symbol_col = "Symbol" if "Symbol" in df.columns else "SYMBOL" if "SYMBOL" in df.columns else df.columns[0]
        company_col = "Company Name" if "Company Name" in df.columns else "Company" if "Company" in df.columns else symbol_col
        result = df[[symbol_col, company_col]].rename(columns={symbol_col: "Symbol", company_col: "Company"})
    except Exception:
        symbols = FALLBACK_INDEX_SYMBOLS.get(clean_name, DEFAULT_NSE_UNIVERSE)
        result = pd.DataFrame({"Symbol": symbols, "Company": symbols})
    result["Symbol"] = result["Symbol"].astype(str).str.upper().str.strip()
    return result.drop_duplicates("Symbol").reset_index(drop=True)


def universe_for_segment(segment: str, limit: int | None = None) -> list[str]:
    clean = segment.upper()
    if clean in ("ALL NSE", "ALL NSE STOCKS", "ALL"):
        symbols = get_all_nse_equities()["Symbol"].tolist()
    elif clean in ("BLUE CHIP", "BLUECHIP"):
        symbols = get_index_constituents("NIFTY 50")["Symbol"].tolist()
    elif clean in ("LARGE CAP", "LARGECAP"):
        symbols = get_index_constituents("NIFTY 100")["Symbol"].tolist()
    elif clean in ("MID CAP", "MIDCAP"):
        symbols = get_index_constituents("NIFTY MIDCAP 150")["Symbol"].tolist()
    elif clean in ("SMALL CAP", "SMALLCAP"):
        symbols = get_index_constituents("NIFTY SMALLCAP 250")["Symbol"].tolist()
    elif clean in INDEX_URLS:
        symbols = get_index_constituents(clean)["Symbol"].tolist()
    else:
        symbols = DEFAULT_NSE_UNIVERSE
    return symbols[:limit] if limit else symbols


def segment_options() -> list[str]:
    return [
        "Blue Chip",
        "Large Cap",
        "Mid Cap",
        "Small Cap",
        "All NSE Stocks",
        "NIFTY 50",
        "NIFTY NEXT 50",
        "NIFTY 100",
        "NIFTY 200",
        "NIFTY 500",
        "NIFTY BANK",
        "NIFTY IT",
        "NIFTY PHARMA",
        "NIFTY AUTO",
        "NIFTY FMCG",
    ]
