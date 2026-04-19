from __future__ import annotations

import pandas as pd
import streamlit as st

from app.ui import apply_page_config, sidebar_footer
from backend.nse_universe import segment_options, universe_for_segment
from backend.scanner import SCAN_FUNCTIONS


def _flatten_checks(rows: list[dict], section: str | None = None) -> pd.DataFrame:
    flattened = []
    for row in rows:
        for check in row.get("Engine Checks", []):
            if section and check.get("Section") != section:
                continue
            flattened.append(
                {
                    "Symbol": row.get("Symbol"),
                    "Company": row.get("Company"),
                    "Final Score": row.get("Final Score"),
                    **check,
                }
            )
    return pd.DataFrame(flattened)


def _flatten_sources(rows: list[dict]) -> pd.DataFrame:
    flattened = []
    for row in rows:
        for source in row.get("Source Status", []):
            flattened.append(
                {
                    "Symbol": row.get("Symbol"),
                    "Company": row.get("Company"),
                    "Final Score": row.get("Final Score"),
                    "Source": source.get("source"),
                    "Status": source.get("status"),
                    "Message": source.get("message"),
                }
            )
    return pd.DataFrame(flattened)


def _section_summary(rows: list[dict]) -> pd.DataFrame:
    flattened = []
    for row in rows:
        for section, summary in (row.get("Section Summary") or {}).items():
            flattened.append(
                {
                    "Symbol": row.get("Symbol"),
                    "Company": row.get("Company"),
                    "Section": section,
                    "Passed": summary.get("Passed"),
                    "Failed": summary.get("Failed"),
                    "Points": round(summary.get("Points", 0), 1),
                }
            )
    return pd.DataFrame(flattened)


def _display_columns(df: pd.DataFrame) -> list[str]:
    preferred = [
        "Symbol",
        "Company",
        "Final Score",
        "Score",
        "Technical Score",
        "Fundamental Score",
        "TV Score",
        "TradingView",
        "Top Pattern",
        "Pattern Direction",
        "Pattern Confidence",
        "Price",
        "Change %",
        "RSI",
        "Trend",
        "Breakout Probability",
        "PE Ratio",
        "ROE",
        "ROCE",
        "Debt to Equity",
        "Profit Growth",
        "Passed Checks",
        "Failed Checks",
        "Source Count",
        "Primary Source",
    ]
    return [col for col in preferred if col in df.columns]


apply_page_config("Scanner | Indian Stock AI Agent")

st.sidebar.title("Indian Stock AI Agent")
st.sidebar.page_link("main.py", label="Dashboard")
st.sidebar.page_link("pages/Scanner.py", label="Scanner")
st.sidebar.page_link("pages/Watchlist.py", label="Watchlist")
st.sidebar.page_link("pages/Settings.py", label="Settings")
sidebar_footer()

st.title("All-in-One NSE Stock Analyst")
st.caption("No yfinance. The scanner uses accessible sources only, shows every check, and ranks stocks by visible rules.")

with st.container():
    controls = st.columns([1.5, 1, 1, 1])
    segment = controls[0].selectbox("Universe", options=segment_options(), index=0)
    scan_limit = controls[1].number_input("Return rows", min_value=10, max_value=250, value=25, step=5)
    max_symbols = controls[2].number_input("Analyze symbols", min_value=10, max_value=1800, value=50, step=10)
    include_custom = controls[3].toggle("Use custom symbols", value=False)

    if include_custom:
        symbols_text = st.text_area(
            "Custom NSE symbols",
            value="SIEMENS,LTM,LTIM,ANGELONE,RELIANCE,TCS,INFY,HDFCBANK",
            help="Comma-separated NSE symbols. Useful for focused checks and chart-pattern validation.",
            height=90,
        )
        universe = [item.strip().upper() for item in symbols_text.split(",") if item.strip()]
    else:
        universe = universe_for_segment(segment, limit=int(max_symbols))

    st.markdown(f"Prepared **{len(universe)}** symbols from **{segment}**.")

st.markdown("### Filters")
scan_names = list(SCAN_FUNCTIONS)
button_cols = st.columns(4)
selected_scan = None
for idx, scan_name in enumerate(scan_names):
    if button_cols[idx % 4].button(scan_name, use_container_width=True):
        selected_scan = scan_name

if selected_scan:
    st.session_state.selected_scan = selected_scan

