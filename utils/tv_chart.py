"""
TradingView-style charting using the open-source Lightweight Charts library
(via `streamlit-lightweight-charts`).

Why a new module? The previous Plotly charts had several issues — deprecated
API surface (titlefont etc.), heavy DOM weight on large universes, and a
non-trader-friendly look. Lightweight Charts is what TradingView themselves
use for their fast-loading widgets — same crosshair, candlestick rendering,
panes, and time scaling.

Public API:
    render_tv_chart(df, ...) -> renders a candlestick + volume chart
    render_pattern_chart(df, patterns, ...) -> with trendline overlays
"""
from __future__ import annotations
import logging
import time
from typing import Optional, Iterable

import pandas as pd
import streamlit as st

try:
    from streamlit_lightweight_charts import renderLightweightCharts
    _HAS_LWC = True
except ImportError:
    _HAS_LWC = False

logger = logging.getLogger(__name__)

# ── Theme matching the app's Zerodha dark palette ────────────────────────────
CHART_THEME = {
    "layout": {
        "background": {"type": "solid", "color": "#131722"},
        "textColor": "#94a3b8",
    },
    "grid": {
        "vertLines": {"color": "#1e293b"},
        "horzLines": {"color": "#1e293b"},
    },
    "rightPriceScale": {"borderColor": "#1e293b"},
    "timeScale": {"borderColor": "#1e293b", "timeVisible": True, "secondsVisible": False},
    "crosshair": {"mode": 1},   # 1 = magnet
}

UP_COLOR   = "#26a69a"
DOWN_COLOR = "#ef5350"


# ── Helpers ──────────────────────────────────────────────────────────────────
def _df_to_candle_data(df: pd.DataFrame) -> list:
    """Convert OHLCV DataFrame → Lightweight Charts candlestick payload."""
    out = []
    for ts, row in df.iterrows():
        try:
            t = ts.strftime("%Y-%m-%d") if hasattr(ts, "strftime") else str(ts)[:10]
            out.append({
                "time": t,
                "open":  float(row["Open"]),
                "high":  float(row["High"]),
                "low":   float(row["Low"]),
                "close": float(row["Close"]),
            })
        except Exception:
            continue
    return out


def _df_to_volume_data(df: pd.DataFrame) -> list:
    out = []
    if "Volume" not in df.columns:
        return out
    for ts, row in df.iterrows():
        try:
            t = ts.strftime("%Y-%m-%d") if hasattr(ts, "strftime") else str(ts)[:10]
            color = UP_COLOR if row["Close"] >= row["Open"] else DOWN_COLOR
            out.append({"time": t, "value": float(row["Volume"]), "color": color})
        except Exception:
            continue
    return out


def _line_data(df: pd.DataFrame, series: pd.Series) -> list:
    out = []
    for ts, val in zip(df.index, series):
        try:
            if pd.isna(val):
                continue
            t = ts.strftime("%Y-%m-%d") if hasattr(ts, "strftime") else str(ts)[:10]
            out.append({"time": t, "value": float(val)})
        except Exception:
            continue
    return out


