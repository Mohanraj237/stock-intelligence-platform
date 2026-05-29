from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st
import pandas as pd


from utils.theme import apply_theme
apply_theme()

from storage.file_store import get_watchlist, add_to_watchlist, remove_from_watchlist
from services.market_router import (
    get_region, get_universe_names as get_all_universe_names,
    get_universe_display_map as universe_display_map,
    get_universe_symbols, scan_symbols_bulk, tv_score, fmt_currency, fmt_volume,
)
region = get_region()

def get_tv_analysis_batch(symbols):
    return scan_symbols_bulk(symbols)
from app.components.chart_widget import render_mini_chart

st.markdown("## ⭐ Watchlist")

watchlist = get_watchlist()

# ── Add / Remove ──────────────────────────────────────────────────────────────
disp_map = universe_display_map()
all_names = get_all_universe_names()
labels = [disp_map.get(n, n) for n in all_names]
_add_col, _rem_col = st.columns([3, 1])
with _add_col:
    _uni_label = st.selectbox("Index / Universe", labels, key="wl_uni")
    _uni = all_names[labels.index(_uni_label)]
    _uni_syms = get_universe_symbols(_uni)
    to_add = st.multiselect("Add stocks to watchlist", _uni_syms, key="wl_add_syms")
    if st.button("➕ Add Selected") and to_add:
        for s in to_add:
            add_to_watchlist(s)
        st.success(f"Added: {', '.join(to_add)}")
        st.rerun()
with _rem_col:
    if watchlist:
        st.markdown("<br>", unsafe_allow_html=True)
        to_rem = st.selectbox("Remove", watchlist, key="wl_remove")
        if st.button("🗑️ Remove"):
            remove_from_watchlist(to_rem)
            st.rerun()

st.markdown(f"**{len(watchlist)} stocks** in watchlist")

if not watchlist:
    st.info("Watchlist is empty. Add stocks above.")
    st.stop()

# ── Load live data ─────────────────────────────────────────────────────────────
if st.button("🔄 Refresh Live Data", type="primary"):
    with st.spinner(f"Fetching data for {len(watchlist)} stocks..."):
        batch = get_tv_analysis_batch(watchlist)

    rows = []
    for sym in watchlist:
        data = batch.get(sym, {})
        ind  = data.get("indicators") or {}
        rec  = data.get("recommendation", "N/A")
        rows.append({
            "Symbol": sym,
            "Price": ind.get("close"),
            "Change %": ind.get("change"),
            "RSI": ind.get("rsi"),
            "MACD": ind.get("macd"),
            "SMA 50": ind.get("sma50"),
            "SMA 200": ind.get("sma200"),
            "Volume": ind.get("volume"),
            "Signal": rec,
            "Score": tv_score(rec),
        })

    df = pd.DataFrame(rows)

    def fmt_price(v):
        try: return fmt_currency(float(v))
        except: return "—"
    def fmt_pct(v):
        try:
            f = float(v)
            return f"{f:+.2f}%"
        except: return "—"

    df_disp = df.copy()
    df_disp["Price"] = df_disp["Price"].apply(fmt_price)
    df_disp["Change %"] = df_disp["Change %"].apply(fmt_pct)
    for col in ["RSI", "MACD", "Score"]:
        if col in df_disp.columns:
            df_disp[col] = df_disp[col].apply(lambda x: f"{float(x):.2f}" if x is not None else "—")

    def color_rec(val):
        c = {"STRONG_BUY":"#22c55e","BUY":"#86efac","NEUTRAL":"#f59e0b","SELL":"#f87171","STRONG_SELL":"#ef4444"}
        return f"color:{c.get(str(val).upper(),'#94a3b8')};font-weight:600"

    st.dataframe(df_disp.style.map(color_rec, subset=["Signal"]),
                 use_container_width=True, height=400)
    st.download_button("📥 Export CSV", df.to_csv(index=False), "watchlist.csv", "text/csv")

    # Quick mini charts for top 4
    st.markdown("### Mini Charts")
    chart_cols = st.columns(min(4, len(watchlist)))
    for i, (col, sym) in enumerate(zip(chart_cols, watchlist[:4])):
        with col:
            st.markdown(f"**{sym}**")
            render_mini_chart(sym)
else:
    # Show basic list
    st.markdown("### Current Watchlist")
    for sym in watchlist:
        rec_label = ""
        col_sym, col_btn = st.columns([4, 1])
        with col_sym:
            st.markdown(f"**{sym}**")
        with col_btn:
            if st.button("✕", key=f"rm_{sym}"):
                remove_from_watchlist(sym)
                st.rerun()
