from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from utils.theme import apply_theme, GREEN, RED, BLUE, CARD, BORDER, TEXT, TEXT_DIM
apply_theme()

from services.market_router import (
    get_region, get_universe_names as get_all_universe_names,
    get_universe_display_map as universe_display_map,
    get_universe_symbols, scan_symbols_bulk, tv_score, fmt_currency, fmt_volume,
    get_index_quotes,
)
region = get_region()

st.markdown("## 🌐 Universe Explorer")

# ── Universe + Controls ───────────────────────────────────────────────────────
disp_map  = universe_display_map()
all_names = get_all_universe_names()
labels    = [disp_map.get(n, n) for n in all_names]

ue1, ue2, ue3 = st.columns([3, 2, 1])
with ue1:
    sel_label = st.selectbox("Index / Universe", labels, key="ue_index")
    sel_name  = all_names[labels.index(sel_label)]
with ue2:
    sort_by = st.selectbox("Sort By", [
        "Change % ↓", "Change % ↑", "RSI ↓", "RSI ↑",
        "ADX ↓", "Volume ↓", "30D Ret% ↓", "1Y Ret% ↓", "Symbol A-Z",
    ], key="ue_sort")
with ue3:
    st.markdown("<br>", unsafe_allow_html=True)
    run_scan = st.button("🔄 Scan Universe", type="primary", key="ue_run")

# ── Filters expander ──────────────────────────────────────────────────────────
with st.expander("🔧 Filters & Rules", expanded=False):
    fc1, fc2, fc3, fc4 = st.columns(4)
    with fc1:
        st.markdown(f'<span style="color:{TEXT_DIM};font-size:0.78rem;font-weight:700">SIGNAL</span>', unsafe_allow_html=True)
        sig_filter = st.multiselect("Market Signal", ["STRONG_BUY", "BUY", "NEUTRAL", "SELL", "STRONG_SELL"],
                                    default=[], key="ue_sig")
    with fc2:
        st.markdown(f'<span style="color:{TEXT_DIM};font-size:0.78rem;font-weight:700">RSI ZONE</span>', unsafe_allow_html=True)
        rsi_min_f = st.number_input("RSI Min", 0.0, 100.0, 0.0, key="ue_rsi_min")
        rsi_max_f = st.number_input("RSI Max", 0.0, 100.0, 100.0, key="ue_rsi_max")
    with fc3:
        st.markdown(f'<span style="color:{TEXT_DIM};font-size:0.78rem;font-weight:700">PRICE RULES</span>', unsafe_allow_html=True)
        above_sma50  = st.checkbox("Price > SMA 50",  key="ue_sma50")
        above_sma200 = st.checkbox("Price > SMA 200", key="ue_sma200")
        macd_bull    = st.checkbox("MACD Bullish",     key="ue_macd")
    with fc4:
        st.markdown(f'<span style="color:{TEXT_DIM};font-size:0.78rem;font-weight:700">CHANGE %</span>', unsafe_allow_html=True)
        chg_min = st.number_input("Change% Min", -20.0, 20.0, -20.0, key="ue_chg_min")
        chg_max = st.number_input("Change% Max", -20.0, 20.0,  20.0, key="ue_chg_max")

# ── Load data ─────────────────────────────────────────────────────────────────
@st.cache_data(ttl=300, show_spinner=False)
def _load_universe_tv(universe: str, rgn: str):
    symbols = get_universe_symbols(universe)
    all_tv: dict = {}
    batches = [symbols[i:i+100] for i in range(0, len(symbols), 100)]
    for batch in batches:
        all_tv.update(scan_symbols_bulk(batch))

    # Fall back to live index quotes if technical scan returned nothing
    if not all_tv:
        live_quotes = get_index_quotes(universe)
        for q in live_quotes:
            sym = q.get("symbol", "")
            if not sym:
                continue
            chg_pct = float(q.get("change_pct") or 0)
            all_tv[sym] = {
                "symbol": sym,
                "recommendation": "NEUTRAL",
                "indicators": {
                    "close":       q.get("price"),
                    "change":      chg_pct,
                    "volume":      q.get("volume"),
                    "rsi":         None,
                    "macd":        None,
                    "macd_signal": None,
                    "sma50":       None,
                    "sma200":      None,
                    "adx":         None,
                },
                "_live_source":  True,
                "_return_30d":   q.get("return_30d"),
                "_return_365d":  q.get("return_365d"),
            }
        if live_quotes and not symbols:
            symbols = [q["symbol"] for q in live_quotes if q.get("symbol")]
    return symbols, all_tv

