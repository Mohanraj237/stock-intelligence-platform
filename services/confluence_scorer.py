"""
Confluence scorer — the core brain of both scanners.

Scores each symbol 0-100 across five independent categories:
  1. Trend / Structure   0-30  (normalised: 30 × winning_votes / votes_available)
  2. Momentum            0-25
  3. Volume confirmation 0-15  (excluded entirely for volume-less instruments,
                                with the remaining categories rescaled to 100)
  4. Candle trigger      0-25
  5. Structural bonus    0-5   (chart/price-action Tier-2 confirmed patterns)

Only show setups above threshold (default 65).
Direction is determined from categories 1+2, then validated by the candle.

The five category ceilings above (30/25/15/25/5) are defaults, configurable
per-user via `ScoringWeights` (Settings → Scoring). See `ScoringWeights` and
`_weighted()` below for how a custom weighting keeps the total on a 0-100
scale regardless of what the weights sum to.

Pattern filtering vs. pattern shaping
-------------------------------------
`pattern_mode="filter"` (default) computes the score from the **full** detector
set, so a score means the same thing with or without a pattern selection. The
selection is applied afterwards, by the router, as a hard post-filter.

`pattern_mode="shape"` is the legacy behaviour: non-selected patterns are
stripped before categories 4 and 5 are computed, which lowers scores.

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
from services.pattern_registry import run_detectors, best_for_confluence, PatternResult

log = logging.getLogger(__name__)

# Minimum bars required to score. EMA50 is a trend-vote input, so anything
# shorter would be scored on a systematically smaller vote set than its peers.
MIN_BARS_TO_SCORE = 50

# Timeframes whose bars sit *inside* a trading session (VWAP resets per session).
INTRADAY_TFS: frozenset[str] = frozenset({"1m", "5m", "15m", "30m", "1h", "4h"})
# Timeframes where one bar is a whole session or longer (rolling VWAP).
POSITIONAL_TFS: frozenset[str] = frozenset({"1d", "1wk", "1mo"})

VWAP_ROLLING_BARS = 20

# Reachable maximum per category — used to rescale when a category is excluded,
# and as the reference size each category's internal formula was tuned against
# (see ScoringWeights below).
_CAT_MAX = {"trend": 30, "momentum": 25, "volume": 15, "candle": 25, "structural": 5}
_MAX_WITHOUT_VOLUME = _CAT_MAX["trend"] + _CAT_MAX["momentum"] + _CAT_MAX["candle"] + _CAT_MAX["structural"]


@dataclass(frozen=True)
class ScoringWeights:
    """
    User-configurable category ceilings (Settings → Scoring). Every internal
    sub-formula (RSI bands, MACD split, RelVol tiers, pattern-strength points,
    the contradiction/range penalties) is untouched and still tuned against
    the _CAT_MAX defaults below — a category's raw output is simply rescaled
    by (custom_weight / default_weight) before the categories are summed, and
    the total is then rescaled to 100 regardless of what the weights sum to.
    This keeps every existing "score means the same 0-100 thing" guarantee
    (thresholds, ≥65/≥80 buckets, tests) valid no matter how a user weights
    the five categories.
    """
    trend: int = _CAT_MAX["trend"]
    momentum: int = _CAT_MAX["momentum"]
    volume: int = _CAT_MAX["volume"]
    candle: int = _CAT_MAX["candle"]
    structural: int = _CAT_MAX["structural"]

    @property
    def total_max(self) -> int:
        return self.trend + self.momentum + self.volume + self.candle + self.structural

    @property
    def max_without_volume(self) -> int:
        return self.trend + self.momentum + self.candle + self.structural


DEFAULT_WEIGHTS = ScoringWeights()


def _weighted(raw_pts: float, cat_weight: int, default_max: int) -> float:
    """Rescale a category's raw points (tuned against `default_max`) to the
    user's configured `cat_weight` ceiling."""
    if default_max <= 0:
        return 0.0
    return raw_pts * cat_weight / default_max


# ─────────────────────────────────────────────────────────────────────────────
# Indicator computation (uses the `ta` library already in requirements.txt)
# ─────────────────────────────────────────────────────────────────────────────

def has_real_volume(df: pd.DataFrame) -> bool:
    """True when the instrument actually reports volume (indices do not)."""
    if "volume" not in df.columns:
        return False
    try:
        v = pd.to_numeric(df["volume"], errors="coerce").fillna(0.0)
        return float(v.tail(50).sum()) > 0
    except Exception:
        return False


