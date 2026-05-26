from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from concurrent.futures import ThreadPoolExecutor, as_completed


from utils.theme import apply_theme, GREEN, RED, BLUE, CARD, BORDER, TEXT, TEXT_DIM, SYM_COLORS, SYM_COLORS_A
apply_theme()

from services.universe_sync import get_universe_symbols, get_all_universe_names, universe_display_map
from services.tradingview_service import scan_symbols_bulk, get_tv_ohlcv_history
from services.screener_service import get_full_screener_data
from storage.cache_manager import get_cached, set_cached, TTL

st.markdown("## ⚖️ Stock Comparator")

# ── Index + Stock Selection ────────────────────────────────────────────────────
disp_map = universe_display_map()
all_names = get_all_universe_names()
labels = [disp_map.get(n, n) for n in all_names]

c_idx, c_stocks, c_period = st.columns([2, 3, 1])

with c_idx:
    sel_label = st.selectbox("Index / Universe", labels, key="cmp_idx")
    sel_universe = all_names[labels.index(sel_label)]

@st.cache_data(ttl=3600, show_spinner=False)
def _get_syms(u):
    return get_universe_symbols(u)

index_syms = _get_syms(sel_universe)

with c_stocks:
    symbols = st.multiselect(
        "Select up to 6 stocks",
        index_syms,
        default=index_syms[:4] if len(index_syms) >= 4 else index_syms[:2],
        max_selections=6,
        key="cmp_stocks",
    )

with c_period:
    comp_period = st.selectbox("Period", ["3mo", "6mo", "1y", "2y"], index=2, key="cmp_period")

if not symbols:
    st.info("Select at least one stock above.")
    st.stop()

# ── Data Fetchers ──────────────────────────────────────────────────────────────
@st.cache_data(ttl=TTL.get("tv_analysis", 300), show_spinner=False)
def _load_tv(syms_key: str) -> dict:
    return scan_symbols_bulk(syms_key.split(","))

@st.cache_data(ttl=TTL.get("screener", 3600), show_spinner=False)
def _load_screener(sym: str) -> dict:
    cached = get_cached("screener", sym)
    if cached:
        return cached
    data = get_full_screener_data(sym)
    if data:
        set_cached("screener", sym, data)
    return data or {}

@st.cache_data(ttl=TTL.get("tv_history", 600), show_spinner=False)
def _load_ohlcv(sym: str, period: str):
    try:
        return get_tv_ohlcv_history(sym, period=period, interval="1d")
    except Exception:
        return None

def _parallel_screener(syms):
    results = {}
    with ThreadPoolExecutor(max_workers=4) as ex:
        futs = {ex.submit(_load_screener, s): s for s in syms}
        for fut in as_completed(futs):
            s = futs[fut]
            try:
                results[s] = fut.result()
            except Exception:
                results[s] = {}
    return results

def _parallel_ohlcv(syms, period):
    results = {}
    with ThreadPoolExecutor(max_workers=4) as ex:
        futs = {ex.submit(_load_ohlcv, s, period): s for s in syms}
        for fut in as_completed(futs):
            s = futs[fut]
            try:
                results[s] = fut.result()
            except Exception:
                results[s] = None
    return results

# ── Auto-load on symbol change ─────────────────────────────────────────────────
syms_key = ",".join(symbols)
prev_key = st.session_state.get("_cmp_key", "")
if syms_key != prev_key or "cmp_tv" not in st.session_state:
    with st.spinner(f"Loading {', '.join(symbols)}..."):
        tv_bulk = _load_tv(syms_key)
        screener_all = _parallel_screener(symbols)
        ohlcv_all = _parallel_ohlcv(symbols, comp_period)
    st.session_state.update({
        "cmp_tv": tv_bulk, "cmp_screener": screener_all,
        "cmp_ohlcv": ohlcv_all, "_cmp_key": syms_key,
    })

tv_bulk      = st.session_state.get("cmp_tv", {})
screener_all = st.session_state.get("cmp_screener", {})
ohlcv_all    = st.session_state.get("cmp_ohlcv", {})

sym_color  = {s: SYM_COLORS[i % len(SYM_COLORS)]  for i, s in enumerate(symbols)}
sym_color_a = {s: SYM_COLORS_A[i % len(SYM_COLORS_A)] for i, s in enumerate(symbols)}

st.markdown("---")

# ═══════════════════════════════════════════════════════════════════════════════
# SECTION A: Price Performance
# ═══════════════════════════════════════════════════════════════════════════════
st.markdown('<div class="z-section">Price Performance (Normalized, Base 100)</div>', unsafe_allow_html=True)