prev_key = st.session_state.get("_ue_key", "")
if run_scan or sel_name != prev_key or "ue_tv_data" not in st.session_state:
    with st.spinner(f"Scanning {sel_name}…"):
        symbols, tv_data = _load_universe_tv(sel_name, region)
    st.session_state.update({"ue_tv_data": tv_data, "ue_symbols": symbols, "_ue_key": sel_name})

tv_data = st.session_state.get("ue_tv_data", {})
symbols = st.session_state.get("ue_symbols", [])

if not tv_data:
    st.warning("No data loaded. Check connection or try again.")
    st.stop()

is_live_fallback = any(v.get("_live_source") for v in tv_data.values())
if is_live_fallback:
    source_name = "Yahoo Finance (US live quotes)" if region == "US" else "NSE India"
    st.info(
        f"📡 **Live quote fallback active** — Technical scan returned no data. "
        f"Technical indicators (RSI, MACD, ADX) not shown; prices sourced from {source_name}.",
        icon=None,
    )

# ── Build rows + apply filters with AUDIT TRAIL ───────────────────────────────
audit_log  = []
all_rows   = []
passed     = []
skipped_cnt = 0

audit_log.append(f"**Universe:** {sel_name} — {len(symbols)} symbols loaded")
audit_log.append(f"**Market data fetched for:** {len(tv_data)} symbols")
audit_log.append("---")
audit_log.append("**Active Rules:**")

# Log active rules
rules_active = []
if sig_filter:
    rules_active.append(f"Signal ∈ {sig_filter}")
if rsi_min_f > 0:
    rules_active.append(f"RSI ≥ {rsi_min_f:.0f}")
if rsi_max_f < 100:
    rules_active.append(f"RSI ≤ {rsi_max_f:.0f}")
if above_sma50:
    rules_active.append("Price > SMA 50")
if above_sma200:
    rules_active.append("Price > SMA 200")
if macd_bull:
    rules_active.append("MACD > Signal (bullish crossover)")
if chg_min > -20:
    rules_active.append(f"Change% ≥ {chg_min:.1f}%")
if chg_max < 20:
    rules_active.append(f"Change% ≤ {chg_max:.1f}%")

if rules_active:
    for r in rules_active:
        audit_log.append(f"  ✔ {r}")
else:
    audit_log.append("  _(no filters active — showing all stocks)_")

audit_log.append("---")
audit_log.append("**Per-Symbol Filter Results:**")

for sym in symbols:
    tv  = tv_data.get(sym, {})
    ind = tv.get("indicators") or {}
    rec = tv.get("recommendation", "NEUTRAL")

    close   = ind.get("close")
    chg     = ind.get("change") or 0
    rsi_v   = ind.get("rsi")
    macd_v  = ind.get("macd")
    macd_s  = ind.get("macd_signal")
    sma50   = ind.get("sma50") or ind.get("ema50")
    sma200  = ind.get("sma200")
    adx_v   = ind.get("adx")
    vol     = ind.get("volume")

    row = {
        "Symbol":   sym,
        "Price":    close,
        "Change %": chg,
        "RSI":      rsi_v,
        "MACD":     macd_v,
        "MACD Sig": macd_s,
        "SMA 50":   sma50,
        "SMA 200":  sma200,
        "ADX":      adx_v,
        "Volume":   vol,
        "Signal":   rec,
        "TV Score": tv_score(rec),
        "_raw":     tv,
        "_ret30":   tv.get("_return_30d"),
        "_ret365":  tv.get("_return_365d"),
    }
    all_rows.append(row)

    # Apply filters and build audit
    reasons_fail = []
    if sig_filter and rec not in sig_filter:
        reasons_fail.append(f"Signal={rec} not in filter")
    if rsi_v is not None:
        if rsi_min_f > 0 and float(rsi_v) < rsi_min_f:
            reasons_fail.append(f"RSI={rsi_v:.1f} < {rsi_min_f:.0f}")
        if rsi_max_f < 100 and float(rsi_v) > rsi_max_f:
            reasons_fail.append(f"RSI={rsi_v:.1f} > {rsi_max_f:.0f}")
    if chg_min > -20 and float(chg) < chg_min:
        reasons_fail.append(f"Change%={chg:.2f} < {chg_min:.1f}")
    if chg_max < 20 and float(chg) > chg_max:
        reasons_fail.append(f"Change%={chg:.2f} > {chg_max:.1f}")
    if above_sma50 and close and sma50:
        if float(close) <= float(sma50):
            reasons_fail.append(f"Price={close:.1f} ≤ SMA50={sma50:.1f}")
    if above_sma200 and close and sma200:
        if float(close) <= float(sma200):
            reasons_fail.append(f"Price={close:.1f} ≤ SMA200={sma200:.1f}")
    if macd_bull and macd_v is not None and macd_s is not None:
        if float(macd_v) <= float(macd_s):
            reasons_fail.append(f"MACD={macd_v:.2f} ≤ Signal={macd_s:.2f}")

    if reasons_fail:
        skipped_cnt += 1
        if len(passed) + skipped_cnt <= 50:  # limit audit verbosity
            audit_log.append(f"  ✗ **{sym}** — skipped: {'; '.join(reasons_fail)}")
    else:
        passed.append(row)
        if len(passed) <= 30:
            checks = []
            if sig_filter:
                checks.append(f"Signal={rec} ✔")
            if rsi_v:
                checks.append(f"RSI={rsi_v:.1f} ✔")
            if above_sma50 and sma50 and close:
                checks.append(f"Price>SMA50 ✔")
            if macd_bull and macd_v and macd_s:
                checks.append(f"MACD>{macd_s:.2f} ✔")
            audit_log.append(f"  ✅ **{sym}** — passed" + (f": {', '.join(checks)}" if checks else ""))