def _typical_price(df: pd.DataFrame) -> pd.Series:
    return (df["high"] + df["low"] + df["close"]) / 3


def _vwap_rolling(df: pd.DataFrame, window: int = VWAP_ROLLING_BARS) -> pd.Series:
    """
    Rolling N-bar VWAP: Σ(typical_price × volume) / Σ(volume) over the trailing
    `window` bars.

    Used on 1d/1wk/1mo. A session-reset VWAP is meaningless there: each bar is
    its own session, so the "VWAP" collapses to (high+low+close)/3 of that same
    bar and the "Price > VWAP" test degenerates into "did the bar close in the
    upper part of its own range".
    """
    tp  = _typical_price(df)
    vol = pd.to_numeric(df["volume"], errors="coerce").astype(float)
    num = (tp * vol).rolling(window, min_periods=window).sum()
    den = vol.rolling(window, min_periods=window).sum().replace(0, np.nan)
    return num / den


def _session_dates(df: pd.DataFrame, session_tz: str) -> pd.Index:
    """
    Session date for each intraday bar, in the **exchange's** local timezone.

    get_ohlcv() hands us tz-naive timestamps already converted to IST. Grouping
    those by IST calendar date splits a US session (19:00–02:30 IST) across IST
    midnight, resetting VWAP mid-session. Converting to the exchange's own
    timezone first keeps each session in one bucket.
    """
    idx = df.index
    try:
        if getattr(idx, "tz", None) is not None:
            local = idx.tz_convert(session_tz)
        else:
            local = (idx.tz_localize("Asia/Kolkata", nonexistent="shift_forward",
                                     ambiguous="NaT")
                        .tz_convert(session_tz))
        return local.normalize()
    except Exception:
        return idx.normalize()


def _vwap_session(df: pd.DataFrame, session_tz: str = "Asia/Kolkata") -> pd.Series:
    """Session-based VWAP for intraday bars: resets at each session open."""
    try:
        dates = _session_dates(df, session_tz)
        parts: list[pd.Series] = []
        tp  = _typical_price(df)
        vol = pd.to_numeric(df["volume"], errors="coerce").astype(float).replace(0, np.nan)

        for _, mask in df.groupby(dates).groups.items():
            grp_tp  = tp.loc[mask]
            grp_vol = vol.loc[mask]
            cumvol  = grp_vol.cumsum()
            parts.append((grp_tp * grp_vol).cumsum() / cumvol)

        return pd.concat(parts).reindex(df.index)
    except Exception:
        tp = _typical_price(df)
        vol = pd.to_numeric(df["volume"], errors="coerce").astype(float)
        cumvol = vol.cumsum().replace(0, np.nan)
        return (tp * vol).cumsum() / cumvol


def compute_vwap(df: pd.DataFrame, timeframe: str = "",
                 session_tz: str = "Asia/Kolkata") -> pd.Series:
    """
    VWAP appropriate to the timeframe.
      • intraday (5m…4h) → session-reset VWAP, grouped by exchange-local session
      • 1d / 1wk / 1mo   → rolling 20-bar VWAP
      • no real volume   → all-NaN, so the "Price vs VWAP" vote is skipped
    """
    if not has_real_volume(df):
        return pd.Series(np.nan, index=df.index, dtype=float)
    if timeframe in INTRADAY_TFS:
        return _vwap_session(df, session_tz)
    return _vwap_rolling(df)


def add_indicators(df: pd.DataFrame, timeframe: str = "",
                   session_tz: str = "Asia/Kolkata") -> pd.DataFrame:
    """Add EMA20/50, VWAP, RSI, MACD-hist, ATR, RelVol in-place."""
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

    df["vwap"] = compute_vwap(df, timeframe, session_tz)

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
    volume_score: int       # 0-15 (0 and excluded when volume_available is False)
    candle_score: int       # 0-25
    structural_score: int = 0  # 0-5 (chart/price-action Tier-2 bonus)
    pattern: PatternSignal = field(default_factory=lambda: NO_PATTERN)
    spot_price: float = 0.0
    atr: float = 0.0
    rel_vol: float = 1.0
    reasons: list[str] = field(default_factory=list)
    patterns: list[dict] = field(default_factory=list)  # full registry output
    volume_available: bool = True
    bars_used: int = 0
    lookback_note: str = ""


