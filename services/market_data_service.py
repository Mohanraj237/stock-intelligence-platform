"""
Market data service for NSE / BSE.

Sources:
  - NSE India  -> live quotes, index constituents, market status (services/nse_service)
  - Yahoo Finance -> OHLCV history (no API key needed)
  - `ta` library -> RSI / MACD / EMA / SMA / ADX / BB / Stochastic / CCI / ATR

This module replaces the previous TradingView-backed service. No external
data licence or session cookie is required. All function names that the
rest of the codebase imports are preserved for backwards compatibility,
so existing pages continue to work unchanged.
"""
from __future__ import annotations
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, Dict, Any, List

import requests as _requests

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Symbol normalisation
# ─────────────────────────────────────────────────────────────────────────────
def normalize_symbol(symbol: str) -> str:
    return symbol.upper().strip().replace(".NS", "").replace(".BO", "").replace("-EQ", "")


# ─────────────────────────────────────────────────────────────────────────────
# OHLCV history (Yahoo Finance)
# ─────────────────────────────────────────────────────────────────────────────
_YAHOO_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}


def get_ohlcv_history(
    symbol: str,
    period: str = "1y",
    interval: str = "1d",
) -> Optional[Any]:
    """
    Fetch OHLCV history from Yahoo Finance.
    Returns pandas DataFrame with columns Open, High, Low, Close, Volume
    indexed by Date.
    """
    try:
        import pandas as pd
        clean = normalize_symbol(symbol)
        yahoo_sym = f"{clean}.NS"

        period_map = {"1m": "1mo", "3m": "3mo", "6m": "6mo", "1y": "1y",
                      "2y": "2y", "5y": "5y", "max": "max", "3mo": "3mo",
                      "6mo": "6mo", "1mo": "1mo"}
        interval_map = {"1D": "1d", "1d": "1d",
                        "1W": "1wk", "1w": "1wk", "1wk": "1wk",
                        "1M": "1mo", "1mo": "1mo"}

        yf_period = period_map.get(period, "1y")
        yf_interval = interval_map.get(interval, "1d")

        sess = _requests.Session()
        sess.headers.update(_YAHOO_HEADERS)
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_sym}"
        params = {"interval": yf_interval, "range": yf_period, "includeAdjustedClose": "true"}
        resp = sess.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        result = data["chart"]["result"][0]
        ts = result["timestamp"]
        ohlcv = result["indicators"]["quote"][0]
        dates = pd.to_datetime(ts, unit="s", utc=True).tz_convert("Asia/Kolkata").tz_localize(None)
        df = pd.DataFrame({
            "Open":   ohlcv.get("open", []),
            "High":   ohlcv.get("high", []),
            "Low":    ohlcv.get("low", []),
            "Close":  ohlcv.get("close", []),
            "Volume": ohlcv.get("volume", []),
        }, index=dates)
        df.index.name = "Date"
        df = df.dropna(subset=["Close"])
        return df
    except Exception as e:
        logger.warning(f"OHLCV history failed for {symbol}: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Indicator computation (using `ta` library)
# ─────────────────────────────────────────────────────────────────────────────
def _compute_indicators(df) -> dict:
    """Compute the same set of indicators previously sourced from TradingView."""
    if df is None or len(df) < 5:
        return {}
    try:
        import ta
        c = df["Close"]
        h = df["High"]
        l = df["Low"]
        v = df.get("Volume")

        ind: Dict[str, Optional[float]] = {
            "open":   float(df["Open"].iloc[-1]),
            "high":   float(h.iloc[-1]),
            "low":    float(l.iloc[-1]),
            "close":  float(c.iloc[-1]),
            "volume": float(v.iloc[-1]) if v is not None and len(v) else None,
            "change": float((c.iloc[-1] - c.iloc[-2]) / c.iloc[-2] * 100) if len(c) > 1 else 0.0,
        }

        if len(c) >= 14:
            ind["rsi"] = float(ta.momentum.RSIIndicator(c, window=14).rsi().iloc[-1])
            macd = ta.trend.MACD(c)
            ind["macd"] = float(macd.macd().iloc[-1])
            ind["macd_signal"] = float(macd.macd_signal().iloc[-1])
            ind["macd_hist"] = float(macd.macd_diff().iloc[-1])
            adx = ta.trend.ADXIndicator(h, l, c)
            ind["adx"] = float(adx.adx().iloc[-1])
            ind["adx_pos"] = float(adx.adx_pos().iloc[-1])
            ind["adx_neg"] = float(adx.adx_neg().iloc[-1])
            atr = ta.volatility.AverageTrueRange(h, l, c)
            ind["atr"] = float(atr.average_true_range().iloc[-1])
        if len(c) >= 20:
            ind["sma20"] = float(ta.trend.SMAIndicator(c, window=20).sma_indicator().iloc[-1])
            ind["ema20"] = float(ta.trend.EMAIndicator(c, window=20).ema_indicator().iloc[-1])
            bb = ta.volatility.BollingerBands(c)
            ind["bb_upper"] = float(bb.bollinger_hband().iloc[-1])
            ind["bb_lower"] = float(bb.bollinger_lband().iloc[-1])
            ind["bb_mid"]   = float(bb.bollinger_mavg().iloc[-1])
            stoch = ta.momentum.StochasticOscillator(h, l, c)
            ind["stoch_k"] = float(stoch.stoch().iloc[-1])
            ind["stoch_d"] = float(stoch.stoch_signal().iloc[-1])
            ind["cci20"]   = float(ta.trend.CCIIndicator(h, l, c, window=20).cci().iloc[-1])
        if len(c) >= 50:
            ind["sma50"] = float(ta.trend.SMAIndicator(c, window=50).sma_indicator().iloc[-1])
            ind["ema50"] = float(ta.trend.EMAIndicator(c, window=50).ema_indicator().iloc[-1])
        if len(c) >= 100:
            ind["sma100"] = float(ta.trend.SMAIndicator(c, window=100).sma_indicator().iloc[-1])
            ind["ema100"] = float(ta.trend.EMAIndicator(c, window=100).ema_indicator().iloc[-1])
        if len(c) >= 200:
            ind["sma200"] = float(ta.trend.SMAIndicator(c, window=200).sma_indicator().iloc[-1])
            ind["ema200"] = float(ta.trend.EMAIndicator(c, window=200).ema_indicator().iloc[-1])

        # Strip NaN
        return {k: (None if (val is not None and val != val) else val) for k, val in ind.items()}
    except Exception as e:
        logger.debug(f"Indicator computation failed: {e}")
        return {}


# ─────────────────────────────────────────────────────────────────────────────
# Recommendation derivation (from indicators)
# ─────────────────────────────────────────────────────────────────────────────
def _derive_recommendation(ind: dict) -> str:
    """Aggregate indicators into STRONG_BUY / BUY / NEUTRAL / SELL / STRONG_SELL."""
    if not ind:
        return "NEUTRAL"
    score = 0
    rsi = ind.get("rsi")
    macd = ind.get("macd")
    macd_sig = ind.get("macd_signal")
    close = ind.get("close")
    sma50 = ind.get("sma50")
    sma200 = ind.get("sma200")
    ema20 = ind.get("ema20")
    adx = ind.get("adx")
    adx_pos = ind.get("adx_pos")
    adx_neg = ind.get("adx_neg")

    if rsi is not None:
        if rsi < 30: score += 2
        elif rsi < 45: score += 1
        elif rsi > 70: score -= 2
        elif rsi > 55: score += 1
    if macd is not None and macd_sig is not None:
        if macd > macd_sig: score += 1
        else: score -= 1
        if macd > 0: score += 1
        else: score -= 1
    if close and ema20 and close > ema20: score += 1
    elif close and ema20: score -= 1
    if close and sma50 and close > sma50: score += 1
    elif close and sma50: score -= 1
    if close and sma200 and close > sma200: score += 2
    elif close and sma200: score -= 2
    if adx and adx > 25 and adx_pos and adx_neg:
        if adx_pos > adx_neg: score += 1
        else: score -= 1

    if score >= 6: return "STRONG_BUY"
    if score >= 3: return "BUY"
    if score <= -6: return "STRONG_SELL"
    if score <= -3: return "SELL"
    return "NEUTRAL"


# ─────────────────────────────────────────────────────────────────────────────
# Single-symbol analysis (replaces get_tv_analysis)
# ─────────────────────────────────────────────────────────────────────────────
def get_market_analysis(symbol: str, interval: str = "1d") -> Optional[Dict[str, Any]]:
    """Fetch OHLCV for `symbol`, compute indicators, derive recommendation."""
    period = "1y" if interval == "1d" else "2y"
    df = get_ohlcv_history(symbol, period=period, interval=interval)
    if df is None or df.empty:
        return None
    ind = _compute_indicators(df)
    rec = _derive_recommendation(ind)
    return {
        "symbol": normalize_symbol(symbol),
        "exchange": "NSE",
        "interval": interval,
        "recommendation": rec,
        "indicators": ind,
        "fetched_at": time.time(),
        "source": "Yahoo Finance + computed",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Bulk scanner (replaces scan_symbols_bulk)
# ─────────────────────────────────────────────────────────────────────────────
def scan_market_bulk(
    symbols: List[str],
    exchange: str = "NSE",
    max_workers: int = 8,
) -> Dict[str, Dict]:
    """
    Parallel OHLCV fetch + indicator computation for many symbols.
    Returns dict keyed by clean symbol, same shape as the old TV bulk scanner.
    """
    if not symbols:
        return {}
    out: Dict[str, Dict] = {}

    def _worker(sym: str):
        try:
            data = get_market_analysis(sym, interval="1d")
            return sym, data
        except Exception as e:
            logger.debug(f"scan_market_bulk worker failed for {sym}: {e}")
            return sym, None

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = {ex.submit(_worker, normalize_symbol(s)): s for s in symbols}
        for fut in as_completed(futs):
            sym, data = fut.result()
            if data:
                out[sym] = data
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Recommendation → score (used by Scanner / Universe Explorer for sorting)
# ─────────────────────────────────────────────────────────────────────────────
def score_signal(recommendation: str) -> int:
    return {"STRONG_BUY": 100, "BUY": 80, "NEUTRAL": 50,
            "SELL": 25, "STRONG_SELL": 5}.get(str(recommendation).upper(), 50)