audit_log.append("---")
audit_log.append(f"**Result: {len(passed)} / {len(symbols)} passed filters** ({skipped_cnt} skipped)")

# ── Sort ──────────────────────────────────────────────────────────────────────
_sort_map = {
    "Change % ↓":   ("Change %",  False),
    "Change % ↑":   ("Change %",  True),
    "RSI ↓":        ("RSI",       False),
    "RSI ↑":        ("RSI",       True),
    "ADX ↓":        ("ADX",       False),
    "Volume ↓":     ("Volume",    False),
    "30D Ret% ↓":   ("_ret30",    False),
    "1Y Ret% ↓":    ("_ret365",   False),
    "Symbol A-Z":   ("Symbol",    True),
}
sort_col, sort_asc = _sort_map.get(sort_by, ("Change %", False))
passed_sorted = sorted(
    passed,
    key=lambda x: (x.get(sort_col) is not None, x.get(sort_col) or 0),
    reverse=not sort_asc,
)

# ── Summary metrics ───────────────────────────────────────────────────────────
df_all = pd.DataFrame(all_rows)
total     = len(df_all)
gainers   = int((pd.to_numeric(df_all["Change %"], errors="coerce") > 0).sum())
losers    = int((pd.to_numeric(df_all["Change %"], errors="coerce") < 0).sum())
buy_cnt   = int(df_all["Signal"].str.contains("BUY", na=False).sum())
avg_rsi   = pd.to_numeric(df_all["RSI"], errors="coerce").mean()
avg_chg   = pd.to_numeric(df_all["Change %"], errors="coerce").mean()

m1, m2, m3, m4, m5, m6, m7 = st.columns(7)
m1.metric("Total",      total)
m2.metric("Advancing",  gainers)
m3.metric("Declining",  losers)
m4.metric("Avg Change", f"{avg_chg:+.2f}%" if pd.notna(avg_chg) else "—")
m5.metric("Avg RSI",    f"{avg_rsi:.1f}" if pd.notna(avg_rsi) else "—")
m6.metric("Buy Signals", buy_cnt)
m7.metric("Filtered",   len(passed))

st.markdown("---")

# ── Charts row ────────────────────────────────────────────────────────────────
ch1, ch2 = st.columns(2)

with ch1:
    st.markdown('<div class="z-section">Signal Distribution</div>', unsafe_allow_html=True)
    sig_counts = df_all["Signal"].value_counts()
    sig_colors = {
        "STRONG_BUY": GREEN, "BUY": "#4caf50",
        "NEUTRAL": TEXT_DIM, "SELL": "#e57373", "STRONG_SELL": RED,
    }
    fig_sig = go.Figure(go.Bar(
        x=list(sig_counts.index), y=list(sig_counts.values),
        marker_color=[sig_colors.get(s, BLUE) for s in sig_counts.index],
        text=list(sig_counts.values), textposition="outside",
    ))
    fig_sig.update_layout(
        template="plotly_dark", paper_bgcolor=CARD, plot_bgcolor=CARD,
        height=240, showlegend=False, margin=dict(l=0, r=0, t=10, b=0),
        xaxis=dict(tickfont=dict(size=10), gridcolor=BORDER),
        yaxis=dict(gridcolor=BORDER),
    )
    st.plotly_chart(fig_sig, use_container_width=True)

