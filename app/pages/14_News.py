from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime

from utils.theme import apply_theme, GREEN, RED, BLUE, CARD, BORDER, TEXT, TEXT_DIM, YELLOW
apply_theme()

from services.news_service import (
    get_market_news, get_stock_news, get_nse_announcements,
    RSS_FEEDS, classify_sentiment,
)
from services.universe_sync import get_universe_symbols, get_all_universe_names, universe_display_map

st.markdown("## 📰 News Feed")
st.markdown(
    f'<div style="color:{TEXT_DIM};font-size:0.85rem;margin-bottom:10px">'
    f'Aggregated headlines from Moneycontrol · Economic Times · Business Standard · LiveMint '
    f'· NSE corporate announcements. All feeds are free and require no API key.</div>',
    unsafe_allow_html=True,
)

tab_market, tab_stock, tab_announce = st.tabs([
    "🌐 Market News", "🔍 Stock-Specific", "📢 NSE Announcements"
])

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 1 — Aggregated market news
# ═══════════════════════════════════════════════════════════════════════════════
with tab_market:
    n1, n2, n3 = st.columns([2, 1, 1])
    with n1:
        sources = st.multiselect("Sources (empty = all)", list(RSS_FEEDS.keys()),
                                  default=[], key="news_src")
    with n2:
        limit = st.number_input("Max headlines", min_value=20, max_value=200,
                                 value=80, step=20, key="news_limit")
    with n3:
        sent_filter = st.selectbox("Sentiment",
            ["All", "POSITIVE", "MILDLY POSITIVE", "NEUTRAL", "MILDLY NEGATIVE", "NEGATIVE"],
            key="news_sent")

    if st.button("🔄 Load News", type="primary", key="news_load"):
        with st.spinner(f"Fetching {len(sources) or len(RSS_FEEDS)} RSS sources in parallel…"):
            news = get_market_news(limit=int(limit), sources=sources or None)
        st.session_state["news_data"] = news

    news = st.session_state.get("news_data", [])
    if news:
        if sent_filter != "All":
            news = [n for n in news if n["sentiment"] == sent_filter]

        # Sentiment counts
        pos = sum(1 for n in news if "POSITIVE" in n["sentiment"])
        neg = sum(1 for n in news if "NEGATIVE" in n["sentiment"])
        neu = len(news) - pos - neg
        cm1, cm2, cm3, cm4 = st.columns(4)
        cm1.metric("Total Headlines", len(news))
        cm2.metric("Positive ▲", pos)
        cm3.metric("Negative ▼", neg)
        cm4.metric("Neutral —", neu)

        st.markdown("---")

        # Render headlines as cards
        for n in news:
            color = (GREEN if "POSITIVE" in n["sentiment"] else
                     RED if "NEGATIVE" in n["sentiment"] else
                     YELLOW if n["sentiment"] == "NEUTRAL" else TEXT_DIM)
            bg = (f"rgba(38,166,154,0.06)" if "POSITIVE" in n["sentiment"] else
                  f"rgba(239,83,80,0.06)" if "NEGATIVE" in n["sentiment"] else
                  CARD)
            sym_chip = f'<span style="background:{color};color:#fff;padding:2px 8px;border-radius:10px;font-size:0.7rem;margin-right:6px">{n["sentiment"]}</span>'
            src_chip = f'<span style="color:{TEXT_DIM};font-size:0.7rem;margin-right:6px">[{n["source"]}]</span>'
            ts = ""
            if n.get("ts"):
                try:
                    ts = datetime.fromtimestamp(n["ts"]).strftime("%Y-%m-%d %H:%M")
                except Exception:
                    ts = ""
            st.markdown(
                f'<div style="background:{bg};border-left:3px solid {color};'
                f'border-radius:0 6px 6px 0;padding:8px 14px;margin:4px 0">'
                f'{sym_chip}{src_chip}'
                f'<span style="color:{TEXT_DIM};font-size:0.7rem">{ts}</span><br>'
                f'<a href="{n["link"]}" target="_blank" style="color:{TEXT};font-weight:600;text-decoration:none">'
                f'{n["title"]}</a><br>'
                f'<span style="color:{TEXT_DIM};font-size:0.78rem">{n.get("summary","")[:200]}…</span>'
                f'</div>',
                unsafe_allow_html=True,
            )

        # Sentiment distribution chart
        st.markdown("---")
        ch1, ch2 = st.columns(2)
        with ch1:
            fig_pie = go.Figure(go.Pie(
                labels=["Positive", "Negative", "Neutral"],
                values=[pos, neg, neu], hole=0.45,
                marker=dict(colors=[GREEN, RED, YELLOW]),
            ))
            fig_pie.update_layout(
                title="Market Sentiment from News",
                template="plotly_dark", paper_bgcolor=CARD, plot_bgcolor=CARD,
                height=300, margin=dict(l=10, r=10, t=40, b=10),
            )
            st.plotly_chart(fig_pie, use_container_width=True)

        with ch2:
            src_counts = pd.Series([n["source"] for n in news]).value_counts()
            fig_src = go.Figure(go.Bar(
                x=list(src_counts.values), y=list(src_counts.index),
                orientation="h", marker_color=BLUE,
                text=list(src_counts.values), textposition="outside",
            ))
            fig_src.update_layout(
                title="Headlines by Source", template="plotly_dark",
                paper_bgcolor=CARD, plot_bgcolor=CARD, height=300,
                margin=dict(l=10, r=10, t=40, b=10),
                xaxis=dict(gridcolor=BORDER), yaxis=dict(gridcolor=BORDER),
            )
            st.plotly_chart(fig_src, use_container_width=True)

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 2 — Stock-specific news
# ═══════════════════════════════════════════════════════════════════════════════
with tab_stock:
    s1, s2, s3 = st.columns([2, 2, 1])
    with s1:
        disp_map  = universe_display_map()
        all_names = get_all_universe_names()
        labels    = [disp_map.get(n, n) for n in all_names]
        n_label = st.selectbox("Index", labels, key="news_s_idx")
        n_uni   = all_names[labels.index(n_label)]
        n_syms  = get_universe_symbols(n_uni)
    with s2:
        n_sym = st.selectbox("Stock", n_syms, key="news_s_sym")
    with s3:
        n_lim = st.number_input("Max news", min_value=5, max_value=50, value=15, key="news_s_lim")

    if st.button("🔍 Find News", type="primary", key="news_s_btn"):
        with st.spinner(f"Searching news mentioning {n_sym}…"):
            stock_news = get_stock_news(n_sym, limit=int(n_lim))
        if not stock_news:
            st.info(f"No news found for {n_sym} in current RSS feeds. Check NSE Announcements tab for disclosures.")
        else:
            st.success(f"**{len(stock_news)} headlines** mentioning {n_sym}.")
            for n in stock_news:
                color = (GREEN if "POSITIVE" in n["sentiment"] else
                         RED if "NEGATIVE" in n["sentiment"] else YELLOW)
                bg = (f"rgba(38,166,154,0.06)" if "POSITIVE" in n["sentiment"] else
                      f"rgba(239,83,80,0.06)" if "NEGATIVE" in n["sentiment"] else CARD)
                ts = ""
                if n.get("ts"):
                    try: ts = datetime.fromtimestamp(n["ts"]).strftime("%Y-%m-%d %H:%M")
                    except Exception: ts = ""
                st.markdown(
                    f'<div style="background:{bg};border-left:3px solid {color};'
                    f'padding:8px 14px;margin:4px 0;border-radius:0 6px 6px 0">'
                    f'<span style="color:{color};font-weight:700">{n["sentiment"]}</span> '
                    f'<span style="color:{TEXT_DIM};font-size:0.72rem">[{n["source"]}] {ts}</span><br>'
                    f'<a href="{n["link"]}" target="_blank" style="color:{TEXT};text-decoration:none">'
                    f'<b>{n["title"]}</b></a><br>'
                    f'<span style="color:{TEXT_DIM};font-size:0.78rem">{n.get("summary","")[:240]}…</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 3 — NSE corporate announcements
# ═══════════════════════════════════════════════════════════════════════════════
with tab_announce:
    a1, a2 = st.columns([2, 1])
    with a1:
        ann_label = st.selectbox("Index (for symbol picker)", labels, key="ann_idx")
        ann_uni   = all_names[labels.index(ann_label)]
        ann_syms  = ["(All — market-wide)"] + get_universe_symbols(ann_uni)
        ann_sym   = st.selectbox("Symbol", ann_syms, key="ann_sym")
    with a2:
        ann_btn = st.button("🔄 Load Announcements", type="primary", key="ann_btn")

    if ann_btn:
        sym_arg = None if ann_sym == "(All — market-wide)" else ann_sym
        with st.spinner("Fetching NSE corporate announcements…"):
            anns = get_nse_announcements(symbol=sym_arg)
        st.session_state["news_anns"] = anns

    anns = st.session_state.get("news_anns", [])
    if anns:
        st.success(f"**{len(anns)} announcements** loaded.")
        df_a = pd.DataFrame([{
            "Date":     a.get("date", "")[:16],
            "Symbol":   a.get("symbol", ""),
            "Subject":  a.get("subject", "")[:80],
            "Title":    a.get("title", "")[:140],
            "Sentiment": a.get("sentiment", "NEUTRAL"),
        } for a in anns])

        def _style_a(df):
            styles = pd.DataFrame("", index=df.index, columns=df.columns)
            for i in range(len(df)):
                s = df.iloc[i]["Sentiment"]
                c = (GREEN if "POSITIVE" in s else RED if "NEGATIVE" in s else YELLOW)
                styles.iloc[i, df.columns.get_loc("Sentiment")] = f"color:{c};font-weight:700"
            return styles

        st.dataframe(df_a.style.apply(_style_a, axis=None),
                      use_container_width=True, hide_index=True, height=560)

        st.download_button("📥 Export CSV", df_a.to_csv(index=False),
                            f"announcements_{ann_sym.replace(' ','_')}.csv", "text/csv")
