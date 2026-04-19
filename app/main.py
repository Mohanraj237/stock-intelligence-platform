from __future__ import annotations

import pandas as pd
import streamlit as st

# FIXED IMPORT
from ui import apply_page_config, sidebar_footer

from backend.ai_analysis import generate_ai_analysis
from backend.fundamentals import get_fundamentals
from backend.patterns import detect_chart_patterns
from backend.stock_data import collect_price_histories, get_price_history, get_quote
from backend.technical_analysis import technical_summary
from backend.tradingview_analysis import get_tradingview_summary
from backend.watchlist import add_to_watchlist, seed_default_watchlist

from utils.charts import candlestick_chart
from utils.export_report import export_stock_pdf
from utils.formatting import fmt_market_cap, fmt_number, fmt_rupees


apply_page_config("Dashboard | Indian Stock AI Agent")
seed_default_watchlist()

st.sidebar.title("Indian Stock AI Agent")
st.sidebar.page_link("main.py", label="Dashboard")
st.sidebar.page_link("pages/Scanner.py", label="Scanner")
st.sidebar.page_link("pages/Watchlist.py", label="Watchlist")
st.sidebar.page_link("pages/Settings.py", label="Settings")
sidebar_footer()

st.title("AI Stock Market Analyst")
st.caption("NSE/BSE technicals, fundamentals, scanner intelligence, and AI-assisted research.")

symbol = st.text_input(
    "Search by NSE symbol or company name",
    value="RELIANCE",
    placeholder="RELIANCE, TCS, INFY, HDFCBANK, TATAMOTORS",
).strip()

col_a, col_b = st.columns([1, 4])
run_analysis = col_a.button("Analyze", type="primary", use_container_width=True)
col_b.caption("Tip: use NSE symbols without suffix. The app tries .NS first, then .BO.")

if symbol and (run_analysis or "last_symbol" not in st.session_state):
    st.session_state.last_symbol = symbol

active_symbol = st.session_state.get("last_symbol", symbol)

if active_symbol:
    try:
        with st.spinner(f"Fetching market data for {active_symbol.upper()}..."):
            quote = get_quote(active_symbol)
            _, history = get_price_history(active_symbol, period="1y")
            tech_df, technicals = technical_summary(history)
            patterns = detect_chart_patterns(tech_df)
            collected = collect_price_histories(active_symbol, period="1y")
            fundamentals = get_fundamentals(active_symbol)
            tradingview = get_tradingview_summary(quote.symbol)
            ai_analysis = generate_ai_analysis(
                quote.__dict__, technicals, fundamentals, tradingview
            )

        st.subheader(f"{quote.company_name} ({quote.symbol})")
        st.caption(
            f"Exchange source: {quote.exchange} via {quote.yahoo_symbol} | "
            f"Data provider: {quote.source}"
        )

        price_cols = st.columns(5)
        price_cols[0].metric(
            "Current Price",
            fmt_rupees(quote.current_price),
            f"{fmt_number(quote.day_change_pct)}%",
        )
        price_cols[1].metric("52 Week High", fmt_rupees(quote.fifty_two_week_high))
        price_cols[2].metric("52 Week Low", fmt_rupees(quote.fifty_two_week_low))
        price_cols[3].metric("Volume", fmt_number(quote.volume, digits=0))
        price_cols[4].metric("Market Cap", fmt_market_cap(quote.market_cap))

        chart_tab, pattern_tab, tech_tab, fund_tab, tv_tab, sources_tab, ai_tab = st.tabs(
            [
                "Chart",
                "Patterns",
                "Technicals",
                "Fundamentals",
                "TradingView",
                "Sources",
                "AI Summary",
            ]
        )

        with chart_tab:
            st.plotly_chart(
                candlestick_chart(
                    tech_df.tail(220),
                    f"{quote.symbol} Candlestick with Moving Averages",
                    patterns=patterns,
                ),
                use_container_width=True,
            )

        with pattern_tab:
            if patterns:
                pattern_rows = pd.DataFrame(patterns)
                st.dataframe(pattern_rows, use_container_width=True, hide_index=True)
            else:
                st.info("No high-confidence chart pattern detected.")

        with tech_tab:
            tech_rows = pd.DataFrame(
                [{"Metric": k, "Value": v} for k, v in technicals.items()]
            )
            st.dataframe(tech_rows, use_container_width=True, hide_index=True)

        with fund_tab:
            fund_rows = pd.DataFrame(
                [{"Metric": k, "Value": v} for k, v in fundamentals.items()]
            )
            st.dataframe(fund_rows, use_container_width=True, hide_index=True)

        with tv_tab:
            st.json(tradingview)

        with sources_tab:
            st.json(collected)

        with ai_tab:
            st.metric("Final AI Score", ai_analysis.get("final_score", "N/A"))
            st.markdown(f"**Stance:** {ai_analysis.get('stance', 'N/A')}")
            st.markdown(f"**Short-term:** {ai_analysis.get('short_term_outlook', 'N/A')}")
            st.markdown(f"**Long-term:** {ai_analysis.get('long_term_outlook', 'N/A')}")

            st.markdown("### Risks")
            for r in ai_analysis.get("risks", []):
                st.write("-", r)

            st.markdown("### Opportunities")
            for o in ai_analysis.get("opportunities", []):
                st.write("-", o)

            c1, c2 = st.columns(2)

            if c1.button("Save to Watchlist", use_container_width=True):
                add_to_watchlist(quote.symbol, quote.company_name)
                st.success("Added to watchlist")

            if c2.button("Export PDF Report", use_container_width=True):
                pdf_path = export_stock_pdf(
                    quote.symbol, quote.__dict__, technicals, ai_analysis
                )
                st.success(f"Saved: {pdf_path}")

    except Exception as exc:
        st.error(f"Could not analyze {active_symbol.upper()}: {exc}")