with ch2:
    st.markdown('<div class="z-section">RSI Distribution</div>', unsafe_allow_html=True)
    rsi_vals = pd.to_numeric(df_all["RSI"], errors="coerce").dropna()
    fig_rsi = go.Figure(go.Histogram(x=rsi_vals, nbinsx=25, marker_color=BLUE, opacity=0.8))
    fig_rsi.add_vline(x=30, line_dash="dot", line_color=GREEN, annotation_text="30 (OS)")
    fig_rsi.add_vline(x=50, line_dash="dash", line_color=TEXT_DIM, annotation_text="50")
    fig_rsi.add_vline(x=70, line_dash="dot", line_color=RED, annotation_text="70 (OB)")
    fig_rsi.update_layout(
        template="plotly_dark", paper_bgcolor=CARD, plot_bgcolor=CARD,
        height=240, showlegend=False, margin=dict(l=0, r=0, t=10, b=0),
        xaxis=dict(gridcolor=BORDER), yaxis=dict(gridcolor=BORDER),
    )
    st.plotly_chart(fig_rsi, use_container_width=True)

# ── Main table ────────────────────────────────────────────────────────────────
st.markdown(f'<div class="z-section">Stocks — {len(passed_sorted)} shown (of {total} in universe)</div>', unsafe_allow_html=True)

