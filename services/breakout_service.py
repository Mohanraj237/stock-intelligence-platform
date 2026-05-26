"""
Breakout-state classifier.

Given a stock's OHLCV at a specific timeframe, classify the latest candle's
position relative to the most relevant breakout level (52-bar high/low,
recent swing pivot, or pattern target):

  VERGE_BREAKOUT       — within 2 % of the level, momentum building
  FRESH_BREAKOUT       — broke through in the last 1 candle
  CONFIRMED_BREAKOUT   — broke through 2-5 candles ago, holding above
  EXTENDED             — broke through > 5 candles ago, may be late
  NO_BREAKOUT          — comfortably inside range / nothing close
  VERGE_BREAKDOWN / FRESH_BREAKDOWN / CONFIRMED_BREAKDOWN — bearish equivalents

Per-timeframe rules (per the user's spec):
  - 1d → expects "confirmed breakout" (held for at least 2 days)
  - 1w → expects "fresh / single-candle breakout"
  - 1mo → "confirmed"
"""
from __future__ import annotations
from typing import Optional


# ── Constants ────────────────────────────────────────────────────────────────
VERGE_BREAKOUT       = "VERGE_BREAKOUT"
FRESH_BREAKOUT       = "FRESH_BREAKOUT"
CONFIRMED_BREAKOUT   = "CONFIRMED_BREAKOUT"
EXTENDED             = "EXTENDED"
NO_BREAKOUT          = "NO_BREAKOUT"
VERGE_BREAKDOWN      = "VERGE_BREAKDOWN"
FRESH_BREAKDOWN      = "FRESH_BREAKDOWN"
CONFIRMED_BREAKDOWN  = "CONFIRMED_BREAKDOWN"

BULLISH_STATES = {VERGE_BREAKOUT, FRESH_BREAKOUT, CONFIRMED_BREAKOUT, EXTENDED}
BEARISH_STATES = {VERGE_BREAKDOWN, FRESH_BREAKDOWN, CONFIRMED_BREAKDOWN}

STATE_COLOR = {
    VERGE_BREAKOUT:      "#f5c542",   # yellow — about to break
    FRESH_BREAKOUT:      "#26a69a",   # green — just broke
    CONFIRMED_BREAKOUT:  "#1ec48a",   # bright green — confirmed
    EXTENDED:            "#94a3b8",   # dim — late
    NO_BREAKOUT:         "#94a3b8",
    VERGE_BREAKDOWN:     "#f5c542",
    FRESH_BREAKDOWN:     "#ef5350",
    CONFIRMED_BREAKDOWN: "#d32f2f",
}

STATE_LABEL = {
    VERGE_BREAKOUT:      "Verge of breakout",
    FRESH_BREAKOUT:      "Fresh breakout (1 candle)",
    CONFIRMED_BREAKOUT:  "Confirmed breakout",
    EXTENDED:            "Extended (late entry)",
    NO_BREAKOUT:         "No breakout",
    VERGE_BREAKDOWN:     "Verge of breakdown",
    FRESH_BREAKDOWN:     "Fresh breakdown",
    CONFIRMED_BREAKDOWN: "Confirmed breakdown",
}


# ── Per-timeframe expectations ───────────────────────────────────────────────
TIMEFRAME_RULES = {
    "1d":  {"preferred": [CONFIRMED_BREAKOUT, FRESH_BREAKOUT], "label": "Confirmed (≥ 2 d)"},
    "1w":  {"preferred": [FRESH_BREAKOUT],                    "label": "Single-candle breakout"},
    "1mo": {"preferred": [CONFIRMED_BREAKOUT],                "label": "Confirmed monthly"},
}


# ── Helper: locate the relevant breakout level ───────────────────────────────
def _find_breakout_level(df, lookback_for_high: int = 60) -> Optional[float]:
    """
    Return the most recent significant resistance level: the highest high
    over the lookback window EXCLUDING the last bar (so we can detect a
    real break of that level on the latest candles).
    """
    if df is None or len(df) < lookback_for_high + 5:
        # Use whatever we have
        if df is None or len(df) < 10:
            return None
        return float(df["High"].iloc[:-1].max())
    return float(df["High"].iloc[-(lookback_for_high + 1):-1].max())


