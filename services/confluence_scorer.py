"""
Confluence scorer — the core brain of the live scanner.

Scores each symbol 0-100 across four independent categories:
  1. Trend / Structure   0-30
  2. Momentum            0-25
  3. Volume confirmation 0-20
  4. Candle trigger      0-25

Only show setups above threshold (default 65).
Direction is determined from categories 1+2, then validated by the candle.

Indicator pre-requisites (expected columns from ta library or manual calc):
  ema_20, ema_50, vwap, rsi, macd_hist, atr, rel_vol
  (all added by add_indicators() in this module)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import ta

from services.pattern_detector import PatternSignal, detect, NO_PATTERN

log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Indicator computation (uses the `ta` library already in requirements.txt)
# ─────────────────────────────────────────────────────────────────────────────

def _vwap_daily(df: pd.DataFrame) -> pd.Series:
    """
    Session-based VWAP: resets at the start of each trading day.
    Groups bars by calendar date and computes cumulative VWAP within each session.
    Safe for daily (1d) DataFrames too — each bar becomes its own "session".
    """
    try:
        idx = df.index
        if hasattr(idx, "tz") and idx.tz is not None:
            dates = idx.tz_convert("Asia/Kolkata").normalize()
        else:
            dates = idx.normalize()

        parts: list[pd.Series] = []
        tp = (df["high"] + df["low"] + df["close"]) / 3
        vol = df["volume"].replace(0, np.nan)

        for _, mask in df.groupby(dates).groups.items():
            grp_tp  = tp.loc[mask]
            grp_vol = vol.loc[mask]
            cumvol  = grp_vol.cumsum()
            vwap_g  = (grp_tp * grp_vol).cumsum() / cumvol
            parts.append(vwap_g)

        return pd.concat(parts).reindex(df.index)
    except Exception:
        # fallback: simple cumulative VWAP if grouping fails
        tp = (df["high"] + df["low"] + df["close"]) / 3
        cumvol = df["volume"].cumsum().replace(0, np.nan)
        return (tp * df["volume"]).cumsum() / cumvol


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Add EMA20/50, VWAP (session-reset), RSI, MACD-hist, ATR, RelVol in-place."""
    if df.empty or len(df) < 5:
        return df

    c  = df["close"]
    h  = df["high"]
    lo = df["low"]
    v  = df["volume"]

    # EMA — ta library computes from first bar; valid from bar N onward
    if len(c) >= 20:
        df["ema_20"] = ta.trend.EMAIndicator(c, window=20).ema_indicator()
    if len(c) >= 50:
        df["ema_50"] = ta.trend.EMAIndicator(c, window=50).ema_indicator()

    # Session-based VWAP
    df["vwap"] = _vwap_daily(df)

    # RSI
    if len(c) >= 14:
        df["rsi"] = ta.momentum.RSIIndicator(c, window=14).rsi()

    # MACD histogram
    if len(c) >= 26:
        macd = ta.trend.MACD(c)
        df["macd_hist"] = macd.macd_diff()

    # ATR
    if len(c) >= 14:
        df["atr"] = ta.volatility.AverageTrueRange(h, lo, c).average_true_range()

    # Relative volume vs 20-bar rolling average
    if len(c) >= 20:
        avg_vol = v.rolling(20).mean().replace(0, np.nan)
        df["rel_vol"] = v / avg_vol

    return df


# ─────────────────────────────────────────────────────────────────────────────
# Result dataclass
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ConfluenceResult:
    symbol: str
    direction: str          # "bullish" | "bearish" | "range"
    total: int              # 0-100
    trend_score: int        # 0-30
    momentum_score: int     # 0-25
    volume_score: int       # 0-20
    candle_score: int       # 0-25
    pattern: PatternSignal = field(default_factory=lambda: NO_PATTERN)
    spot_price: float = 0.0
    atr: float = 0.0
    rel_vol: float = 1.0
    reasons: list[str] = field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
# Scorer
# ─────────────────────────────────────────────────────────────────────────────

def score(symbol: str, df: pd.DataFrame) -> ConfluenceResult | None:
    """
    Score the last bar of df for a tradeable setup.
    Returns None if data is insufficient (< 30 bars).
    """
    if df.empty or len(df) < 20:
        log.debug("Skipping %s — only %d bars", symbol, len(df))
        return None

    try:
        return _score(symbol, df)
    except Exception as exc:
        log.warning("Scorer error for %s: %s", symbol, exc)
        return None