if passed_sorted:
    df_disp = pd.DataFrame([{
        "Symbol":    r["Symbol"],
        "Price":     fmt_currency(r["Price"]) if r.get("Price") else "—",
        "Change %":  f"{float(r['Change %']):+.2f}%" if r.get("Change %") is not None else "—",
        "RSI":       f"{float(r['RSI']):.1f}" if r.get("RSI") is not None else "—",
        "ADX":       f"{float(r['ADX']):.1f}" if r.get("ADX") is not None else "—",
        "MACD":      f"{float(r['MACD']):.2f}" if r.get("MACD") is not None else "—",
        "vs SMA50":  (
            f"{(float(r['Price'])-float(r['SMA 50']))/abs(float(r['SMA 50']))*100:+.1f}%"
            if r.get("Price") and r.get("SMA 50") else "—"
        ),
        "vs SMA200": (
            f"{(float(r['Price'])-float(r['SMA 200']))/abs(float(r['SMA 200']))*100:+.1f}%"
            if r.get("Price") and r.get("SMA 200") else "—"
        ),
        "30D Ret%":  f"{float(r['_ret30']):+.2f}%" if r.get("_ret30") is not None else "—",
        "1Y Ret%":   f"{float(r['_ret365']):+.2f}%" if r.get("_ret365") is not None else "—",
        "Volume":    fmt_volume(r["Volume"]) if r.get("Volume") else "—",
        "Signal":    r["Signal"],
        "_chg":      float(r["Change %"]) if r.get("Change %") is not None else 0,
        "_rsi":      float(r["RSI"]) if r.get("RSI") is not None else 50,
        "_rec":      r["Signal"],
        "_ret30":    float(r["_ret30"]) if r.get("_ret30") is not None else None,
        "_ret365":   float(r["_ret365"]) if r.get("_ret365") is not None else None,
    } for r in passed_sorted])

    def _style_universe(df: pd.DataFrame):
        styles = pd.DataFrame("", index=df.index, columns=df.columns)
        for i in range(len(df)):
            chg_v = df.iloc[i]["_chg"]
            rsi_v = df.iloc[i]["_rsi"]
            rec_v = str(df.iloc[i]["_rec"])
            c_chg = GREEN if float(chg_v) >= 0 else RED
            styles.iloc[i, df.columns.get_loc("Change %")] = f"color:{c_chg};font-weight:700"
            if float(rsi_v) > 70:
                styles.iloc[i, df.columns.get_loc("RSI")] = f"color:{RED};font-weight:600"
            elif float(rsi_v) < 35:
                styles.iloc[i, df.columns.get_loc("RSI")] = f"color:{GREEN};font-weight:600"
            if "STRONG_BUY" in rec_v:
                styles.iloc[i, df.columns.get_loc("Signal")] = f"color:{GREEN};font-weight:800"
            elif "BUY" in rec_v:
                styles.iloc[i, df.columns.get_loc("Signal")] = f"color:{GREEN};font-weight:600"
            elif "STRONG_SELL" in rec_v:
                styles.iloc[i, df.columns.get_loc("Signal")] = f"color:{RED};font-weight:800"
            elif "SELL" in rec_v:
                styles.iloc[i, df.columns.get_loc("Signal")] = f"color:{RED};font-weight:600"
            else:
                styles.iloc[i, df.columns.get_loc("Signal")] = f"color:{TEXT_DIM}"
            vs50 = df.iloc[i]["vs SMA50"]
            if vs50 != "—":
                try:
                    v50 = float(vs50.replace("%","").replace("+",""))
                    styles.iloc[i, df.columns.get_loc("vs SMA50")] = f"color:{GREEN if v50 >= 0 else RED}"
                except Exception:
                    pass
            vs200 = df.iloc[i]["vs SMA200"]
            if vs200 != "—":
                try:
                    v200 = float(vs200.replace("%","").replace("+",""))
                    styles.iloc[i, df.columns.get_loc("vs SMA200")] = f"color:{GREEN if v200 >= 0 else RED}"
                except Exception:
                    pass
            ret30 = df.iloc[i]["_ret30"]
            if ret30 is not None:
                try:
                    styles.iloc[i, df.columns.get_loc("30D Ret%")] = f"color:{GREEN if float(ret30) >= 0 else RED}"
                except Exception:
                    pass
            ret365 = df.iloc[i]["_ret365"]
            if ret365 is not None:
                try:
                    styles.iloc[i, df.columns.get_loc("1Y Ret%")] = f"color:{GREEN if float(ret365) >= 0 else RED}"
                except Exception:
                    pass
        return styles

    st.dataframe(
        df_disp.style.apply(_style_universe, axis=None).hide(subset=["_chg", "_rsi", "_rec", "_ret30", "_ret365"], axis="columns"),
        use_container_width=True, hide_index=True, height=520,
    )

    # ── Scatter: RSI vs Change% ────────────────────────────────────────────────
    with st.expander("📊 RSI vs Change% Scatter", expanded=False):
        scatter_rows = [r for r in passed_sorted if r.get("RSI") is not None and r.get("Change %") is not None]
        if scatter_rows:
            fig_sc = go.Figure(go.Scatter(
                x=[float(r["RSI"]) for r in scatter_rows],
                y=[float(r["Change %"]) for r in scatter_rows],
                mode="markers+text",
                text=[r["Symbol"] for r in scatter_rows],
                textposition="top center",
                textfont=dict(size=8, color=TEXT_DIM),
                marker=dict(
                    color=[float(r["Change %"]) for r in scatter_rows],
                    colorscale=[[0, RED], [0.5, TEXT_DIM], [1, GREEN]],
                    cmid=0, size=8, showscale=True,
                    colorbar=dict(title="Change %", tickfont=dict(color=TEXT)),
                ),
                hovertemplate="<b>%{text}</b><br>RSI: %{x:.1f}<br>Change: %{y:.2f}%<extra></extra>",
            ))
            fig_sc.add_vline(x=30, line_dash="dot", line_color=GREEN)
            fig_sc.add_vline(x=70, line_dash="dot", line_color=RED)
            fig_sc.add_hline(y=0, line_dash="dash", line_color=TEXT_DIM)
            fig_sc.update_layout(
                template="plotly_dark", paper_bgcolor=CARD, plot_bgcolor=CARD,
                height=400, margin=dict(l=10, r=10, t=20, b=20),
                xaxis=dict(title="RSI", gridcolor=BORDER, range=[0, 100]),
                yaxis=dict(title="Change %", gridcolor=BORDER),
            )
            st.plotly_chart(fig_sc, use_container_width=True)

    # ── Download ───────────────────────────────────────────────────────────────
    dl_df = df_disp.drop(columns=["_chg","_rsi","_rec","_ret30","_ret365"], errors="ignore")
    st.download_button(
        "⬇ Download CSV", dl_df.to_csv(index=False),
        f"{sel_name.replace(' ','_')}_universe.csv", "text/csv",
    )
else:
    st.info("No stocks match the current filters. Relax the filter criteria or clear all filters.")

# ── Audit Trail ───────────────────────────────────────────────────────────────
with st.expander("🔎 Analysis Audit Log", expanded=False):
    for line in audit_log:
        st.markdown(line)