active_scan = st.session_state.get("selected_scan", "All-in-One Rank")
rules = {
    "All-in-One Rank": "Ranks by visible final score across technical, fundamental, TradingView, pattern, and source checks.",
    "Techno-Funda Stocks": "Requires both technical and fundamental strength, with TradingView not bearish.",
    "Breakout Stocks": "Price above 50 DMA, RSI above 60, volume support, and breakout/resistance confirmation.",
    "Chart Pattern Stocks": "Ranks stocks with detected breakout, triangle, double-bottom, double-top, or breakdown patterns.",
    "Undervalued Stocks": "PE below broad threshold, ROE above 15, low debt, and growing profit.",
    "Swing Trade Stocks": "MACD bullish crossover, RSI 55-70, positive trend, and pattern support.",
    "Strong Fundamentals": "ROCE above 18, low debt, positive sales growth, and quality metrics.",
}
st.info(f"Active filter: **{active_scan}**. {rules.get(active_scan, '')}")

if st.button("Run Analysis", type="primary", use_container_width=True):
    with st.spinner(f"Collecting Yahoo/NSE/Screener/Trendlyne/TradingView data for {len(universe)} symbols..."):
        rows = SCAN_FUNCTIONS[active_scan](universe, int(scan_limit))
    st.session_state.scan_rows = rows
    st.session_state.scan_name = active_scan

rows = st.session_state.get("scan_rows", [])

if rows:
    df = pd.DataFrame(rows)
    visible_df = df[_display_columns(df)].copy()

    customize_cols = st.columns([1, 1, 1, 1])
    sort_options = [col for col in ["Final Score", "Score", "Pattern Confidence", "Technical Score", "Fundamental Score", "RSI", "Breakout Probability"] if col in visible_df.columns]
    sort_by = customize_cols[0].selectbox("Sort by", options=sort_options, index=0)
    min_score = customize_cols[1].slider("Minimum final score", min_value=0, max_value=100, value=0)
    pattern_only = customize_cols[2].toggle("Pattern only", value=False)
    passed_only = customize_cols[3].toggle("Hide failed checks in engine tabs", value=False)

    if "Final Score" in visible_df.columns:
        visible_df = visible_df[visible_df["Final Score"].fillna(0) >= min_score]
    if pattern_only and "Top Pattern" in visible_df.columns:
        visible_df = visible_df[visible_df["Top Pattern"].fillna("").astype(str).ne("")]
    visible_df = visible_df.sort_values(sort_by, ascending=False)
    visible_symbols = set(visible_df["Symbol"].tolist())
    visible_rows = [row for row in rows if row.get("Symbol") in visible_symbols]

    ranking_tab, sources_tab, technical_tab, pattern_tab, fundamental_tab, tv_tab, score_tab = st.tabs(
        ["Final Ranking", "Data Sources", "Technical Engine", "Pattern Engine", "Fundamental Engine", "TradingView Engine", "Score Engine"]
    )

    with ranking_tab:
        st.dataframe(visible_df, use_container_width=True, hide_index=True)
        st.download_button(
            "Download Ranking CSV",
            visible_df.to_csv(index=False).encode("utf-8"),
            file_name=f"{st.session_state.get('scan_name', active_scan).lower().replace(' ', '_')}.csv",
            mime="text/csv",
        )

    with sources_tab:
        st.caption("Every accessible source is shown independently. No yfinance calls are made.")
        source_df = _flatten_sources(visible_rows)
        if source_df.empty:
            st.warning("No source diagnostics were returned.")
        else:
            st.dataframe(source_df, use_container_width=True, hide_index=True)

    for tab, section, caption in [
        (technical_tab, "Technical", "Moving averages, RSI, MACD, volume, and breakout checks."),
        (pattern_tab, "Pattern", "Detected chart structure such as breakout, triangle, double bottom/top, or breakdown."),
        (fundamental_tab, "Fundamental", "Valuation, quality, leverage, and growth checks from Screener/Trendlyne/Yahoo direct quote."),
        (tv_tab, "TradingView", "TradingView recommendation checks."),
    ]:
        with tab:
            st.caption(caption)
            check_df = _flatten_checks(visible_rows, section=section)
            if passed_only and not check_df.empty:
                check_df = check_df[check_df["Status"] == "PASS"]
            if check_df.empty:
                st.warning(f"No {section.lower()} checks available for the visible rows.")
            else:
                st.dataframe(check_df, use_container_width=True, hide_index=True)

    with score_tab:
        st.caption("How the backend scoring engine reached the ranking.")
        st.markdown(
            """
            **Final Score Formula**

            `Final Score = Technical Score * 0.45 + Fundamental Score * 0.40 + TradingView Score * 0.15`

            Pattern strength contributes inside the technical score. Source coverage is shown separately so users can judge confidence.
            """
        )
        summary_df = _section_summary(visible_rows)
        if not summary_df.empty:
            st.dataframe(summary_df, use_container_width=True, hide_index=True)
else:
    st.info("Choose a filter and press Run Analysis. Try custom symbols like SIEMENS, LTM, LTIM, ANGELONE for pattern checks.")