def _score(symbol: str, df: pd.DataFrame) -> ConfluenceResult:
    i = len(df) - 1
    last = df.iloc[i]
    reasons: list[str] = []

    close = float(last["close"])

    # ── Category 1: Trend / Structure (0-30) ────────────────────────────────
    ema20 = float(last.get("ema_20", np.nan))
    ema50 = float(last.get("ema_50", np.nan))
    vwap  = float(last.get("vwap", np.nan))

    bull_votes = bear_votes = 0

    if not np.isnan(ema20):
        if close > ema20:
            bull_votes += 1
            reasons.append("Price>EMA20")
        else:
            bear_votes += 1
            reasons.append("Price<EMA20")

    if not np.isnan(ema50):
        if close > ema50:
            bull_votes += 1
            reasons.append("Price>EMA50")
        else:
            bear_votes += 1
            reasons.append("Price<EMA50")

    if not np.isnan(ema20) and not np.isnan(ema50):
        if ema20 > ema50:
            bull_votes += 1
            reasons.append("EMA20>EMA50")
        else:
            bear_votes += 1
            reasons.append("EMA50>EMA20")

    if not np.isnan(vwap) and vwap > 0:
        if close > vwap:
            bull_votes += 1
            reasons.append("Price>VWAP")
        else:
            bear_votes += 1
            reasons.append("Price<VWAP")

    # Swing structure: higher-highs / higher-lows (last 10 bars)
    lookback = df.iloc[max(0, i - 10): i]
    if len(lookback) >= 3:
        recent_highs = lookback["high"].values
        recent_lows  = lookback["low"].values
        if float(last["high"]) > recent_highs.max():
            bull_votes += 1
            reasons.append("New 10-bar high")
        elif float(last["low"]) < recent_lows.min():
            bear_votes += 1
            reasons.append("New 10-bar low")

    if bull_votes > bear_votes:
        trend_dir  = "bullish"
        trend_pts  = min(30, bull_votes * 5)
    elif bear_votes > bull_votes:
        trend_dir  = "bearish"
        trend_pts  = min(30, bear_votes * 5)
    else:
        trend_dir  = "range"
        trend_pts  = 5

    # ── Category 2: Momentum (0-25) ─────────────────────────────────────────
    rsi       = float(last.get("rsi", np.nan))
    macd_hist = float(last.get("macd_hist", np.nan))
    prev_hist = float(df.iloc[i - 1].get("macd_hist", np.nan)) if i > 0 else np.nan

    momentum_pts = 0

    if not np.isnan(rsi):
        if trend_dir == "bullish":
            if 45 < rsi < 70:
                momentum_pts += 12
                reasons.append(f"RSI {rsi:.0f} healthy")
            elif rsi >= 70:
                momentum_pts += 4
                reasons.append(f"RSI {rsi:.0f} overbought")
            elif rsi > 50:
                momentum_pts += 8
        elif trend_dir == "bearish":
            if 30 < rsi < 55:
                momentum_pts += 12
                reasons.append(f"RSI {rsi:.0f} healthy")
            elif rsi <= 30:
                momentum_pts += 4
                reasons.append(f"RSI {rsi:.0f} oversold")
            elif rsi < 50:
                momentum_pts += 8
        else:
            momentum_pts += 8 if 40 < rsi < 60 else 4

    if not np.isnan(macd_hist) and not np.isnan(prev_hist):
        if trend_dir == "bullish" and macd_hist > prev_hist:
            momentum_pts += 13
            reasons.append("MACD hist rising")
        elif trend_dir == "bearish" and macd_hist < prev_hist:
            momentum_pts += 13
            reasons.append("MACD hist falling")
        elif abs(macd_hist) > abs(prev_hist):
            momentum_pts += 6

    momentum_pts = min(25, momentum_pts)

    # ── Category 3: Volume (0-20) ────────────────────────────────────────────
    rel_vol = float(last.get("rel_vol", np.nan))
    volume_pts = 0

    if not np.isnan(rel_vol):
        if rel_vol >= 2.5:
            volume_pts = 20
            reasons.append(f"Vol surge {rel_vol:.1f}×")
        elif rel_vol >= 1.8:
            volume_pts = 15
            reasons.append(f"High vol {rel_vol:.1f}×")
        elif rel_vol >= 1.3:
            volume_pts = 10
            reasons.append(f"Vol above avg {rel_vol:.1f}×")
        else:
            volume_pts = 4
    else:
        volume_pts = 8  # no volume data (index) — neutral score

    # ── Category 4: Candle Trigger (0-25) ────────────────────────────────────
    pattern = detect(df, i)
    candle_pts = 0

    if pattern.strength > 0:
        if pattern.direction == trend_dir:
            candle_pts = pattern.points   # full credit when aligned
            reasons.append(f"Pattern: {pattern.name}")
        elif trend_dir == "range":
            candle_pts = max(0, pattern.points - 8)
            reasons.append(f"Pattern: {pattern.name}")
        # opposite direction → 0 pts (contradicts trend)

    # ── Total & final direction ───────────────────────────────────────────────
    total = trend_pts + momentum_pts + volume_pts + candle_pts

    # If pattern direction contradicts trend direction significantly, penalise
    if pattern.strength >= 2 and pattern.direction not in (trend_dir, "neutral"):
        total = max(0, total - 15)
        reasons.append("Pattern contradicts trend (penalised)")

    # Consolidate direction: pattern can upgrade "range"
    if trend_dir == "range" and pattern.direction in ("bullish", "bearish"):
        final_dir = pattern.direction
    else:
        final_dir = trend_dir

    atr = float(last.get("atr", close * 0.005))
    if np.isnan(atr) or atr <= 0:
        atr = close * 0.005  # 0.5% fallback

    rv = rel_vol if not np.isnan(rel_vol) else 1.0

    return ConfluenceResult(
        symbol=symbol,
        direction=final_dir,
        total=int(min(100, max(0, total))),
        trend_score=int(trend_pts),
        momentum_score=int(momentum_pts),
        volume_score=int(volume_pts),
        candle_score=int(candle_pts),
        pattern=pattern,
        spot_price=close,
        atr=atr,
        rel_vol=rv,
        reasons=reasons,
    )
