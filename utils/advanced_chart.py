"""
Full-featured interactive OHLCV chart using Plotly.
Replaces TradingView widget — same keyboard/mouse interactions.

Keyboard shortcuts work via Plotly modebar:
  - Scroll to zoom, drag to pan, double-click to reset
  - Shift+drag to zoom box, Ctrl+scroll for x-axis zoom only

Features:
  - Candlestick + EMAs + Bollinger Bands
  - Volume bars (green/red)
  - RSI, MACD subplots
  - ATR-based stop loss/target lines
  - Pattern trendline overlays
  - Multiple timeframes via yfinance
  - Crosshair on hover
"""
from __future__ import annotations
from typing import Optional
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from utils.theme import (
    BG, CARD, BORDER, TEXT, TEXT_DIM,
    GREEN, RED, BLUE, YELLOW, ORANGE, PURPLE,
)

# ── Indicator calculators ──────────────────────────────────────────────────────

def _ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()

def _sma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window).mean()

def _rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0).ewm(span=period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(span=period, adjust=False).mean()
    rs = gain / loss.replace(0, float("nan"))
    return 100 - 100 / (1 + rs)

def _macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    fast_ema = _ema(series, fast)
    slow_ema = _ema(series, slow)
    macd_line = fast_ema - slow_ema
    signal_line = _ema(macd_line, signal)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram

def _bollinger(series: pd.Series, window: int = 20, std: float = 2.0):
    mid = _sma(series, window)
    sd = series.rolling(window).std()
    return mid + std * sd, mid, mid - std * sd

def _atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    hi, lo, cl = df["High"], df["Low"], df["Close"]
    tr = pd.concat([hi - lo, (hi - cl.shift()).abs(), (lo - cl.shift()).abs()], axis=1).max(axis=1)
    return tr.ewm(span=period, adjust=False).mean()

def _vwap(df: pd.DataFrame) -> pd.Series:
    tp = (df["High"] + df["Low"] + df["Close"]) / 3
    return (tp * df["Volume"]).cumsum() / df["Volume"].cumsum()


# ── Chart builder ──────────────────────────────────────────────────────────────

def build_ohlcv_chart(
    df: pd.DataFrame,
    symbol: str = "",
    show_ema: bool = True,
    show_bb: bool = False,
    show_vwap: bool = False,
    show_volume: bool = True,
    show_rsi: bool = True,
    show_macd: bool = True,
    patterns: list | None = None,
    support_levels: list[float] | None = None,
    resistance_levels: list[float] | None = None,
    price_target: float | None = None,
    stop_loss: float | None = None,
    height: int = 720,
) -> go.Figure:
    """
    Build a full-featured interactive OHLCV Plotly chart.
    Returns the Figure — caller does st.plotly_chart(fig, use_container_width=True).
    """
    if df is None or df.empty:
        fig = go.Figure()
        fig.update_layout(
            template="plotly_dark", paper_bgcolor=CARD, plot_bgcolor=CARD,
            annotations=[dict(text="No data available", x=0.5, y=0.5,
                              xref="paper", yref="paper", showarrow=False,
                              font=dict(size=18, color=TEXT_DIM))]
        )
        return fig

    df = df.copy().dropna(subset=["Close"])

    # ── Subplot layout ─────────────────────────────────────────────────────────
    rows_needed = 1  # price always
    if show_volume:
        rows_needed += 1
    if show_rsi:
        rows_needed += 1
    if show_macd:
        rows_needed += 1

    row_heights_map = {1: [1.0], 2: [0.6, 0.4], 3: [0.55, 0.2, 0.25], 4: [0.5, 0.17, 0.17, 0.16]}
    row_heights = row_heights_map.get(rows_needed, [0.5] + [0.17] * (rows_needed - 1))

    subplot_titles = [symbol or "Price"]
    row_map = {"price": 1}
    next_row = 2
    if show_volume:
        subplot_titles.append("Volume")
        row_map["volume"] = next_row
        next_row += 1
    if show_rsi:
        subplot_titles.append("RSI (14)")
        row_map["rsi"] = next_row
        next_row += 1
    if show_macd:
        subplot_titles.append("MACD (12,26,9)")
        row_map["macd"] = next_row

    fig = make_subplots(
        rows=rows_needed, cols=1,
        shared_xaxes=True,
        row_heights=row_heights,
        vertical_spacing=0.025,
        subplot_titles=subplot_titles,
    )

    close = df["Close"]
    idx = df.index

    # ── Candlestick ────────────────────────────────────────────────────────────
    fig.add_trace(go.Candlestick(
        x=idx, open=df["Open"], high=df["High"], low=df["Low"], close=close,
        increasing=dict(line=dict(color=GREEN, width=1), fillcolor=GREEN),
        decreasing=dict(line=dict(color=RED, width=1), fillcolor=RED),
        name=symbol or "Price",
        hovertext=[
            f"O: {o:.2f}  H: {h:.2f}  L: {l:.2f}  C: {c:.2f}<br>Chg: {((c-o)/o*100):+.2f}%"
            for o, h, l, c in zip(df["Open"], df["High"], df["Low"], close)
        ],
        hoverinfo="x+text",
        showlegend=False,
    ), row=1, col=1)

    # ── EMAs ──────────────────────────────────────────────────────────────────
    if show_ema:
        ema_configs = [
            (9,  "#f59e0b", "EMA 9"),
            (20, "#2962ff", "EMA 20"),
            (50, "#26a69a", "EMA 50"),
            (200, "#9c27b0", "EMA 200"),
        ]
        for span, color, name in ema_configs:
            if len(close) >= span:
                fig.add_trace(go.Scatter(
                    x=idx, y=_ema(close, span), name=name,
                    line=dict(color=color, width=1.2),
                    opacity=0.85, hoverinfo="skip",
                ), row=1, col=1)

    # ── Bollinger Bands ────────────────────────────────────────────────────────
    if show_bb and len(close) >= 20:
        bb_upper, bb_mid, bb_lower = _bollinger(close)
        fig.add_trace(go.Scatter(
            x=idx, y=bb_upper, name="BB Upper",
            line=dict(color=BLUE, width=1, dash="dot"), opacity=0.5, hoverinfo="skip",
        ), row=1, col=1)
        fig.add_trace(go.Scatter(
            x=idx, y=bb_lower, name="BB Lower", fill="tonexty",
            fillcolor="rgba(41,98,255,0.05)",
            line=dict(color=BLUE, width=1, dash="dot"), opacity=0.5, hoverinfo="skip",
        ), row=1, col=1)

    # ── VWAP ──────────────────────────────────────────────────────────────────
    if show_vwap and "Volume" in df.columns:
        try:
            vwap = _vwap(df)
            fig.add_trace(go.Scatter(
                x=idx, y=vwap, name="VWAP",
                line=dict(color=ORANGE, width=1.3, dash="dash"), hoverinfo="skip",
            ), row=1, col=1)
        except Exception:
            pass

    # ── Price Target / Stop Loss lines ────────────────────────────────────────
    if price_target:
        fig.add_hline(y=price_target, line_color=GREEN, line_dash="dash", line_width=1.5,
                      annotation_text=f"Target ₹{price_target:,.2f}",
                      annotation_position="right",
                      annotation_font_color=GREEN, row=1, col=1)
    if stop_loss:
        fig.add_hline(y=stop_loss, line_color=RED, line_dash="dash", line_width=1.5,
                      annotation_text=f"Stop ₹{stop_loss:,.2f}",
                      annotation_position="right",
                      annotation_font_color=RED, row=1, col=1)

    # ── Support / Resistance ──────────────────────────────────────────────────
    for lvl in (support_levels or []):
        fig.add_hline(y=lvl, line_color=GREEN, line_dash="dot", line_width=1,
                      opacity=0.6, row=1, col=1)
    for lvl in (resistance_levels or []):
        fig.add_hline(y=lvl, line_color=RED, line_dash="dot", line_width=1,
                      opacity=0.6, row=1, col=1)

    # ── Pattern trendlines ────────────────────────────────────────────────────
    for pat in (patterns or []):
        d = pat.get("direction", "neutral") if isinstance(pat, dict) else "neutral"
        lc = GREEN if d == "bullish" else RED if d == "bearish" else YELLOW
        for ln in (pat.get("lines", []) if isinstance(pat, dict) else []):
            if not isinstance(ln, dict):
                continue
            try:
                fig.add_shape(
                    type="line",
                    x0=str(ln["x0"]), y0=float(ln["y0"]),
                    x1=str(ln["x1"]), y1=float(ln["y1"]),
                    line=dict(color=ln.get("color", lc), width=1.8, dash=ln.get("dash", "dot")),
                    xref="x", yref="y",
                )
            except Exception:
                pass

    # ── Volume ────────────────────────────────────────────────────────────────
    if show_volume and "volume" in row_map:
        vol_row = row_map["volume"]
        vol_colors = [GREEN if c >= o else RED for c, o in zip(close, df["Open"])]
        fig.add_trace(go.Bar(
            x=idx, y=df["Volume"], name="Volume",
            marker_color=vol_colors, opacity=0.7,
            hovertemplate="Vol: %{y:,.0f}<extra></extra>",
            showlegend=False,
        ), row=vol_row, col=1)
        # Volume MA20
        if len(df) >= 20:
            fig.add_trace(go.Scatter(
                x=idx, y=_sma(df["Volume"], 20), name="Vol MA20",
                line=dict(color=YELLOW, width=1), hoverinfo="skip",
            ), row=vol_row, col=1)

    # ── RSI ───────────────────────────────────────────────────────────────────
    if show_rsi and "rsi" in row_map and len(close) >= 15:
        rsi_row = row_map["rsi"]
        rsi_vals = _rsi(close)
        # Color RSI line by zone
        fig.add_trace(go.Scatter(
            x=idx, y=rsi_vals, name="RSI",
            line=dict(color=ORANGE, width=1.5),
            hovertemplate="RSI: %{y:.1f}<extra></extra>",
        ), row=rsi_row, col=1)
        fig.add_hrect(y0=70, y1=100, fillcolor="rgba(239,83,80,0.07)",
                       line_width=0, row=rsi_row, col=1)
        fig.add_hrect(y0=0, y1=30, fillcolor="rgba(38,166,154,0.07)",
                       line_width=0, row=rsi_row, col=1)
        fig.add_hline(y=70, line_dash="dot", line_color=RED, line_width=1, row=rsi_row, col=1)
        fig.add_hline(y=30, line_dash="dot", line_color=GREEN, line_width=1, row=rsi_row, col=1)
        fig.add_hline(y=50, line_dash="dot", line_color=BORDER, line_width=0.5, row=rsi_row, col=1)
        fig.update_yaxes(range=[0, 100], row=rsi_row, col=1)

    # ── MACD ──────────────────────────────────────────────────────────────────
    if show_macd and "macd" in row_map and len(close) >= 27:
        macd_row = row_map["macd"]
        macd_line, signal_line, hist = _macd(close)
        hist_colors = [GREEN if v >= 0 else RED for v in hist.fillna(0)]
        fig.add_trace(go.Bar(
            x=idx, y=hist, name="MACD Hist",
            marker_color=hist_colors, opacity=0.6,
            hovertemplate="Hist: %{y:.3f}<extra></extra>",
            showlegend=False,
        ), row=macd_row, col=1)
        fig.add_trace(go.Scatter(
            x=idx, y=macd_line, name="MACD",
            line=dict(color=BLUE, width=1.4),
            hovertemplate="MACD: %{y:.3f}<extra></extra>",
        ), row=macd_row, col=1)
        fig.add_trace(go.Scatter(
            x=idx, y=signal_line, name="Signal",
            line=dict(color=ORANGE, width=1.2),
            hovertemplate="Signal: %{y:.3f}<extra></extra>",
        ), row=macd_row, col=1)
        fig.add_hline(y=0, line_dash="dot", line_color=BORDER, line_width=0.5, row=macd_row, col=1)

    # ── Global layout ──────────────────────────────────────────────────────────
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor=CARD,
        plot_bgcolor=CARD,
        height=height,
        margin=dict(l=10, r=60, t=30, b=10),
        hovermode="x unified",
        legend=dict(
            orientation="h", yanchor="bottom", y=1.01, xanchor="left", x=0,
            bgcolor="rgba(0,0,0,0)", font=dict(size=11),
        ),
        xaxis_rangeslider_visible=False,
        # Crosshair cursor
        xaxis=dict(
            gridcolor=BORDER, linecolor=BORDER,
            showspikes=True, spikecolor=TEXT_DIM, spikethickness=1,
            spikedash="dot", spikemode="across",
            tickfont=dict(color=TEXT_DIM, size=10),
        ),
        yaxis=dict(
            gridcolor=BORDER, linecolor=BORDER,
            showspikes=True, spikecolor=TEXT_DIM, spikethickness=1,
            spikedash="dot", spikemode="across",
            tickfont=dict(color=TEXT_DIM, size=10),
            side="right",
            tickprefix="₹",
        ),
        font=dict(color=TEXT),
        dragmode="zoom",
        # Modebar buttons: zoom, pan, reset, crosshair toggle, download
        modebar=dict(
            bgcolor="rgba(0,0,0,0)",
            color=TEXT_DIM,
            activecolor=BLUE,
        ),
    )

    # All subplot y-axes: right-side ticks, no prefix on non-price rows
    for row in range(2, rows_needed + 1):
        fig.update_yaxes(
            side="right",
            gridcolor=BORDER, linecolor=BORDER,
            tickfont=dict(color=TEXT_DIM, size=10),
            row=row, col=1,
        )
        fig.update_xaxes(
            gridcolor=BORDER, linecolor=BORDER,
            tickfont=dict(color=TEXT_DIM, size=10),
            showspikes=True, spikecolor=TEXT_DIM, spikethickness=1,
            spikedash="dot", spikemode="across",
            row=row, col=1,
        )

    # Subplot title font
    for ann in fig.layout.annotations:
        ann.update(font=dict(color=TEXT_DIM, size=11))

    return fig