# ── Public API ───────────────────────────────────────────────────────────────
def render_tv_chart(
    df: pd.DataFrame,
    symbol: str = "",
    height: int = 480,
    show_volume: bool = True,
    show_emas: Iterable[int] = (20, 50, 200),
    entry: Optional[float] = None,
    target: Optional[float] = None,
    stop: Optional[float] = None,
    key_levels: Optional[dict] = None,
    pattern_lines: Optional[list] = None,
    title: str = "",
    key_suffix: str = "",
):
    """
    Render a TradingView-style candlestick chart inside Streamlit.

    Args:
        df: pandas OHLCV DataFrame indexed by Date
        symbol: stock symbol (used for chart title)
        show_volume: render a 25%-height volume pane below price
        show_emas: tuple of EMA periods to overlay (e.g. (20, 50, 200))
        entry / target / stop: horizontal price lines drawn on the chart
        key_levels: dict like {"support": 1200, "resistance": 1300}
        pattern_lines: list of {x0, y0, x1, y1, color, dash} dicts
        title: optional chart title (default uses symbol)
    """
    if df is None or df.empty:
        st.warning("No OHLCV data to render.")
        return

    if not _HAS_LWC:
        st.error("`streamlit-lightweight-charts` not installed. "
                 "Run: pip install streamlit-lightweight-charts")
        return

    candles = _df_to_candle_data(df)
    if not candles:
        st.warning("OHLCV data could not be converted for charting.")
        return

    # ── Build series list ────────────────────────────────────────────────────
    series: list = []

    # Candlestick (always)
    series.append({
        "type": "Candlestick",
        "data": candles,
        "options": {
            "upColor":         UP_COLOR,
            "downColor":       DOWN_COLOR,
            "borderUpColor":   UP_COLOR,
            "borderDownColor": DOWN_COLOR,
            "wickUpColor":     UP_COLOR,
            "wickDownColor":   DOWN_COLOR,
        },
    })

    # EMA overlays
    closes = df["Close"].astype(float)
    ema_colors = {20: "#2962ff", 50: "#ff9800", 100: "#7e57c2", 200: "#9c27b0"}
    for span in show_emas:
        if len(closes) >= span:
            ema = closes.ewm(span=span, adjust=False).mean()
            series.append({
                "type": "Line",
                "data": _line_data(df, ema),
                "options": {
                    "color":      ema_colors.get(span, "#94a3b8"),
                    "lineWidth":  1,
                    "title":      f"EMA{span}",
                    "priceLineVisible": False,
                    "lastValueVisible": False,
                    "crosshairMarkerVisible": False,
                },
            })

    # ── Price-line overlays (entry / target / stop / pattern key levels) ─────
    price_lines = []
    if entry is not None:
        price_lines.append({"price": float(entry), "color": "#2962ff",
                            "lineWidth": 2, "lineStyle": 0, "title": f"Entry {entry:.2f}"})
    if target is not None:
        price_lines.append({"price": float(target), "color": UP_COLOR,
                            "lineWidth": 2, "lineStyle": 2, "title": f"Target {target:.2f}"})
    if stop is not None:
        price_lines.append({"price": float(stop), "color": DOWN_COLOR,
                            "lineWidth": 2, "lineStyle": 2, "title": f"Stop {stop:.2f}"})
    if key_levels:
        if key_levels.get("support"):
            price_lines.append({"price": float(key_levels["support"]),
                                "color": UP_COLOR, "lineWidth": 1, "lineStyle": 1,
                                "title": "Support"})
        if key_levels.get("resistance"):
            price_lines.append({"price": float(key_levels["resistance"]),
                                "color": DOWN_COLOR, "lineWidth": 1, "lineStyle": 1,
                                "title": "Resistance"})

    if price_lines:
        # Attach to the candlestick series
        series[0]["priceLines"] = price_lines

    # ── Pattern trendlines as separate Line series ───────────────────────────
    if pattern_lines:
        for ln in pattern_lines:
            try:
                line_pts = [
                    {"time": str(ln["x0"])[:10], "value": float(ln["y0"])},
                    {"time": str(ln["x1"])[:10], "value": float(ln["y1"])},
                ]
                series.append({
                    "type": "Line",
                    "data": line_pts,
                    "options": {
                        "color":     ln.get("color", "#f5c542"),
                        "lineWidth": 2,
                        "lineStyle": 2 if ln.get("dash") == "dot" else 0,
                        "title":     ln.get("label", ""),
                        "priceLineVisible": False,
                        "lastValueVisible": False,
                        "crosshairMarkerVisible": False,
                    },
                })
            except Exception:
                continue

    # ── Volume pane ───────────────────────────────────────────────────────────
    charts_payload: list = []

    chart_options = dict(CHART_THEME)
    chart_options["height"] = max(height - (110 if show_volume else 0), 240)
    if title or symbol:
        chart_options["watermark"] = {
            "visible": True, "fontSize": 18, "horzAlign": "left",
            "vertAlign": "top", "color": "rgba(148, 163, 184, 0.18)",
            "text": title or symbol,
        }

    charts_payload.append({"chart": chart_options, "series": series})

    if show_volume:
        vol_data = _df_to_volume_data(df)
        if vol_data:
            vol_options = dict(CHART_THEME)
            vol_options["height"] = 110
            vol_options["timeScale"] = dict(CHART_THEME["timeScale"])
            charts_payload.append({
                "chart": vol_options,
                "series": [{
                    "type": "Histogram",
                    "data": vol_data,
                    "options": {
                        "priceFormat": {"type": "volume"},
                        "priceScaleId": "",
                    },
                    "priceScale": {"scaleMargins": {"top": 0.1, "bottom": 0.0}},
                }],
            })

    # Unique key per render
    chart_key = f"tv_{symbol}_{key_suffix}_{int(time.time()*1000) % 1000000}"
    try:
        renderLightweightCharts(charts_payload, key=chart_key)
    except Exception as e:
        logger.warning(f"lightweight-charts render failed: {e}")
        st.error(f"Chart render failed: {e}")