def _find_breakdown_level(df, lookback: int = 60) -> Optional[float]:
    if df is None or len(df) < lookback + 5:
        if df is None or len(df) < 10:
            return None
        return float(df["Low"].iloc[:-1].min())
    return float(df["Low"].iloc[-(lookback + 1):-1].min())


# ── Main classifier ──────────────────────────────────────────────────────────
def classify_breakout(df, level_override: Optional[float] = None,
                       direction: str = "auto") -> dict:
    """
    Classify the breakout state for the latest candle.

    Args:
        df: pandas DataFrame with Open/High/Low/Close/Volume
        level_override: pass a custom level (e.g. pattern's resistance) instead
            of letting the function find a 60-bar high
        direction: "long", "short", or "auto" (try both, return strongest)

    Returns:
        {
          state, label, color, level, current_price, distance_pct,
          bars_since_breakout, volume_confirmed
        }
    """
    if df is None or len(df) < 10:
        return _empty_result()

    last = float(df["Close"].iloc[-1])
    last_high = float(df["High"].iloc[-1])
    last_low  = float(df["Low"].iloc[-1])

    # ── BREAKOUT side ──
    res_level = level_override if direction != "short" else None
    if res_level is None and direction != "short":
        res_level = _find_breakout_level(df)

    breakout_state = NO_BREAKOUT
    bars_since_breakout = 0
    if res_level and last_high > 0:
        dist_pct = (last - res_level) / res_level * 100
        if -2 <= dist_pct < 0:
            breakout_state = VERGE_BREAKOUT
        elif dist_pct >= 0:
            # Find how many bars ago the close first crossed res_level
            closes = df["Close"].astype(float).values
            for k in range(1, min(len(closes), 30)):
                if closes[-k - 1] <= res_level < closes[-k]:
                    bars_since_breakout = k
                    break
            else:
                # Already extended
                bars_since_breakout = 30
            if bars_since_breakout == 1:
                breakout_state = FRESH_BREAKOUT
            elif 2 <= bars_since_breakout <= 5:
                breakout_state = CONFIRMED_BREAKOUT
            elif bars_since_breakout > 5:
                breakout_state = EXTENDED

    # ── BREAKDOWN side (if direction allows) ──
    breakdown_state = NO_BREAKOUT
    bars_since_breakdown = 0
    sup_level = None
    if direction != "long":
        sup_level = _find_breakdown_level(df)
        if sup_level and last_low > 0:
            dist_pct_down = (last - sup_level) / sup_level * 100
            if 0 < dist_pct_down <= 2:
                breakdown_state = VERGE_BREAKDOWN
            elif dist_pct_down <= 0:
                closes = df["Close"].astype(float).values
                for k in range(1, min(len(closes), 30)):
                    if closes[-k - 1] >= sup_level > closes[-k]:
                        bars_since_breakdown = k
                        break
                else:
                    bars_since_breakdown = 30
                if bars_since_breakdown == 1:
                    breakdown_state = FRESH_BREAKDOWN
                elif 2 <= bars_since_breakdown <= 5:
                    breakdown_state = CONFIRMED_BREAKDOWN
                else:
                    breakdown_state = CONFIRMED_BREAKDOWN  # collapse extended-down into confirmed

    # ── Pick stronger side ──
    if direction == "long":
        state = breakout_state
        level = res_level
        bars  = bars_since_breakout
    elif direction == "short":
        state = breakdown_state
        level = sup_level
        bars  = bars_since_breakdown
    else:
        # auto: prioritise non-NO_BREAKOUT
        if breakout_state != NO_BREAKOUT and breakdown_state == NO_BREAKOUT:
            state, level, bars = breakout_state, res_level, bars_since_breakout
        elif breakdown_state != NO_BREAKOUT and breakout_state == NO_BREAKOUT:
            state, level, bars = breakdown_state, sup_level, bars_since_breakdown
        else:
            # both quiet or both active — prefer the non-extended side
            if breakout_state in (FRESH_BREAKOUT, CONFIRMED_BREAKOUT, VERGE_BREAKOUT):
                state, level, bars = breakout_state, res_level, bars_since_breakout
            elif breakdown_state in (FRESH_BREAKDOWN, CONFIRMED_BREAKDOWN, VERGE_BREAKDOWN):
                state, level, bars = breakdown_state, sup_level, bars_since_breakdown
            else:
                state, level, bars = NO_BREAKOUT, res_level, 0

    # ── Volume confirmation ──
    volume_confirmed = False
    if "Volume" in df.columns and len(df) >= 21:
        vols = df["Volume"].astype(float).values
        avg20 = vols[-21:-1].mean() or 1
        recent = vols[-1] if state in (FRESH_BREAKOUT, FRESH_BREAKDOWN) else vols[-min(bars, 5):].mean()
        volume_confirmed = bool(recent > avg20 * 1.4)

    distance_pct = None
    if level and level > 0:
        distance_pct = (last - level) / level * 100

    return {
        "state":           state,
        "label":           STATE_LABEL.get(state, state),
        "color":           STATE_COLOR.get(state, "#94a3b8"),
        "level":           round(level, 2) if level else None,
        "current_price":   round(last, 2),
        "distance_pct":    round(distance_pct, 2) if distance_pct is not None else None,
        "bars_since_breakout": bars,
        "volume_confirmed": volume_confirmed,
        "is_bullish":       state in BULLISH_STATES,
        "is_bearish":       state in BEARISH_STATES,
    }