def render_ohlcv_chart(
    df: pd.DataFrame,
    symbol: str = "",
    show_ema: bool = True,
    show_bb: bool = False,
    show_vwap: bool = False,
    show_rsi: bool = True,
    show_macd: bool = True,
    patterns: list | None = None,
    price_target: float | None = None,
    stop_loss: float | None = None,
    height: int = 720,
    key: str = "ohlcv_chart",
) -> None:
    """Streamlit wrapper — renders controls + Plotly chart."""
    import streamlit as st

    # ── Indicator toggles ──────────────────────────────────────────────────────
    with st.container():
        c1, c2, c3, c4, c5 = st.columns(5)
        show_ema  = c1.checkbox("EMA Lines",   value=show_ema,  key=f"{key}_ema")
        show_bb   = c2.checkbox("Bollinger",    value=show_bb,   key=f"{key}_bb")
        show_vwap = c3.checkbox("VWAP",         value=show_vwap, key=f"{key}_vwap")
        show_rsi  = c4.checkbox("RSI",          value=show_rsi,  key=f"{key}_rsi")
        show_macd = c5.checkbox("MACD",         value=show_macd, key=f"{key}_macd")

    fig = build_ohlcv_chart(
        df=df, symbol=symbol,
        show_ema=show_ema, show_bb=show_bb, show_vwap=show_vwap,
        show_volume=True, show_rsi=show_rsi, show_macd=show_macd,
        patterns=patterns, price_target=price_target, stop_loss=stop_loss,
        height=height,
    )

    st.plotly_chart(
        fig,
        use_container_width=True,
        config={
            "scrollZoom": True,           # mouse wheel zoom
            "displayModeBar": True,
            "modeBarButtonsToAdd": [
                "drawline", "drawopenpath", "drawclosedpath",
                "drawcircle", "drawrect", "eraseshape",
            ],
            "modeBarButtonsToRemove": ["toImage"],
            "displaylogo": False,
        },
    )
