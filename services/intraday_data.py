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
}

# NSE/BSE symbol → Yahoo Finance ticker
# All tickers confirmed working as of 2026-06-09 (WS-4 verification)
_INDEX_MAP: dict[str, str] = {
    # NSE indices
    "NIFTY":      "^NSEI",
    "BANKNIFTY":  "^NSEBANK",
    "FINNIFTY":   "NIFTY_FIN_SERVICE.NS",
    "SENSEX":     "^BSESN",
    "MIDCPNIFTY": "NIFTY_MID_SELECT.NS",   # was omitted — now works
    # BSE indices
    "BANKEX":     "BSE-BANK.BO",           # was omitted — BSE Bankex
    # Volatility index
    "INDIAVIX":   "^INDIAVIX",             # India VIX — used as NSE fallback
}

# Equity symbols whose YF ticker does not follow the {SYMBOL}.NS convention
# Key = NSE symbol (as used in the platform), Value = Yahoo Finance ticker
_EQUITY_TICKER_OVERRIDE: dict[str, str] = {
    "TATAMOTORS": "TMCV.NS",    # Tata Motors Ltd — YF uses TMCV.NS (WS-4)
    "ETERNAL":    "ETERNAL.NS", # formerly ZOMATO; company renamed to Eternal Ltd 2025
}


def _ticker(symbol: str) -> str:
    s = symbol.upper()
    # Index symbols have explicit YF ticker mappings
    if s in _INDEX_MAP:
        return _INDEX_MAP[s]
    # Equity symbols with non-standard YF tickers
    if s in _EQUITY_TICKER_OVERRIDE:
        return _EQUITY_TICKER_OVERRIDE[s]
    # Default: append .NS for NSE equities
    return f"{s}.NS"


# ─────────────────────────────────────────────────────────────────────────────
# Core fetch — one symbol, one interval, fresh Session every time
# ─────────────────────────────────────────────────────────────────────────────

def get_ohlcv(symbol: str, interval: str = "1d") -> pd.DataFrame:
    """
    Fetch OHLCV from Yahoo Finance REST API.
    Fresh requests.Session() per call — avoids shared-session rate limiting.
    Tries query1 first; falls back to query2 on 404.
    """
    ticker   = _ticker(symbol.upper())
    yf_range = _YF_RANGE.get(interval, "1y")
    params   = {"interval": interval, "range": yf_range}

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
            return df.dropna(subset=["close"])
        except Exception as exc:
            log.debug("YF REST %s/%s (%s): %s", symbol, interval, base, exc)
            continue

    log.warning("YF REST %s/%s: all endpoints failed", symbol, interval)
    return pd.DataFrame()


# ─────────────────────────────────────────────────────────────────────────────
# Per-symbol multi-timeframe fetcher  (used by the scanner)
# ─────────────────────────────────────────────────────────────────────────────

_ALL_TIMEFRAMES = ["5m", "15m", "1h", "1d"]


def fetch_symbol_all_tfs(symbol: str) -> dict[str, pd.DataFrame]:
    """
    Fetch all 4 timeframes for ONE symbol sequentially.
    0.4 s pause between each TF call — same symbol, different interval.
    Returns dict[timeframe → DataFrame].
    """
    result: dict[str, pd.DataFrame] = {}
    for i, tf in enumerate(_ALL_TIMEFRAMES):
        if i > 0:
            _time.sleep(0.2)
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
    "indices": _ALL_INDICES,      # 4 index derivatives
    "stocks":  _ALL_FNO_EQUITY,   # ~62 NSE F&O eligible equities (static fallback)
}

SCAN_UNIVERSE: list[str] = UNIVERSE_PRESETS["stocks"]
INTRADAY_TFS:  list[str] = ["5m", "15m", "1h"]
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


def get_daily(symbol: str, period: str = "6mo") -> pd.DataFrame:
    """Alias: daily OHLCV for backtest use."""
    return get_ohlcv(symbol, interval="1d")