# ─────────────────────────────────────────────────────────────────────────────
# Category 2 helper — RSI, scored relative to the trend direction
# ─────────────────────────────────────────────────────────────────────────────

def rsi_points(rsi: float, trend_dir: str) -> tuple[int, str]:
    """
    RSI contribution (0-12) and a human-readable label.

    The overbought/oversold cliff is a taper, not a step: a bullish setup at
    RSI 72 is not worth a third of one at RSI 69. Points decay linearly from
    12 at RSI 70 to 4 at RSI 80 (mirrored 30 → 20 for bearish).
    """
    if np.isnan(rsi):
        return 0, ""

    if trend_dir == "bullish":
        if rsi >= 80:
            return 4, f"RSI {rsi:.0f} deeply overbought"
        if rsi >= 70:
            return int(round(12 - (rsi - 70) * 0.8)), f"RSI {rsi:.0f} overbought"
        if rsi > 45:
            return 12, f"RSI {rsi:.0f} healthy"
        if rsi > 40:
            return 8, f"RSI {rsi:.0f} building"
        return 4, f"RSI {rsi:.0f} weak"

    if trend_dir == "bearish":
        if rsi <= 20:
            return 4, f"RSI {rsi:.0f} deeply oversold"
        if rsi <= 30:
            return int(round(12 - (30 - rsi) * 0.8)), f"RSI {rsi:.0f} oversold"
        if rsi < 55:
            return 12, f"RSI {rsi:.0f} healthy"
        if rsi < 60:
            return 8, f"RSI {rsi:.0f} rolling over"
        return 4, f"RSI {rsi:.0f} strong (against trend)"

    # range
    if 40 < rsi < 60:
        return 8, f"RSI {rsi:.0f} balanced"
    return 4, f"RSI {rsi:.0f} stretched"


# ─────────────────────────────────────────────────────────────────────────────
# Scorer
# ─────────────────────────────────────────────────────────────────────────────

def score(
    symbol: str,
    df: pd.DataFrame,
    timeframe: str = "",
    enabled_pattern_ids: set[str] | None = None,
    pattern_mode: str = "filter",
    weights: ScoringWeights | None = None,
) -> ConfluenceResult | None:
    """
    Score the last bar of df for a tradeable setup.
    Returns None if data is insufficient (< MIN_BARS_TO_SCORE bars).
    Pass timeframe so the pattern registry uses correct TF gates.

    pattern_mode:
      "filter" — score from the full detector set (default). enabled_pattern_ids
                 is ignored here; the caller applies it as a hard post-filter.
      "shape"  — legacy: only enabled_pattern_ids may contribute to the Candle
                 Trigger (0-25) and Structural bonus (0-5) categories.

    weights: user-configured category ceilings (defaults to DEFAULT_WEIGHTS,
             i.e. today's fixed 30/25/15/25/5 split, when omitted).
    """
    if df.empty or len(df) < MIN_BARS_TO_SCORE:
        log.debug("Skipping %s — only %d bars (need %d)", symbol, len(df), MIN_BARS_TO_SCORE)
        return None

    try:
        return _score(symbol, df, timeframe, enabled_pattern_ids, pattern_mode, weights)
    except Exception as exc:
        log.warning("Scorer error for %s: %s", symbol, exc)
        return None