try:
    fig_perf = go.Figure()
    for sym in symbols:
        df_s = ohlcv_all.get(sym)
        if df_s is None or df_s.empty:
            continue
        close = df_s["Close"].astype(float).dropna()
        if close.empty:
            continue
        norm = (close / close.iloc[0]) * 100
        fig_perf.add_trace(go.Scatter(
            x=close.index, y=norm, name=sym,
            line=dict(color=sym_color[sym], width=2), mode="lines",
        ))
    fig_perf.update_layout(
        template="plotly_dark", paper_bgcolor=CARD, plot_bgcolor=CARD,
        height=380, hovermode="x unified",
        legend=dict(orientation="h", y=1.05, bgcolor=CARD),
        margin=dict(t=20, b=20, l=10, r=10),
        xaxis=dict(gridcolor=BORDER), yaxis=dict(gridcolor=BORDER, title="Indexed (Base=100)"),
    )
    st.plotly_chart(fig_perf, use_container_width=True)
except Exception as e:
    st.warning(f"Price chart error: {e}")

st.markdown("---")

# ═══════════════════════════════════════════════════════════════════════════════
# SECTION B: Fundamental Comparison
# ═══════════════════════════════════════════════════════════════════════════════
st.markdown('<div class="z-section">Fundamental Comparison</div>', unsafe_allow_html=True)

FUNDA_METRICS = [
    ("Market Cap (Cr)",  "market_cap",       "high"),
    ("PE Ratio",         "pe",               "low"),
    ("PB Ratio",         "pb",               "low"),
    ("ROE (%)",          "roe",              "high"),
    ("ROCE (%)",         "roce",             "high"),
    ("OPM (%)",          "opm",              "high"),
    ("NPM (%)",          "npm",              "high"),
    ("Debt/Equity",      "debt_equity",      "low"),
    ("Sales Growth %",   "sales_growth",     "high"),
    ("Profit Growth %",  "profit_growth",    "high"),
    ("Promoter %",       "promoter_holding", "high"),
    ("EPS",              "eps",              "high"),
]

try:
    funda_rows = []
    for label, key, better in FUNDA_METRICS:
        row = {"Metric": label, "_better": better}
        for sym in symbols:
            ratios = (screener_all.get(sym) or {}).get("ratios") or {}
            row[sym] = ratios.get(key)
        funda_rows.append(row)

    df_funda = pd.DataFrame(funda_rows).set_index("Metric")
    better_col = df_funda.pop("_better")

    def _fmt(v):
        if v is None:
            return "—"
        try:
            return f"{float(v):,.2f}"
        except Exception:
            return str(v)

    df_fmt = df_funda.map(_fmt)

    def _style_funda(df: pd.DataFrame):
        styled = pd.DataFrame("", index=df.index, columns=df.columns)
        for idx in df.index:
            better = better_col.get(idx, "high")
            nums = {}
            for col in df.columns:
                raw = df_funda.loc[idx, col]
                try:
                    nums[col] = float(raw)
                except (TypeError, ValueError):
                    pass
            if not nums:
                continue
            best  = max(nums, key=lambda c: nums[c]) if better == "high" else min(nums, key=lambda c: nums[c])
            worst = min(nums, key=lambda c: nums[c]) if better == "high" else max(nums, key=lambda c: nums[c])
            styled.loc[idx, best]  = f"color:{GREEN};font-weight:700"
            styled.loc[idx, worst] = f"color:{RED};font-weight:700"
        return styled

    st.dataframe(df_fmt.style.apply(_style_funda, axis=None), use_container_width=True)
except Exception as e:
    st.warning(f"Fundamental table error: {e}")

st.markdown("---")

# ═══════════════════════════════════════════════════════════════════════════════
# SECTION C: Radar Chart
# ═══════════════════════════════════════════════════════════════════════════════
st.markdown('<div class="z-section">Radar Comparison</div>', unsafe_allow_html=True)

RADAR_METRICS = [("ROE", "roe"), ("ROCE", "roce"), ("OPM", "opm"),
                 ("Sales Growth", "sales_growth"), ("Promoter %", "promoter_holding"), ("PE (inv)", "pe")]

try:
    fig_radar = go.Figure()
    cats = [m[0] for m in RADAR_METRICS]
    cats_closed = cats + [cats[0]]
    for sym in symbols:
        ratios = (screener_all.get(sym) or {}).get("ratios") or {}
        vals = []
        for _, key in RADAR_METRICS:
            v = ratios.get(key)
            try:
                fv = float(v)
                if key == "pe" and fv > 0:
                    fv = min(100, 1000 / fv)
                vals.append(max(0.0, fv))
            except (TypeError, ValueError):
                vals.append(0.0)
        fig_radar.add_trace(go.Scatterpolar(
            r=vals + [vals[0]], theta=cats_closed, name=sym, fill="toself",
            fillcolor=sym_color_a[sym], line=dict(color=sym_color[sym], width=2),
        ))
    fig_radar.update_layout(
        polar=dict(
            bgcolor=CARD,
            radialaxis=dict(gridcolor=BORDER, linecolor=BORDER, color=TEXT_DIM),
            angularaxis=dict(gridcolor=BORDER, linecolor=BORDER, color=TEXT),
        ),
        paper_bgcolor=CARD, font=dict(color=TEXT),
        legend=dict(orientation="h", y=-0.1, bgcolor=CARD),
        height=430, margin=dict(t=30, b=60, l=40, r=40),
    )
    st.plotly_chart(fig_radar, use_container_width=True)