def _empty_result() -> dict:
    return {
        "state": NO_BREAKOUT, "label": "Insufficient data", "color": "#94a3b8",
        "level": None, "current_price": None, "distance_pct": None,
        "bars_since_breakout": 0, "volume_confirmed": False,
        "is_bullish": False, "is_bearish": False,
    }


# ── Convenience: classify across multiple timeframes ─────────────────────────
def classify_multi_timeframe(symbol: str, fetch_fn) -> dict:
    """
    Run the classifier across 1d / 1w / 1mo for a single symbol.
    `fetch_fn(period, interval)` should return a DataFrame.

    Returns dict {tf_label: classification_dict, "_overall": "..."}
    """
    out = {}
    plans = [
        ("1d",  "1y",  "1d"),
        ("1w",  "5y",  "1W"),
        ("1mo", "max", "1M"),
    ]
    for label, period, interval in plans:
        try:
            df = fetch_fn(symbol, period, interval)
            if df is None or len(df) < 30:
                out[label] = _empty_result()
                continue
            out[label] = classify_breakout(df)
        except Exception:
            out[label] = _empty_result()

    # Per the user's spec, derive an "ideal-setup" overall flag
    daily = out.get("1d", {})
    weekly = out.get("1w", {})
    overall = "—"
    if (daily.get("state") == CONFIRMED_BREAKOUT and weekly.get("state") == FRESH_BREAKOUT
        and daily.get("is_bullish") and weekly.get("is_bullish")):
        overall = "🟢 Ideal swing-buy setup (1d confirmed + 1w fresh)"
    elif daily.get("state") in (FRESH_BREAKOUT, CONFIRMED_BREAKOUT) and weekly.get("is_bullish"):
        overall = "🟢 Bullish breakout in progress"
    elif daily.get("state") == VERGE_BREAKOUT or weekly.get("state") == VERGE_BREAKOUT:
        overall = "🟡 Approaching breakout — watch closely"
    elif daily.get("is_bearish") and weekly.get("is_bearish"):
        overall = "🔴 Bearish breakdown across timeframes"
    out["_overall"] = overall
    return out