def _trend_category(df: pd.DataFrame, i: int, reasons: list[str]) -> tuple[str, int]:
    """
    Category 1 — Trend / Structure (0-30).

    A voting system over five possible votes. Points are **normalised** to the
    number of votes that were actually available:

        points = round(30 × winning_votes / votes_available)

    so a symbol whose EMA50 is unavailable is not penalised for it, and the
    category can genuinely reach its stated 30-point maximum.
    """
    last = df.iloc[i]
    close = float(last["close"])
    ema20 = float(last.get("ema_20", np.nan))
    ema50 = float(last.get("ema_50", np.nan))
    vwap  = float(last.get("vwap", np.nan))

    bull_votes = bear_votes = votes_available = 0

    if not np.isnan(ema20):
        votes_available += 1
        if close > ema20:
            bull_votes += 1
            reasons.append("Price>EMA20")
        else:
            bear_votes += 1
            reasons.append("Price<EMA20")

    if not np.isnan(ema50):
        votes_available += 1
        if close > ema50:
            bull_votes += 1
            reasons.append("Price>EMA50")
        else:
            bear_votes += 1
            reasons.append("Price<EMA50")

    if not np.isnan(ema20) and not np.isnan(ema50):
        votes_available += 1
        if ema20 > ema50:
            bull_votes += 1
            reasons.append("EMA20>EMA50")
        else:
            bear_votes += 1
            reasons.append("EMA50>EMA20")

    if not np.isnan(vwap) and vwap > 0:
        votes_available += 1
        if close > vwap:
            bull_votes += 1
            reasons.append("Price>VWAP")
        else:
            bear_votes += 1
            reasons.append("Price<VWAP")

    # Swing structure: new 10-bar high / low. The vote is available whenever the
    # lookback exists; the bar may legitimately abstain by being neither.
    lookback = df.iloc[max(0, i - 10): i]
    if len(lookback) >= 3:
        votes_available += 1
        if float(last["high"]) > lookback["high"].values.max():
            bull_votes += 1
            reasons.append("New 10-bar high")
        elif float(last["low"]) < lookback["low"].values.min():
            bear_votes += 1
            reasons.append("New 10-bar low")

    if votes_available == 0 or bull_votes == bear_votes:
        return "range", 5

    if bull_votes > bear_votes:
        return "bullish", int(round(_CAT_MAX["trend"] * bull_votes / votes_available))
    return "bearish", int(round(_CAT_MAX["trend"] * bear_votes / votes_available))


def _resolve_tf(df: pd.DataFrame, timeframe: str) -> str:
    """
    Guarantee a non-empty timeframe — an empty string makes run_detectors skip
    every chart-pattern detector (their valid_timeframes doesn't include "").
    """
    if timeframe:
        return timeframe
    if len(df) <= 390:      # ≤5d × 78 bars/day → 5m intraday
        return "5m"
    if len(df) <= 480:
        return "15m"
    if len(df) <= 1300:
        return "1h"
    return "1d"