except Exception as e:
    st.warning(f"Radar chart error: {e}")

st.markdown("---")

# ═══════════════════════════════════════════════════════════════════════════════
# SECTION D: Technical Comparison
# ═══════════════════════════════════════════════════════════════════════════════
st.markdown('<div class="z-section">Technical Comparison</div>', unsafe_allow_html=True)

try:
    tech_rows = []

    def _pct_vs(val, ref):
        try:
            return f"{(float(val) - float(ref)) / abs(float(ref)) * 100:+.1f}%"
        except Exception:
            return "—"

    for sym in symbols:
        tv = tv_bulk.get(sym, {})
        ind = tv.get("indicators") or {}
        price_v  = ind.get("close")
        rsi_v    = ind.get("rsi")
        rec      = tv.get("recommendation", "—")
        tech_rows.append({
            "Symbol":    sym,
            "Price":     f"₹{price_v:,.2f}" if price_v else "—",
            "Change %":  f"{ind.get('change', 0):+.2f}%" if ind.get("change") is not None else "—",
            "RSI":       f"{rsi_v:.1f}" if rsi_v else "—",
            "vs SMA50":  _pct_vs(price_v, ind.get("sma50")),
            "vs SMA200": _pct_vs(price_v, ind.get("sma200")),
            "MACD":      f"{ind.get('macd', 0):.2f}" if ind.get("macd") is not None else "—",
            "ADX":       f"{ind.get('adx', 0):.1f}" if ind.get("adx") is not None else "—",
            "Signal":    rec,
            "_rsi":      rsi_v,
            "_rec":      rec,
        })

    df_tech = pd.DataFrame(tech_rows).set_index("Symbol")

    def _style_tech(df):
        styles = pd.DataFrame("", index=df.index, columns=df.columns)
        for sym in df.index:
            rsi_raw = df_tech.loc[sym, "_rsi"]
            rec_raw = df_tech.loc[sym, "_rec"]
            try:
                r = float(rsi_raw) if rsi_raw else None
                if r and r > 70:
                    styles.loc[sym, "RSI"] = f"color:{RED};font-weight:600"
                elif r and r < 40:
                    styles.loc[sym, "RSI"] = f"color:{GREEN};font-weight:600"
            except Exception:
                pass
            if "BUY" in str(rec_raw):
                styles.loc[sym, "Signal"] = f"color:{GREEN};font-weight:700"
            elif "SELL" in str(rec_raw):
                styles.loc[sym, "Signal"] = f"color:{RED};font-weight:700"
        return styles

    st.dataframe(
        df_tech.drop(columns=["_rsi", "_rec"], errors="ignore").style.apply(_style_tech, axis=None),
        use_container_width=True,
    )
except Exception as e:
    st.warning(f"Technical comparison error: {e}")

st.markdown("---")

# ═══════════════════════════════════════════════════════════════════════════════
# SECTION E: AI Score Comparison
# ═══════════════════════════════════════════════════════════════════════════════
st.markdown('<div class="z-section">AI Score Comparison</div>', unsafe_allow_html=True)

try:
    from services.ai_service import analyze_stock
    ai_rows = []
    for sym in symbols:
        v = analyze_stock(sym, tv=tv_bulk.get(sym), screener=screener_all.get(sym))
        ai_rows.append({
            "Symbol": sym, "Verdict": v.verdict, "Score": v.score,
            "Tech": v.tech_score, "Fundamental": v.fund_score,
            "Pattern": v.pattern_score, "Momentum": v.momentum_score,
        })

    df_ai = pd.DataFrame(ai_rows).set_index("Symbol")

    def _style_ai(df):
        styles = pd.DataFrame("", index=df.index, columns=df.columns)
        for sym in df.index:
            verdict = df.loc[sym, "Verdict"]
            if "BUY" in str(verdict):
                styles.loc[sym, "Verdict"] = f"color:{GREEN};font-weight:700"
            elif "SELL" in str(verdict):
                styles.loc[sym, "Verdict"] = f"color:{RED};font-weight:700"
        return styles

    st.dataframe(df_ai.style.apply(_style_ai, axis=None), use_container_width=True)

    # Score bar chart
    fig_ai = go.Figure()
    for sym in symbols:
        row = next((r for r in ai_rows if r["Symbol"] == sym), {})
        fig_ai.add_trace(go.Bar(
            name=sym,
            x=["Score", "Tech", "Fundamental", "Pattern", "Momentum"],
            y=[row.get("Score",0), row.get("Tech",0), row.get("Fundamental",0),
               row.get("Pattern",0), row.get("Momentum",0)],
            marker_color=sym_color.get(sym, BLUE),
        ))
    fig_ai.update_layout(
        barmode="group", template="plotly_dark",
        paper_bgcolor=CARD, plot_bgcolor=CARD, height=300,
        margin=dict(l=0, r=0, t=10, b=0),
        legend=dict(orientation="h"),
    )
    st.plotly_chart(fig_ai, use_container_width=True)
except Exception as e:
    st.warning(f"AI comparison error: {e}")
