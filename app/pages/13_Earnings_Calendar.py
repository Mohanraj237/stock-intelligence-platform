from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from utils.theme import apply_theme, GREEN, RED, BLUE, CARD, BORDER, TEXT, TEXT_DIM, YELLOW
apply_theme()

from services.earnings_service import (
    get_upcoming_results, get_recent_earnings, get_earnings_calendar,
)
from services.universe_sync import get_universe_symbols, get_all_universe_names, universe_display_map

st.markdown("## 📅 Earnings Calendar")
st.markdown(
    f'<div style="color:{TEXT_DIM};font-size:0.85rem;margin-bottom:10px">'
    f'Upcoming quarterly results from NSE board meetings + recent earnings sentiment from Screener.in</div>',
    unsafe_allow_html=True,
)

tab_upcoming, tab_recent, tab_single = st.tabs([
    "📆 Upcoming Results", "📊 Recent Earnings (Universe)", "🔍 Stock-Level History"
])

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 1 — Upcoming results across the market
# ═══════════════════════════════════════════════════════════════════════════════
with tab_upcoming:
    u1, u2 = st.columns([1, 4])
    with u1:
        days_ahead = st.selectbox("Look ahead", [7, 14, 30, 60], index=1, key="ec_days")
    if st.button("🔄 Load Upcoming Results", type="primary", key="ec_load_up"):
        with st.spinner("Fetching upcoming board meetings from NSE…"):
            data = get_upcoming_results(days_ahead=int(days_ahead))
        st.session_state["ec_upcoming"] = data

    upcoming = st.session_state.get("ec_upcoming", [])
    if upcoming:
        st.success(f"**{len(upcoming)} upcoming results** within next {days_ahead} days.")

        df_up = pd.DataFrame(upcoming)
        df_up = df_up[["date", "symbol", "company", "purpose"]]
        df_up.columns = ["Date", "Symbol", "Company", "Purpose"]
        st.dataframe(df_up, use_container_width=True, hide_index=True, height=480)

        # Calendar grouping by date
        st.markdown("---")
        st.markdown('<div class="z-section">By Date</div>', unsafe_allow_html=True)
        grouped = df_up.groupby("Date")
        for date, group in grouped:
            with st.expander(f"📅 {date} — {len(group)} companies"):
                st.dataframe(group[["Symbol", "Company", "Purpose"]],
                              use_container_width=True, hide_index=True)

        st.download_button("📥 Export CSV", df_up.to_csv(index=False),
                           "upcoming_earnings.csv", "text/csv")
    else:
        if "ec_upcoming" in st.session_state:
            st.info("No upcoming results announcements in this window — try a longer range.")
        else:
            st.info("Click **Load Upcoming Results** to fetch from NSE.")

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 2 — Recent earnings per universe
# ═══════════════════════════════════════════════════════════════════════════════
with tab_recent:
    r1, r2, r3 = st.columns([2, 1, 1])
    with r1:
        disp_map  = universe_display_map()
        all_names = get_all_universe_names()
        labels    = [disp_map.get(n, n) for n in all_names]
        ec_label = st.selectbox("Universe", labels, key="ec_uni")
        ec_uni   = all_names[labels.index(ec_label)]
    with r2:
        ec_max = st.number_input("Max stocks", min_value=10, max_value=100, value=30,
                                  step=5, key="ec_max")
    with r3:
        sentiment_filter = st.selectbox(
            "Filter by sentiment",
            ["All", "POSITIVE", "MILDLY POSITIVE", "NEUTRAL", "MILDLY NEGATIVE", "NEGATIVE"],
            key="ec_sent",
        )

    if st.button("🚀 Scan Recent Earnings", type="primary", key="ec_scan"):
        symbols = get_universe_symbols(ec_uni)[:int(ec_max)]
        prog = st.progress(0.1, text=f"Fetching last quarter for {len(symbols)} stocks…")
        cal = get_earnings_calendar(symbols, days_ahead=int(days_ahead) if "ec_days" in st.session_state else 14,
                                    fetch_recent=True, max_workers=6)
        prog.empty()
        st.session_state["ec_recent_data"] = cal
        st.session_state["ec_recent_uni"]  = ec_uni

    cal = st.session_state.get("ec_recent_data")
    if cal:
        recent_map = cal.get("recent", {})
        rows = []
        for sym, qs in recent_map.items():
            if not qs:
                continue
            q = qs[0]
            rows.append({
                "Symbol": sym,
                "Quarter": q.get("quarter", ""),
                "Sales (Cr)": f"{q['sales']:,.1f}" if q.get("sales") else "—",
                "Net Profit (Cr)": f"{q['net_profit']:,.1f}" if q.get("net_profit") else "—",
                "OPM %": f"{q['opm']:.1f}%" if q.get("opm") is not None else "—",
                "Sales YoY": f"{q['sales_growth_yoy']:+.1f}%" if q.get("sales_growth_yoy") is not None else "—",
                "Profit YoY": f"{q['profit_growth_yoy']:+.1f}%" if q.get("profit_growth_yoy") is not None else "—",
                "Sentiment": q.get("sentiment", "UNKNOWN"),
                "_score": q.get("score", 0),
                "_color": q.get("sentiment_color", "neutral"),
            })

        if sentiment_filter != "All":
            rows = [r for r in rows if r["Sentiment"] == sentiment_filter]

        if not rows:
            st.warning("No results to show. Try a different universe or sentiment filter.")
        else:
            rows.sort(key=lambda r: r["_score"], reverse=True)
            df = pd.DataFrame(rows)

            # Counts metric strip
            pos = sum(1 for r in rows if "POSITIVE" in r["Sentiment"])
            neg = sum(1 for r in rows if "NEGATIVE" in r["Sentiment"])
            neu = len(rows) - pos - neg
            cm1, cm2, cm3, cm4 = st.columns(4)
            cm1.metric("Total Reported", len(rows))
            cm2.metric("Positive ▲", pos)
            cm3.metric("Negative ▼", neg)
            cm4.metric("Neutral —", neu)

            st.markdown("---")

            def _style(df):
                styles = pd.DataFrame("", index=df.index, columns=df.columns)
                for i in range(len(df)):
                    s = df.iloc[i]["Sentiment"]
                    color = (GREEN if "POSITIVE" in s else
                             RED if "NEGATIVE" in s else
                             YELLOW if s == "NEUTRAL" else TEXT_DIM)
                    styles.iloc[i, df.columns.get_loc("Sentiment")] = f"color:{color};font-weight:700"
                    for col in ["Sales YoY", "Profit YoY"]:
                        v = str(df.iloc[i][col])
                        if "+" in v: styles.iloc[i, df.columns.get_loc(col)] = f"color:{GREEN}"
                        elif "-" in v: styles.iloc[i, df.columns.get_loc(col)] = f"color:{RED}"
                return styles

            st.dataframe(
                df.drop(columns=["_score", "_color"]).style.apply(_style, axis=None),
                use_container_width=True, hide_index=True, height=480,
            )

            # Sentiment distribution chart
            ch1, ch2 = st.columns(2)
            with ch1:
                pie_df = pd.DataFrame({"label": ["Positive", "Negative", "Neutral"],
                                        "value": [pos, neg, neu]})
                fig_pie = go.Figure(go.Pie(
                    labels=pie_df["label"], values=pie_df["value"], hole=0.4,
                    marker=dict(colors=[GREEN, RED, YELLOW]),
                ))
                fig_pie.update_layout(
                    title="Earnings Sentiment Distribution",
                    template="plotly_dark", paper_bgcolor=CARD, plot_bgcolor=CARD,
                    height=300, margin=dict(l=10, r=10, t=40, b=10),
                )
                st.plotly_chart(fig_pie, use_container_width=True)

            with ch2:
                # Profit YoY histogram
                pg_vals = [r.get("Profit YoY") for r in rows]
                pg_nums = []
                for v in pg_vals:
                    if v == "—": continue
                    try: pg_nums.append(float(str(v).replace("%","").replace("+","")))
                    except Exception: pass
                if pg_nums:
                    fig_h = go.Figure(go.Histogram(
                        x=pg_nums, nbinsx=20,
                        marker_color=[GREEN if v >= 0 else RED for v in pg_nums],
                    ))
                    fig_h.add_vline(x=0, line_color=TEXT_DIM, line_dash="dash")
                    fig_h.update_layout(
                        title="Profit YoY Growth Distribution",
                        template="plotly_dark", paper_bgcolor=CARD, plot_bgcolor=CARD,
                        height=300, margin=dict(l=10, r=10, t=40, b=10),
                        xaxis=dict(title="YoY Profit Growth %", gridcolor=BORDER),
                        yaxis=dict(gridcolor=BORDER),
                    )
                    st.plotly_chart(fig_h, use_container_width=True)

            st.download_button("📥 Export CSV",
                               df.drop(columns=["_score","_color"]).to_csv(index=False),
                               f"earnings_{ec_uni.replace(' ','_')}.csv", "text/csv")

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 3 — Single-stock earnings history
# ═══════════════════════════════════════════════════════════════════════════════
with tab_single:
    h1, h2, h3 = st.columns([2, 2, 1])
    with h1:
        h_label = st.selectbox("Index", labels, key="ec_h_idx")
        h_uni   = all_names[labels.index(h_label)]
        h_syms  = get_universe_symbols(h_uni)
    with h2:
        h_sym = st.selectbox("Stock", h_syms, key="ec_h_sym")
    with h3:
        h_qs = st.number_input("Quarters", min_value=2, max_value=12, value=8, key="ec_h_qs")

    if st.button("📊 Load Earnings History", type="primary", key="ec_h_load"):
        with st.spinner(f"Fetching {h_qs} quarters for {h_sym}…"):
            history = get_recent_earnings(h_sym, n_quarters=int(h_qs))

        if not history:
            st.warning("No quarterly data available from Screener for this stock.")
        else:
            df_h = pd.DataFrame(history)
            df_disp = df_h.copy()
            df_disp = df_disp[["quarter", "sales", "net_profit", "opm",
                                "sales_growth_yoy", "profit_growth_yoy",
                                "sentiment", "sentiment_reason"]]
            df_disp.columns = ["Quarter", "Sales (Cr)", "Net Profit (Cr)", "OPM %",
                                "Sales YoY %", "Profit YoY %", "Sentiment", "Reason"]

            def _style_h(df):
                styles = pd.DataFrame("", index=df.index, columns=df.columns)
                for i in range(len(df)):
                    s = df.iloc[i]["Sentiment"]
                    c = (GREEN if "POSITIVE" in s else RED if "NEGATIVE" in s else YELLOW)
                    styles.iloc[i, df.columns.get_loc("Sentiment")] = f"color:{c};font-weight:700"
                return styles

            st.dataframe(df_disp.style.apply(_style_h, axis=None),
                          use_container_width=True, hide_index=True)

            # Bar chart of profit growth YoY
            sales_seq = [h.get("sales") for h in reversed(history)]
            np_seq    = [h.get("net_profit") for h in reversed(history)]
            qs_seq    = [h.get("quarter") for h in reversed(history)]

            fig = go.Figure()
            fig.add_trace(go.Bar(name="Sales (Cr)", x=qs_seq, y=sales_seq, marker_color=BLUE))
            fig.add_trace(go.Bar(name="Net Profit (Cr)", x=qs_seq, y=np_seq, marker_color=GREEN))
            fig.update_layout(
                barmode="group", template="plotly_dark", paper_bgcolor=CARD, plot_bgcolor=CARD,
                height=320, margin=dict(l=10, r=10, t=40, b=20),
                title=f"{h_sym} — Quarterly Sales & Profit (last {len(history)} quarters)",
                xaxis=dict(gridcolor=BORDER), yaxis=dict(gridcolor=BORDER),
                legend=dict(orientation="h"),
            )
            st.plotly_chart(fig, use_container_width=True)

            # Sentiment timeline
            sentiment_pts = [{"q": h["quarter"],
                              "score": h["score"],
                              "label": h["sentiment"]} for h in reversed(history)]
            fig_s = go.Figure(go.Scatter(
                x=[p["q"] for p in sentiment_pts],
                y=[p["score"] for p in sentiment_pts],
                mode="lines+markers+text",
                marker=dict(size=12, color=[GREEN if p["score"] > 0 else RED if p["score"] < 0 else YELLOW
                                              for p in sentiment_pts]),
                line=dict(color=TEXT_DIM, width=1, dash="dot"),
                text=[p["label"][:8] for p in sentiment_pts],
                textposition="top center", textfont=dict(size=9, color=TEXT),
            ))
            fig_s.add_hline(y=0, line_color=TEXT_DIM, line_dash="dash")
            fig_s.update_layout(
                title="Sentiment Trend (positive ↑  /  negative ↓)",
                template="plotly_dark", paper_bgcolor=CARD, plot_bgcolor=CARD,
                height=260, margin=dict(l=10, r=10, t=40, b=20),
                xaxis=dict(gridcolor=BORDER), yaxis=dict(gridcolor=BORDER, title="Sentiment Score"),
            )
            st.plotly_chart(fig_s, use_container_width=True)