def _score(
    symbol: str,
    df: pd.DataFrame,
    timeframe: str = "",
    enabled_pattern_ids: set[str] | None = None,
    pattern_mode: str = "filter",
    weights: ScoringWeights | None = None,
) -> ConfluenceResult:
    weights = weights or DEFAULT_WEIGHTS
    i = len(df) - 1
    last = df.iloc[i]
    reasons: list[str] = []

    close = float(last["close"])

    # ── Category 1: Trend / Structure (0-30) ────────────────────────────────
    trend_dir, trend_pts = _trend_category(df, i, reasons)

    # ── Category 2: Momentum (0-25) ─────────────────────────────────────────
    rsi       = float(last.get("rsi", np.nan))
    macd_hist = float(last.get("macd_hist", np.nan))
    prev_hist = float(df.iloc[i - 1].get("macd_hist", np.nan)) if i > 0 else np.nan

    momentum_pts, rsi_label = rsi_points(rsi, trend_dir)
    if rsi_label:
        reasons.append(rsi_label)

    if not np.isnan(macd_hist) and not np.isnan(prev_hist):
        if trend_dir == "bullish" and macd_hist > prev_hist:
            momentum_pts += 13
            reasons.append("MACD hist rising")
        elif trend_dir == "bearish" and macd_hist < prev_hist:
            momentum_pts += 13
            reasons.append("MACD hist falling")
        elif abs(macd_hist) > abs(prev_hist):
            momentum_pts += 6

    momentum_pts = min(_CAT_MAX["momentum"], momentum_pts)

    # ── Category 3: Volume (0-15) ────────────────────────────────────────────
    rel_vol = float(last.get("rel_vol", np.nan))
    volume_available = has_real_volume(df) and not np.isnan(rel_vol)
    volume_pts = 0

    if volume_available:
        if rel_vol >= 2.5:
            volume_pts = 15
            reasons.append(f"Vol surge {rel_vol:.1f}×")
        elif rel_vol >= 1.8:
            volume_pts = 11
            reasons.append(f"High vol {rel_vol:.1f}×")
        elif rel_vol >= 1.3:
            volume_pts = 7
            reasons.append(f"Vol above avg {rel_vol:.1f}×")
        else:
            volume_pts = 3
    else:
        reasons.append("No volume data — volume category excluded, score rescaled")

    # ── Category 4: Candle Trigger (0-25) — fed from pattern registry ────────
    _tf = _resolve_tf(df, timeframe)
    all_patterns = run_detectors(df, _tf)

    shaping = pattern_mode == "shape" and bool(enabled_pattern_ids)
    if shaping:
        all_patterns = [
            p for p in all_patterns
            if p.pattern_id in enabled_pattern_ids or p.parent_id in enabled_pattern_ids
        ]

    # ── Category 5: Structural bonus (0-5) ───────────────────────────────────
    structural_fams = {"chart", "price_action"}
    has_structural = any(
        p.family in structural_fams and p.tier == 2 and p.state == "confirmed"
        for p in all_patterns
    )
    structural_pts = 5 if has_structural else 0
    if has_structural:
        reasons.append("Structural pattern confirmed")

    # Pick the best aligned pattern for the candle trigger
    best_reg = best_for_confluence(all_patterns, trend_dir)

    # Convert to PatternSignal for backward-compat scoring logic
    if best_reg is not None:
        pattern = PatternSignal(best_reg.name, best_reg.direction, best_reg.strength)
    elif not shaping:
        # Legacy single-bar detector fallback. Safe under pattern_mode="filter"
        # because the selection is applied afterwards as a hard post-filter, so
        # the fallback can no longer defeat a user's selection.
        pattern = detect(df, i)
    else:
        pattern = NO_PATTERN

    candle_pts = 0
    if pattern.strength > 0:
        if pattern.direction == trend_dir:
            candle_pts = pattern.points
            reasons.append(f"Pattern: {pattern.name}")
        elif trend_dir == "range":
            candle_pts = max(0, pattern.points - 8)
            reasons.append(f"Pattern: {pattern.name}")

    # ── Total & final direction ───────────────────────────────────────────────
    # Rescale each category's raw points (tuned against the _CAT_MAX defaults)
    # to the user's configured weight, then rescale the sum to a 0-100 total
    # regardless of what the configured weights add up to.
    w_trend      = _weighted(trend_pts,      weights.trend,      _CAT_MAX["trend"])
    w_momentum   = _weighted(momentum_pts,   weights.momentum,   _CAT_MAX["momentum"])
    w_volume     = _weighted(volume_pts,     weights.volume,     _CAT_MAX["volume"])
    w_candle     = _weighted(candle_pts,     weights.candle,     _CAT_MAX["candle"])
    w_structural = _weighted(structural_pts, weights.structural, _CAT_MAX["structural"])

    if volume_available:
        raw_weighted = w_trend + w_momentum + w_volume + w_candle + w_structural
        relevant_max = weights.total_max
    else:
        # Volume-less instruments (indices) are scored on the remaining four
        # categories, rescaled to 100 — not handed free neutral points, which
        # would put them on a different basis than stocks at the same threshold.
        w_volume = 0.0
        raw_weighted = w_trend + w_momentum + w_candle + w_structural
        relevant_max = weights.max_without_volume

    scale = 100.0 / relevant_max if relevant_max > 0 else 0.0
    trend_score      = w_trend * scale
    momentum_score   = w_momentum * scale
    volume_score     = w_volume * scale
    candle_score     = w_candle * scale
    structural_score = w_structural * scale
    total: float = trend_score + momentum_score + volume_score + candle_score + structural_score

    if pattern.strength >= 2 and pattern.direction not in (trend_dir, "neutral"):
        total = max(0.0, total - 15)
        reasons.append("Pattern contradicts trend (penalised)")

    if trend_dir == "range" and pattern.direction in ("bullish", "bearish"):
        final_dir = pattern.direction
    else:
        final_dir = trend_dir

    atr = float(last.get("atr", close * 0.005))
    if np.isnan(atr) or atr <= 0:
        atr = close * 0.005

    rv = rel_vol if not np.isnan(rel_vol) else 1.0

    lookback_note = ""
    if len(df) < MIN_BARS_TO_SCORE:
        lookback_note = (
            f"Scored on {len(df)} bars — EMA50 and other 50-bar lookbacks are "
            "incomplete, so trend votes are drawn from a reduced set."
        )

    return ConfluenceResult(
        symbol=symbol,
        direction=final_dir,
        total=int(min(100, max(0, round(total)))),
        trend_score=int(round(trend_score)),
        momentum_score=int(round(momentum_score)),
        volume_score=int(round(volume_score)),
        candle_score=int(round(candle_score)),
        structural_score=int(round(structural_score)),
        pattern=pattern,
        spot_price=close,
        atr=atr,
        rel_vol=rv,
        reasons=reasons,
        patterns=[p.as_dict() for p in all_patterns],
        volume_available=volume_available,
        bars_used=len(df),
        lookback_note=lookback_note,
    )
