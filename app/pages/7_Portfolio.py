from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st
import pandas as pd
from datetime import datetime


from utils.theme import apply_theme
apply_theme()

from storage.file_store import get_holdings, add_holding, remove_holding
from services.market_router import (
    get_region, get_universe_names as get_all_universe_names,
    get_universe_display_map as universe_display_map,
    get_universe_symbols, get_market_analysis as get_tv_analysis, fmt_currency,
)
from app.components.metrics_card import render_kpi_row

region = get_region()

st.markdown("## 💼 Portfolio Tracker")

# ── Holdings ──────────────────────────────────────────────────────────────────
holdings = get_holdings()

# ── Add holding form ──────────────────────────────────────────────────────────
with st.expander("➕ Add New Holding"):
    disp_map = universe_display_map()
    all_names = get_all_universe_names()
    labels = [disp_map.get(n, n) for n in all_names]
    _uni_label = st.selectbox("Index / Universe", labels, key="port_uni")
    _uni = all_names[labels.index(_uni_label)]
    _syms = get_universe_symbols(_uni)

    with st.form("add_holding"):
        col1, col2, col3, col4 = st.columns(4)
        curr_sym = "$" if region == "US" else "₹"
        with col1:
            new_sym = st.selectbox("Symbol", _syms, key="port_sym")
        with col2:
            new_qty = st.number_input("Quantity", min_value=1, value=10, step=1)
        with col3:
            new_price = st.number_input(f"Buy Price ({curr_sym})", min_value=0.0, value=0.0, step=1.0)
        with col4:
            new_date = st.date_input("Buy Date", value=datetime.now().date())
        if st.form_submit_button("Add Holding", type="primary"):
            add_holding(new_sym, new_qty, new_price, str(new_date))
            st.success(f"Added {new_qty} shares of {new_sym} @ {fmt_currency(new_price)}")
            st.rerun()

if not holdings:
    st.info("No holdings yet. Add your first holding above.")
    st.stop()

# ── Live P&L ──────────────────────────────────────────────────────────────────
st.markdown("### Portfolio Holdings")

rows = []
total_invested = 0
total_current  = 0

for h in holdings:
    sym = h.get("symbol", "")
    qty = h.get("qty", 0) or 0
    buy = h.get("buy_price", 0) or 0
    try:
        tv = get_tv_analysis(sym, "1d") or {}
        cmp = (tv.get("indicators") or {}).get("close") or 0
        change_pct = (tv.get("indicators") or {}).get("change") or 0
        rec = tv.get("recommendation", "NEUTRAL")
    except Exception:
        cmp, change_pct, rec = 0, 0, "N/A"

    invested = qty * buy
    current_val = qty * cmp if cmp else 0
    pnl = current_val - invested
    pnl_pct = (pnl / invested * 100) if invested > 0 else 0

    total_invested += invested
    total_current  += current_val

    rows.append({
        "Symbol": sym,
        "Qty": int(qty),
        "Buy Price": fmt_currency(buy),
        "CMP": fmt_currency(cmp) if cmp else "—",
        "Today %": f"{change_pct:+.2f}%" if change_pct else "—",
        "Invested": fmt_currency(invested, decimals=0),
        "Current Val": fmt_currency(current_val, decimals=0) if current_val else "—",
        "P&L": fmt_currency(pnl, decimals=0) if current_val else "—",
        "P&L %": f"{pnl_pct:+.1f}%" if current_val else "—",
        "Signal": rec,
        "Buy Date": h.get("buy_date", ""),
    })

# KPI summary
total_pnl = total_current - total_invested
total_pnl_pct = (total_pnl / total_invested * 100) if total_invested > 0 else 0
curr_sym = "$" if region == "US" else "₹"
render_kpi_row([
    {"label": "Total Invested", "value": total_invested, "prefix": curr_sym, "decimals": 0},
    {"label": "Current Value", "value": total_current, "prefix": curr_sym, "decimals": 0},
    {"label": "Total P&L", "value": total_pnl, "prefix": curr_sym, "decimals": 0,
     "delta": f"{total_pnl_pct:+.1f}%"},
    {"label": "Holdings", "value": len(holdings)},
], cols=4)

# Table
df = pd.DataFrame(rows)
st.dataframe(df, use_container_width=True, height=350)

# Remove holding
st.markdown("### Remove Holding")
syms = [h.get("symbol") for h in holdings]
to_remove = st.selectbox("Select to remove", syms)
if st.button("🗑️ Remove Holding", type="secondary"):
    remove_holding(to_remove)
    st.success(f"Removed {to_remove}")
    st.rerun()

# Export
st.download_button("📥 Export Portfolio CSV", df.to_csv(index=False), "portfolio.csv", "text/csv")
