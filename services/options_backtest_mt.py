"""
Options Buying Backtest — Madras Trader strategy.

Simulates the strategy on historical daily data WITHOUT lookahead bias:
  • For each date, score is built from data available UP TO that date only.
  • Entry: open of the next session after signal.
  • Exit: when option premium hits 2.5× (target) or 0.65× (SL), or DTE ≤ 2.
  • Premium is modelled via Black-Scholes on the historical price series.

Returns a structured result dict with trades, stats, heatmaps, and insights.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

try:
    import yfinance as yf
    _YF_OK = True
except ImportError:
    _YF_OK = False

try:
    from scipy.stats import norm
    _SCIPY_OK = True
except ImportError:
    _SCIPY_OK = False

RISK_FREE = 0.065   # RBI repo rate proxy

# ── Black-Scholes option pricing ─────────────────────────────────────────────

def _bs_price(S: float, K: float, T: float, sigma: float, option: str = "CE") -> float:
    if not _SCIPY_OK or T <= 0 or sigma <= 0:
        intrinsic = max(S - K, 0) if option == "CE" else max(K - S, 0)
        return intrinsic
    d1 = (np.log(S / K) + (RISK_FREE + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    if option == "CE":
        return float(S * norm.cdf(d1) - K * np.exp(-RISK_FREE * T) * norm.cdf(d2))
    return float(K * np.exp(-RISK_FREE * T) * norm.cdf(-d2) - S * norm.cdf(-d1))


# ── EMA helpers (no pandas_ta dependency) ────────────────────────────────────

def _ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def _daily_score(df_slice: pd.DataFrame, direction: str) -> int:
    """
    Quickly score a daily slice using available data only (no lookahead).
    Returns 0–100 composite score (simplified version of the full scorer).
    """
    if len(df_slice) < 22:
        return 0

    close = df_slice["Close"]
    e20   = _ema(close, 20)
    e50   = _ema(close, 50) if len(df_slice) >= 50 else e20
    last  = float(close.iloc[-1])
    v20   = float(e20.iloc[-1])
    v50   = float(e50.iloc[-1])

    score = 0
    is_ce = direction == "CE"

    # Trend (0–25)
    if is_ce and last > v20 > v50:
        score += 20
    elif not is_ce and last < v20 < v50:
        score += 20
    elif (is_ce and last > v20) or (not is_ce and last < v20):
        score += 10

    # Momentum: RSI in ideal zone (0–15)
    d = close.diff()
    g  = d.where(d > 0, 0.0).ewm(span=14, adjust=False).mean()
    ls = (-d.where(d < 0, 0.0)).ewm(span=14, adjust=False).mean()
    rsi = float((100 - 100 / (1 + g / (ls + 1e-10))).iloc[-1])
    if is_ce and 45 < rsi < 70:
        score += 15
    elif not is_ce and 30 < rsi < 55:
        score += 15
    elif is_ce and 70 <= rsi <= 80:
        score += 8
    elif not is_ce and 20 <= rsi <= 30:
        score += 8

    # Volume (0–10)
    if "Volume" in df_slice.columns:
        vol_avg = df_slice["Volume"].iloc[:-1].mean()
        vol_last = float(df_slice["Volume"].iloc[-1])
        if vol_last > vol_avg * 1.5:
            score += 10
        elif vol_last > vol_avg * 1.2:
            score += 5

    # PDH/PDL breakout (0–15)
    if len(df_slice) >= 2:
        pdh = float(df_slice["High"].iloc[-2])
        pdl = float(df_slice["Low"].iloc[-2])
        if is_ce and last > pdh:
            score += 15
        elif not is_ce and last < pdl:
            score += 15

    # HHHL / LHLL structure (0–10)
    if len(df_slice) >= 10:
        hi = df_slice["High"].values[-10:]
        lo = df_slice["Low"].values[-10:]
        if is_ce and hi[-1] > hi[-5] and lo[-1] > lo[-5]:
            score += 10
        elif not is_ce and hi[-1] < hi[-5] and lo[-1] < lo[-5]:
            score += 10

    # Engulfing candle (0–25)
    if len(df_slice) >= 2:
        o = df_slice["Open"].values
        c = df_slice["Close"].values
        if is_ce and c[-2] < o[-2] and c[-1] > o[-1] and c[-1] > o[-2] and o[-1] < c[-2]:
            score += 25
        elif not is_ce and c[-2] > o[-2] and c[-1] < o[-1] and c[-1] < o[-2] and o[-1] > c[-2]:
            score += 25

    return min(100, score)


# ── Backtest core ─────────────────────────────────────────────────────────────

def backtest_mt_strategy(
    symbol:       str,
    lookback_days: int = 90,
    min_score:    int  = 70,
) -> dict:
    """
    Walk-forward simulation of the MT options buying strategy.

    Steps per day:
    1. Score CE and PE setups using data up to that day (no lookahead).
    2. If score >= min_score: simulate option buy at next open.
    3. Model option price with Black-Scholes (σ from 20-day historical vol).
    4. Exit at 2.5× premium (target), 0.65× premium (SL), or DTE ≤ 2.
    """
    if not _YF_OK:
        return {"error": "yfinance not installed — pip install yfinance"}

    from services.mtf_analyzer import _INDEX_MAP
    ticker = _INDEX_MAP.get(symbol.upper(), f"{symbol.upper()}.NS")

    # Download ~1 year of daily data (need lookback + warmup)
    total_days = lookback_days + 120  # extra for indicator warmup
    try:
        df = yf.download(
            ticker, period=f"{total_days}d", interval="1d",
            progress=False, auto_adjust=True,
        )
    except Exception as exc:
        return {"error": f"yfinance download failed: {exc}"}

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.dropna(subset=["Close", "High", "Low", "Open"]).copy()

    if len(df) < 60:
        return {"error": "Insufficient historical data for backtest"}

    # Use only the relevant lookback window (plus 60-day warmup)
    start_idx = max(60, len(df) - lookback_days - 60)
    df = df.iloc[start_idx:].reset_index(drop=False)

    trades = []
    open_trade: Optional[dict] = None
    warmup = 60  # days before we start simulating

    for i in range(warmup, len(df)):
        row   = df.iloc[i]
        today = row["Date"] if "Date" in df.columns else row.get("index", datetime.now())

        # ── Close open trade if exit conditions met ──────────────────────────
        if open_trade:
            cur_price  = float(row["Close"])
            sigma_hist = float(df["Close"].iloc[max(0, i-20):i].pct_change().std() * np.sqrt(252))
            sigma_hist = max(sigma_hist, 0.08)
            K          = open_trade["strike"]
            dte        = (open_trade["expiry_date"] - today).days if hasattr(today, "date") else open_trade["dte_at_entry"]
            dte        = max(dte, 0)
            T          = dte / 365.0

            cur_premium = _bs_price(cur_price, K, T, sigma_hist, open_trade["option_type"])
            entry_prem  = open_trade["entry_premium"]

            exit_reason = None
            if cur_premium >= entry_prem * 2.5:
                exit_reason = "TARGET"
                exit_premium = entry_prem * 2.5
            elif cur_premium <= entry_prem * 0.65:
                exit_reason = "STOP_LOSS"
                exit_premium = entry_prem * 0.65
            elif dte <= 2:
                exit_reason = "DTE_EXPIRY"
                exit_premium = cur_premium

            if exit_reason:
                pnl_pct = (exit_premium - entry_prem) / entry_prem * 100
                open_trade["exit_date"]    = today.strftime("%Y-%m-%d") if hasattr(today, "strftime") else str(today)
                open_trade["exit_premium"] = round(exit_premium, 2)
                open_trade["pnl_pct"]      = round(pnl_pct, 2)
                open_trade["exit_reason"]  = exit_reason
                open_trade["win"]          = pnl_pct > 0
                trades.append(open_trade)
                open_trade = None

        # ── Score today's setup ───────────────────────────────────────────────
        if open_trade:
            continue

        df_slice = df.iloc[max(0, i-120):i+1]

        # Score CE and PE, pick best direction
        ce_score = _daily_score(df_slice, "CE")
        pe_score = _daily_score(df_slice, "PE")
        best_dir  = "CE" if ce_score >= pe_score else "PE"
        best_score = max(ce_score, pe_score)

        if best_score < min_score:
            continue

        # Build simulated option trade
        spot = float(row["Close"])
        sigma_hist = float(df["Close"].iloc[max(0, i-20):i].pct_change().std() * np.sqrt(252))
        sigma_hist = max(sigma_hist, 0.08)

        # ATM strike (round to nearest 50 for indices, 20 for stocks)
        interval  = 50 if spot > 5000 else 20
        atm_strike = round(spot / interval) * interval

        # DTE: assume nearest 7-day expiry
        dte_target = 10
        expiry_date = today + timedelta(days=dte_target) if hasattr(today, "__add__") else datetime.now() + timedelta(days=dte_target)
        T = dte_target / 365.0

        premium = _bs_price(spot, atm_strike, T, sigma_hist, best_dir)
        if premium < 5:
            continue

        entry_date = df.iloc[i+1]["Date"] if i + 1 < len(df) else today
        open_trade = {
            "symbol":         symbol,
            "option_type":    best_dir,
            "strike":         atm_strike,
            "spot_at_signal": round(spot, 2),
            "score":          best_score,
            "entry_date":     entry_date.strftime("%Y-%m-%d") if hasattr(entry_date, "strftime") else str(entry_date),
            "entry_premium":  round(premium, 2),
            "expiry_date":    expiry_date,
            "dte_at_entry":   dte_target,
            "exit_date":      None,
            "exit_premium":   None,
            "pnl_pct":        None,
            "exit_reason":    None,
            "win":            None,
        }

    # ── Build stats ───────────────────────────────────────────────────────────
    completed = [t for t in trades if t["pnl_pct"] is not None]
    if not completed:
        return {
            "symbol": symbol, "lookback_days": lookback_days,
            "min_score": min_score, "total_trades": 0,
            "win_rate": 0, "avg_return": 0, "profit_factor": 0,
            "max_win": 0, "max_loss": 0, "trades": [], "error": None,
        }

    pnls     = [t["pnl_pct"] for t in completed]
    wins     = [p for p in pnls if p > 0]
    losses   = [p for p in pnls if p <= 0]
    win_rate = len(wins) / len(pnls) * 100

    gross_profit = sum(wins)
    gross_loss   = abs(sum(losses))
    profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else float("inf")

    # Monthly heatmap: month → win_rate, avg_pnl
    monthly_stats: dict[str, dict] = {}
    for t in completed:
        try:
            m = t["entry_date"][:7]  # YYYY-MM
            monthly_stats.setdefault(m, {"pnls": []})
            monthly_stats[m]["pnls"].append(t["pnl_pct"])
        except Exception:
            pass
    heatmap = [
        {
            "month": m,
            "trades": len(v["pnls"]),
            "win_rate": round(sum(1 for p in v["pnls"] if p > 0) / len(v["pnls"]) * 100, 1),
            "avg_pnl": round(sum(v["pnls"]) / len(v["pnls"]), 1),
        }
        for m, v in sorted(monthly_stats.items())
    ]

    # Pattern performance summary
    exit_reasons = {}
    for t in completed:
        er = t["exit_reason"] or "UNKNOWN"
        exit_reasons.setdefault(er, {"count": 0, "total_pnl": 0})
        exit_reasons[er]["count"] += 1
        exit_reasons[er]["total_pnl"] += t["pnl_pct"]

    # Serialise trades (remove expiry_date datetime object)
    serialised_trades = []
    for t in completed:
        tc = dict(t)
        if hasattr(tc.get("expiry_date"), "strftime"):
            tc["expiry_date"] = tc["expiry_date"].strftime("%Y-%m-%d")
        serialised_trades.append(tc)

    return {
        "symbol":         symbol,
        "lookback_days":  lookback_days,
        "min_score":      min_score,
        "total_trades":   len(completed),
        "win_rate":       round(win_rate, 1),
        "avg_return":     round(sum(pnls) / len(pnls), 1),
        "max_win":        round(max(pnls), 1),
        "max_loss":       round(min(pnls), 1),
        "profit_factor":  profit_factor,
        "total_return":   round(sum(pnls), 1),
        "heatmap":        heatmap,
        "exit_breakdown": [
            {"reason": k, "count": v["count"], "avg_pnl": round(v["total_pnl"] / v["count"], 1)}
            for k, v in exit_reasons.items()
        ],
        "trades":  serialised_trades[-30:],   # last 30 for UI
        "error":   None,
    }
