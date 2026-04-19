from __future__ import annotations

import pandas as pd
import streamlit as st

from app.ui import apply_page_config, sidebar_footer
from backend.stock_data import get_quote
from backend.watchlist import add_to_watchlist, list_watchlist, remove_from_watchlist, seed_default_watchlist
from utils.formatting import fmt_number, fmt_rupees


apply_page_config("Watchlist | Indian Stock AI Agent")
seed_default_watchlist()

st.sidebar.title("Indian Stock AI Agent")
st.sidebar.page_link("main.py", label="Dashboard")
st.sidebar.page_link("pages/Scanner.py", label="Scanner")
st.sidebar.page_link("pages/Watchlist.py", label="Watchlist")
st.sidebar.page_link("pages/Settings.py", label="Settings")
sidebar_footer()

st.title("Watchlist")
st.caption("Save favorite NSE/BSE stocks and check latest prices quickly.")

add_cols = st.columns([3, 1])
new_symbol = add_cols[0].text_input("Add symbol", placeholder="TCS")
if add_cols[1].button("Add", use_container_width=True):
    try:
        add_to_watchlist(new_symbol)
        st.success(f"{new_symbol.upper()} added.")
        st.rerun()
    except ValueError as exc:
        st.error(str(exc))

rows = list_watchlist()
if not rows:
    st.info("No symbols saved yet.")
else:
    symbols = [row["symbol"] for row in rows]
    with st.spinner("Refreshing watchlist quotes..."):
        quote_rows = []
        for symbol in symbols:
            try:
                quote = get_quote(symbol)
                quote_rows.append(
                    {
                        "Symbol": quote.symbol,
                        "Company": quote.company_name,
                        "Price": fmt_rupees(quote.current_price),
                        "Change %": fmt_number(quote.day_change_pct),
                        "Volume": fmt_number(quote.volume, digits=0),
                    }
                )
            except Exception as exc:
                quote_rows.append({"Symbol": symbol, "Company": "Unavailable", "Price": "N/A", "Change %": str(exc), "Volume": "N/A"})
    st.dataframe(pd.DataFrame(quote_rows), use_container_width=True, hide_index=True)

    remove_symbol = st.selectbox("Remove symbol", options=symbols)
    if st.button("Remove from Watchlist"):
        remove_from_watchlist(remove_symbol)
        st.success(f"{remove_symbol} removed.")
        st.rerun()
