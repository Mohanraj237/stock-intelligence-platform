from __future__ import annotations
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from utils.theme import apply_theme, GREEN, RED, BLUE, ORANGE, CARD, BORDER, TEXT, TEXT_DIM, BG
apply_theme()

from services.nse_service import (
    get_market_status, get_index_performance, get_index_quotes,
    get_sector_performance, get_fii_dii_data,
)
from services.universe_sync import get_all_universe_names, universe_display_map

# ── Header row ────────────────────────────────────────────────────────────────
h_col, r_col = st.columns([5, 1])
with h_col:
    st.markdown("## 📊 Market Dashboard")
with r_col:
    auto_refresh = st.toggle("🔄 Auto", value=False, key="dash_auto_refresh",
                             help="Auto-refresh every 60 seconds")

st.markdown("---")

# ── Cache helpers ─────────────────────────────────────────────────────────────
@st.cache_data(ttl=120, show_spinner=False)
def _market_status():
    return get_market_status()

@st.cache_data(ttl=120, show_spinner=False)
def _index_perf():
    return get_index_performance()

@st.cache_data(ttl=300, show_spinner=False)
def _sector_perf():
    return get_sector_performance()

@st.cache_data(ttl=300, show_spinner=False)
def _fii_dii():
    return get_fii_dii_data()

@st.cache_data(ttl=300, show_spinner=False)
def _index_quotes(universe: str):
    return get_index_quotes(universe)

# ── Load core data ─────────────────────────────────────────────────────────────
with st.spinner("Loading market data…"):
    mkt_status  = _market_status()
    idx_perf    = _index_perf()

# ── Market Status Banner ───────────────────────────────────────────────────────
status_val = str(mkt_status.get("status", "unknown")).upper()
is_open    = "OPEN" in status_val
status_col = GREEN if is_open else RED
status_lbl = "● MARKET OPEN" if is_open else "● MARKET CLOSED"
trade_date = mkt_status.get("trade_date", "")
mkt_cap    = mkt_status.get("market_cap_lakh_cr")
gift_nifty = mkt_status.get("gift_nifty")
gift_pct   = mkt_status.get("gift_nifty_change_pct")

banner_parts = [f'<span style="color:{status_col};font-weight:700">{status_lbl}</span>']
if trade_date:
    banner_parts.append(f'<span style="color:{TEXT_DIM};margin-left:16px">{trade_date}</span>')
if mkt_cap:
    try:
        banner_parts.append(f'<span style="color:{TEXT_DIM};margin-left:16px">Mkt Cap: <span style="color:{TEXT};font-weight:600">₹{float(mkt_cap):,.0f} L Cr</span></span>')
    except Exception:
        pass
if gift_nifty:
    try:
        gc = GREEN if float(gift_pct or 0) >= 0 else RED
        banner_parts.append(f'<span style="color:{TEXT_DIM};margin-left:16px">GIFT Nifty: <span style="color:{gc};font-weight:600">₹{float(gift_nifty):,.1f} ({float(gift_pct or 0):+.2f}%)</span></span>')
    except Exception:
        pass
st.markdown(
    f'<div style="background:{CARD};border:1px solid {BORDER};border-radius:8px;padding:10px 18px;margin-bottom:14px">'
    + " &nbsp;|&nbsp; ".join(banner_parts) + "</div>",
    unsafe_allow_html=True,
)

# ── Index Performance Cards ───────────────────────────────────────────────────
if idx_perf:
    n_cols = min(len(idx_perf), 6)
    idx_cols = st.columns(n_cols)
    for col, item in zip(idx_cols, idx_perf[:n_cols]):
        pct  = item.get("pct") or 0
        last = item.get("last") or 0
        chg  = item.get("change") or 0
        # Use change (₹) for sign — pct is sometimes 0 from NSE when market
        # is closed and only the absolute change is populated.
        try:
            chg_f, last_f, pct_f = float(chg), float(last), float(pct)
            direction = chg_f if chg_f != 0 else pct_f
            # Compute pct from change/last if NSE gave us 0
            if pct_f == 0 and chg_f != 0 and last_f > 0:
                prev = last_f - chg_f
                if prev > 0:
                    pct = chg_f / prev * 100
        except Exception:
            direction = 0
        is_up = direction >= 0
        ic   = GREEN if is_up else RED
        sign = "▲" if is_up else "▼"
        short_name = item["index"].replace("NIFTY ", "")
        with col:
            st.markdown(
                f'<div class="z-card" style="padding:10px 14px;text-align:center">'
                f'<div class="z-card-title">{short_name}</div>'
                f'<div style="font-size:1.15rem;font-weight:700;color:{TEXT}">{float(last):,.1f}</div>'
                f'<div style="font-size:0.82rem;color:{ic};font-weight:600">{sign} {float(chg):+,.1f} ({float(pct):+.2f}%)</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

st.markdown("---")

# ═══════════════════════════════════════════════════════════════════════════════
# TABS
# ═══════════════════════════════════════════════════════════════════════════════
tab_ov, tab_movers, tab_sector, tab_fii, tab_universe = st.tabs([
    "📈 Overview", "🚀 Top Movers", "🏭 Sectors", "💰 FII / DII", "🔍 Universe"
])

# ─────────────────────────────────────────────────────────────────────────────
# TAB 1 — Overview: Market Breadth
# ─────────────────────────────────────────────────────────────────────────────
with tab_ov:
    try:
        nifty50_quotes = _index_quotes("NIFTY 50")
    except Exception:
        nifty50_quotes = []

    if nifty50_quotes:
        adv = sum(1 for s in nifty50_quotes if (s.get("change_pct") or 0) > 0)
        dec = sum(1 for s in nifty50_quotes if (s.get("change_pct") or 0) < 0)
        unch = len(nifty50_quotes) - adv - dec

        b1, b2, b3, b4, b5 = st.columns(5)
        with b1:
            st.metric("Total Stocks", len(nifty50_quotes))
        with b2:
            st.metric("Advancing", adv, delta=f"{adv/max(len(nifty50_quotes),1)*100:.0f}%")
        with b3:
            st.metric("Declining", dec, delta=f"-{dec/max(len(nifty50_quotes),1)*100:.0f}%", delta_color="inverse")
        with b4:
            st.metric("Unchanged", unch)
        with b5:
            ad_ratio = adv / max(dec, 1)
            st.metric("A/D Ratio", f"{ad_ratio:.2f}", delta="Bullish" if ad_ratio > 1.5 else ("Bearish" if ad_ratio < 0.7 else "Neutral"))

        # Breadth bar
        total = adv + dec + unch
        if total > 0:
            fig_breadth = go.Figure()
            fig_breadth.add_trace(go.Bar(
                x=[adv], y=["Breadth"], orientation="h", name="Advancing",
                marker_color=GREEN, text=[f"▲ {adv}"], textposition="inside",
            ))
            fig_breadth.add_trace(go.Bar(
                x=[unch], y=["Breadth"], orientation="h", name="Unchanged",
                marker_color=TEXT_DIM, text=[f"— {unch}"], textposition="inside",
            ))
            fig_breadth.add_trace(go.Bar(
                x=[dec], y=["Breadth"], orientation="h", name="Declining",
                marker_color=RED, text=[f"▼ {dec}"], textposition="inside",
            ))
            fig_breadth.update_layout(
                barmode="stack", height=80, showlegend=False,
                margin=dict(l=0, r=0, t=4, b=4),
                paper_bgcolor=CARD, plot_bgcolor=CARD,
                xaxis=dict(visible=False), yaxis=dict(visible=False),
            )
            st.plotly_chart(fig_breadth, use_container_width=True)

        st.markdown("---")

        # Change distribution histogram
        pct_vals = [s.get("change_pct") for s in nifty50_quotes if s.get("change_pct") is not None]
        if pct_vals:
            fig_dist = go.Figure()
            fig_dist.add_trace(go.Histogram(
                x=pct_vals, nbinsx=20,
                marker_color=[GREEN if v >= 0 else RED for v in pct_vals],
                name="Change %",
            ))
            fig_dist.update_layout(
                title="NIFTY 50 — Change % Distribution",
                template="plotly_dark", paper_bgcolor=CARD, plot_bgcolor=CARD,
                height=220, margin=dict(l=10, r=10, t=36, b=20),
                xaxis=dict(title="Change %", gridcolor=BORDER),
                yaxis=dict(title="Count", gridcolor=BORDER),
                bargap=0.05,
            )
            st.plotly_chart(fig_dist, use_container_width=True)

        # 52W High/Low proximity cards
        st.markdown('<div class="z-section">52-Week Extremes — NIFTY 50</div>', unsafe_allow_html=True)
        near_high = sorted(
            [s for s in nifty50_quotes if s.get("near_52w_high") is not None],
            key=lambda x: float(x.get("near_52w_high") or 0), reverse=True,
        )[:5]
        near_low = sorted(
            [s for s in nifty50_quotes if s.get("near_52w_low") is not None],
            key=lambda x: float(x.get("near_52w_low") or 0), reverse=True,
        )[:5]

        wk_hi_col, wk_lo_col = st.columns(2)
        with wk_hi_col:
            st.markdown(f'<div style="color:{GREEN};font-weight:700;font-size:0.83rem;margin-bottom:6px">▲ NEAR 52W HIGH</div>', unsafe_allow_html=True)
            for s in near_high:
                pct = s.get("change_pct") or 0
                wh  = s.get("near_52w_high") or 0
                c   = GREEN if float(pct) >= 0 else RED
                st.markdown(
                    f'<div class="z-stock-row">'
                    f'<span style="color:{TEXT};font-weight:700;min-width:100px">{s["symbol"]}</span>'
                    f'<span style="color:{TEXT_DIM};font-size:0.82rem">₹{float(s.get("price") or 0):,.2f}</span>'
                    f'<span style="color:{c};font-weight:600">{float(pct):+.2f}%</span>'
                    f'<span style="color:{GREEN};font-size:0.8rem">{float(wh):.1f}% to 52W Hi</span>'
                    f'</div>', unsafe_allow_html=True,
                )
        with wk_lo_col:
            st.markdown(f'<div style="color:{RED};font-weight:700;font-size:0.83rem;margin-bottom:6px">▼ NEAR 52W LOW</div>', unsafe_allow_html=True)
            for s in near_low:
                pct = s.get("change_pct") or 0
                wl  = s.get("near_52w_low") or 0
                c   = GREEN if float(pct) >= 0 else RED
                st.markdown(
                    f'<div class="z-stock-row">'
                    f'<span style="color:{TEXT};font-weight:700;min-width:100px">{s["symbol"]}</span>'
                    f'<span style="color:{TEXT_DIM};font-size:0.82rem">₹{float(s.get("price") or 0):,.2f}</span>'
                    f'<span style="color:{c};font-weight:600">{float(pct):+.2f}%</span>'
                    f'<span style="color:{RED};font-size:0.8rem">{float(wl):.1f}% to 52W Lo</span>'
                    f'</div>', unsafe_allow_html=True,
                )
    else:
        st.info("Market overview data unavailable — NSE API may be offline.")


# ─────────────────────────────────────────────────────────────────────────────
# TAB 2 — Top Movers
# ─────────────────────────────────────────────────────────────────────────────
with tab_movers:
    disp_map  = universe_display_map()
    all_names = get_all_universe_names()
    labels    = [disp_map.get(n, n) for n in all_names]

    mv_col1, mv_col2, mv_col3 = st.columns([3, 1, 1])
    with mv_col1:
        mv_label    = st.selectbox("Universe", labels, key="dash_mv_uni")
        mv_universe = all_names[labels.index(mv_label)]
    with mv_col2:
        top_n = st.selectbox("Top N", [5, 10, 15, 20], index=1, key="dash_mv_topn")
    with mv_col3:
        sort_by = st.selectbox("Sort by", ["Change %", "Volume", "30D Return", "365D Return"], key="dash_mv_sort")

    mv_btn, _ = st.columns([1, 4])
    with mv_btn:
        load_movers = st.button("🔄 Load Movers", type="primary", key="dash_load_movers")

    if load_movers or st.session_state.get("dash_movers_data") is not None:
        if load_movers:
            with st.spinner("Fetching live movers…"):
                quotes = _index_quotes(mv_universe)
            st.session_state["dash_movers_data"] = quotes
        else:
            quotes = st.session_state.get("dash_movers_data", [])

        if quotes:
            sort_key_map = {
                "Change %":   "change_pct",
                "Volume":     "volume",
                "30D Return": "return_30d",
                "365D Return":"return_365d",
            }
            sk = sort_key_map.get(sort_by, "change_pct")

            sorted_asc  = sorted(quotes, key=lambda x: float(x.get(sk) or 0))
            sorted_desc = sorted(quotes, key=lambda x: float(x.get(sk) or 0), reverse=True)

            gainers = sorted_desc[:top_n]
            losers  = sorted_asc[:top_n]

            def _mover_row(s):
                p   = s.get("price") or 0
                chg = s.get("change_pct") or 0
                vol = s.get("volume") or 0
                r30 = s.get("return_30d") or 0
                return {
                    "Symbol":    s["symbol"],
                    "Price":     f"₹{float(p):,.2f}",
                    "Change %":  f"{float(chg):+.2f}%",
                    "Volume":    f"{float(vol)/1e5:.1f}L" if vol else "—",
                    "30D Ret%":  f"{float(r30):+.2f}%",
                    "_chg":      float(chg),
                }

            df_gain = pd.DataFrame([_mover_row(s) for s in gainers])
            df_lose = pd.DataFrame([_mover_row(s) for s in losers])

            def _style_movers(df, up=True):
                styles = pd.DataFrame("", index=df.index, columns=df.columns)
                c = GREEN if up else RED
                styles["Change %"] = f"color:{c};font-weight:700"
                return styles

            gcol, lcol = st.columns(2)
            with gcol:
                st.markdown(f'<div style="color:{GREEN};font-weight:700;font-size:0.85rem;margin-bottom:6px">▲ TOP GAINERS ({mv_label})</div>', unsafe_allow_html=True)
                st.dataframe(
                    df_gain.drop(columns=["_chg"]).style.apply(lambda df: _style_movers(df, True), axis=None),
                    use_container_width=True, hide_index=True,
                )
            with lcol:
                st.markdown(f'<div style="color:{RED};font-weight:700;font-size:0.85rem;margin-bottom:6px">▼ TOP LOSERS ({mv_label})</div>', unsafe_allow_html=True)
                st.dataframe(
                    df_lose.drop(columns=["_chg"]).style.apply(lambda df: _style_movers(df, False), axis=None),
                    use_container_width=True, hide_index=True,
                )

            # Bar chart: top gainers vs losers
            top5g = sorted_desc[:5]
            top5l = sorted_asc[:5]
            syms_chart = [s["symbol"] for s in top5g] + [s["symbol"] for s in top5l]
            vals_chart = [float(s.get("change_pct") or 0) for s in top5g + top5l]
            colors_chart = [GREEN if v >= 0 else RED for v in vals_chart]

            fig_mv = go.Figure(go.Bar(
                x=syms_chart, y=vals_chart,
                marker_color=colors_chart, text=[f"{v:+.2f}%" for v in vals_chart],
                textposition="outside",
            ))
            fig_mv.update_layout(
                title="Top Gainers & Losers",
                template="plotly_dark", paper_bgcolor=CARD, plot_bgcolor=CARD,
                height=280, margin=dict(l=10, r=10, t=40, b=10),
                xaxis=dict(gridcolor=BORDER), yaxis=dict(gridcolor=BORDER, title="Change %"),
            )
            st.plotly_chart(fig_mv, use_container_width=True)

            # Volume leaders
            st.markdown('<div class="z-section">Volume Leaders</div>', unsafe_allow_html=True)
            vol_leaders = sorted(quotes, key=lambda x: float(x.get("volume") or 0), reverse=True)[:10]
            df_vol = pd.DataFrame([{
                "Symbol": s["symbol"],
                "Price":  f"₹{float(s.get('price') or 0):,.2f}",
                "Volume (L)": f"{float(s.get('volume') or 0)/1e5:.1f}",
                "Turnover (Cr)": f"₹{float(s.get('turnover') or 0)/1e7:.1f}",
                "Change %": f"{float(s.get('change_pct') or 0):+.2f}%",
            } for s in vol_leaders])

            def _style_vol(df):
                styles = pd.DataFrame("", index=df.index, columns=df.columns)
                for i, val in enumerate(df["Change %"]):
                    try:
                        c = GREEN if float(val.replace("+","").replace("%","")) >= 0 else RED
                        styles.iloc[i, df.columns.get_loc("Change %")] = f"color:{c};font-weight:600"
                    except Exception:
                        pass
                return styles

            st.dataframe(df_vol.style.apply(_style_vol, axis=None), use_container_width=True, hide_index=True)
        else:
            st.warning("No data returned for this universe — NSE API may be rate-limiting.")
    else:
        st.info("Select a universe and click **Load Movers** to fetch live data.")

# ─────────────────────────────────────────────────────────────────────────────
# TAB 3 — Sectors
# ─────────────────────────────────────────────────────────────────────────────
with tab_sector:
    sec_btn, _ = st.columns([1, 4])
    with sec_btn:
        load_sectors = st.button("🔄 Load Sector Data", type="primary", key="dash_load_sectors")

    if load_sectors or st.session_state.get("dash_sector_data") is not None:
        if load_sectors:
            with st.spinner("Fetching sector performance…"):
                sector_data = _sector_perf()
            st.session_state["dash_sector_data"] = sector_data
        else:
            sector_data = st.session_state.get("dash_sector_data", [])

        if sector_data:
            # Treemap heatmap
            df_sec = pd.DataFrame(sector_data)
            df_sec["pct"] = df_sec["pct"].apply(lambda x: float(x or 0))
            df_sec["color_val"] = df_sec["pct"]
            df_sec["label"] = df_sec.apply(
                lambda r: f"{r['sector']}<br>{r['pct']:+.2f}%", axis=1
            )

            fig_tree = go.Figure(go.Treemap(
                labels=df_sec["sector"],
                parents=["" for _ in df_sec.iterrows()],
                values=[max(abs(float(v)), 0.1) for v in df_sec["pct"]],
                customdata=df_sec[["pct", "last", "advancing", "declining"]].values,
                hovertemplate=(
                    "<b>%{label}</b><br>"
                    "Change: %{customdata[0]:+.2f}%<br>"
                    "Level: %{customdata[1]:,.1f}<br>"
                    "Adv/Dec: %{customdata[2]}/%{customdata[3]}<extra></extra>"
                ),
                text=df_sec["label"],
                textinfo="text",
                marker=dict(
                    colors=df_sec["pct"],
                    colorscale=[[0, RED], [0.45, "#2a2e39"], [0.55, "#2a2e39"], [1, GREEN]],
                    cmid=0,
                    showscale=True,
                    colorbar=dict(
                        title=dict(text="Change %", font=dict(color=TEXT)),
                        tickfont=dict(color=TEXT),
                        bgcolor=CARD, bordercolor=BORDER,
                    ),
                ),
            ))
            fig_tree.update_layout(
                paper_bgcolor=BG, font=dict(color=TEXT),
                height=440, margin=dict(t=20, b=10, l=10, r=10),
            )
            st.plotly_chart(fig_tree, use_container_width=True)

            # Sector table
            st.markdown('<div class="z-section">Sector Summary</div>', unsafe_allow_html=True)
            df_sec_disp = df_sec[["sector", "last", "pct", "advancing", "declining", "stocks"]].copy()
            df_sec_disp.columns = ["Sector", "Level", "Change %", "Advancing", "Declining", "Stocks"]
            df_sec_disp["Change %"] = df_sec_disp["Change %"].apply(lambda v: f"{float(v):+.2f}%")
            df_sec_disp["Level"]    = df_sec_disp["Level"].apply(lambda v: f"{float(v or 0):,.1f}")

            def _style_sec(df):
                styles = pd.DataFrame("", index=df.index, columns=df.columns)
                for i, val in enumerate(df["Change %"]):
                    try:
                        c = GREEN if float(val.replace("+","").replace("%","")) >= 0 else RED
                        styles.iloc[i, df.columns.get_loc("Change %")] = f"color:{c};font-weight:700"
                    except Exception:
                        pass
                return styles

            st.dataframe(
                df_sec_disp.style.apply(_style_sec, axis=None),
                use_container_width=True, hide_index=True,
            )

            # Bar chart
            fig_bar = go.Figure(go.Bar(
                x=df_sec["sector"], y=df_sec["pct"],
                marker_color=[GREEN if v >= 0 else RED for v in df_sec["pct"]],
                text=[f"{v:+.2f}%" for v in df_sec["pct"]],
                textposition="outside",
            ))
            fig_bar.update_layout(
                template="plotly_dark", paper_bgcolor=CARD, plot_bgcolor=CARD,
                height=300, margin=dict(l=0, r=0, t=20, b=40),
                xaxis=dict(gridcolor=BORDER, tickangle=-30),
                yaxis=dict(gridcolor=BORDER, title="Change %"),
            )
            st.plotly_chart(fig_bar, use_container_width=True)
        else:
            st.warning("Sector data unavailable — NSE API may be rate-limiting.")
    else:
        st.info("Click **Load Sector Data** to fetch live sector performance.")

# ─────────────────────────────────────────────────────────────────────────────
# TAB 4 — FII / DII
# ─────────────────────────────────────────────────────────────────────────────
with tab_fii:
    fii_btn, _ = st.columns([1, 4])
    with fii_btn:
        load_fii = st.button("🔄 Load FII/DII Data", type="primary", key="dash_load_fii")

    if load_fii or st.session_state.get("dash_fii_data") is not None:
        if load_fii:
            with st.spinner("Fetching FII/DII data…"):
                fii_rows = _fii_dii()
            st.session_state["dash_fii_data"] = fii_rows
        else:
            fii_rows = st.session_state.get("dash_fii_data", [])

        if fii_rows:
            df_fii = pd.DataFrame(fii_rows)
            for col in ["fii_buy","fii_sell","fii_net","dii_buy","dii_sell","dii_net"]:
                df_fii[col] = pd.to_numeric(df_fii[col], errors="coerce")
            # If every numeric column is NaN, the API returned no usable data
            num_cols = ["fii_buy","fii_sell","fii_net","dii_buy","dii_sell","dii_net"]
            if df_fii[num_cols].isna().all().all():
                st.info("FII/DII numeric values not yet published by NSE for the latest date.")
                fii_rows = []  # treat as no data
        if fii_rows:

            # Latest day summary cards
            latest = df_fii.iloc[0] if not df_fii.empty else {}
            f1, f2, f3, d1, d2, d3 = st.columns(6)
            def _fii_card(col, label, val):
                try:
                    fv = float(val)
                    col.metric(label, f"₹{abs(fv)/100:.1f}Cr", delta=f"{'+' if fv>=0 else ''}{fv/100:.1f}")
                except Exception:
                    col.metric(label, "—")

            st.markdown(f'<div class="z-section">Latest Day — {latest.get("date","")}</div>', unsafe_allow_html=True)
            _fii_card(f1, "FII Buy",  latest.get("fii_buy"))
            _fii_card(f2, "FII Sell", latest.get("fii_sell"))
            _fii_card(f3, "FII Net",  latest.get("fii_net"))
            _fii_card(d1, "DII Buy",  latest.get("dii_buy"))
            _fii_card(d2, "DII Sell", latest.get("dii_sell"))
            _fii_card(d3, "DII Net",  latest.get("dii_net"))

            st.markdown("---")

            # FII net trend chart
            df_chart = df_fii.dropna(subset=["fii_net", "dii_net"]).head(30).iloc[::-1]
            if not df_chart.empty:
                fig_fii = go.Figure()
                fig_fii.add_trace(go.Bar(
                    x=df_chart["date"], y=df_chart["fii_net"] / 100,
                    name="FII Net (Cr)",
                    marker_color=[GREEN if v >= 0 else RED for v in df_chart["fii_net"]],
                ))
                fig_fii.add_trace(go.Bar(
                    x=df_chart["date"], y=df_chart["dii_net"] / 100,
                    name="DII Net (Cr)",
                    marker_color=[BLUE if v >= 0 else ORANGE for v in df_chart["dii_net"]],
                ))
                fig_fii.update_layout(
                    title="FII & DII Net Activity — 30 Days",
                    barmode="group", template="plotly_dark",
                    paper_bgcolor=CARD, plot_bgcolor=CARD, height=340,
                    margin=dict(l=10, r=10, t=40, b=30),
                    xaxis=dict(gridcolor=BORDER),
                    yaxis=dict(gridcolor=BORDER, title="Net (₹ Cr)"),
                    legend=dict(orientation="h"),
                )
                st.plotly_chart(fig_fii, use_container_width=True)

                # Cumulative FII + DII trend
                df_chart["fii_cum"] = (df_chart["fii_net"] / 100).cumsum()
                df_chart["dii_cum"] = (df_chart["dii_net"] / 100).cumsum()
                fig_cum = go.Figure()
                fig_cum.add_trace(go.Scatter(
                    x=df_chart["date"], y=df_chart["fii_cum"],
                    name="FII Cumulative", line=dict(color=GREEN, width=2), mode="lines",
                ))
                fig_cum.add_trace(go.Scatter(
                    x=df_chart["date"], y=df_chart["dii_cum"],
                    name="DII Cumulative", line=dict(color=BLUE, width=2), mode="lines",
                ))
                fig_cum.update_layout(
                    title="FII & DII Cumulative Net — 30 Days",
                    template="plotly_dark", paper_bgcolor=CARD, plot_bgcolor=CARD, height=280,
                    margin=dict(l=10, r=10, t=40, b=20),
                    xaxis=dict(gridcolor=BORDER),
                    yaxis=dict(gridcolor=BORDER, title="Cumulative (₹ Cr)"),
                    legend=dict(orientation="h"),
                )
                st.plotly_chart(fig_cum, use_container_width=True)

            # Full table
            with st.expander("📋 Full FII/DII Data Table"):
                df_disp = df_fii.copy()
                for c in ["fii_buy","fii_sell","fii_net","dii_buy","dii_sell","dii_net"]:
                    df_disp[c] = df_disp[c].apply(lambda v: f"₹{float(v)/100:,.1f}" if pd.notna(v) else "—")
                df_disp.columns = ["Date","FII Buy","FII Sell","FII Net","DII Buy","DII Sell","DII Net"]
                st.dataframe(df_disp, use_container_width=True, hide_index=True)
        else:
            st.warning("FII/DII data unavailable — NSE API may be offline or rate-limiting.")
    else:
        st.info("Click **Load FII/DII Data** to fetch institutional activity.")

# ─────────────────────────────────────────────────────────────────────────────
# TAB 5 — Universe Explorer (quick view)
# ─────────────────────────────────────────────────────────────────────────────
with tab_universe:
    u_col1, u_col2, u_col3 = st.columns([3, 2, 1])
    with u_col1:
        u_label    = st.selectbox("Universe", labels, key="dash_uni_sel")
        u_universe = all_names[labels.index(u_label)]
    with u_col2:
        u_filter   = st.text_input("Filter symbol", placeholder="e.g. HDFC, INFY", key="dash_uni_filt")
    with u_col3:
        u_sort     = st.selectbox("Sort by", ["Change %", "Price", "Volume", "30D", "365D"], key="dash_uni_sort")

    u_btn, _ = st.columns([1, 4])
    with u_btn:
        load_uni = st.button("🔄 Load Universe", type="primary", key="dash_load_uni")

    if load_uni or st.session_state.get("dash_uni_data_key") == u_universe:
        if load_uni:
            with st.spinner(f"Loading {u_label}…"):
                uni_quotes = _index_quotes(u_universe)
            st.session_state["dash_uni_data"] = uni_quotes
            st.session_state["dash_uni_data_key"] = u_universe
        else:
            uni_quotes = st.session_state.get("dash_uni_data", [])

        if uni_quotes:
            sort_map = {
                "Change %": "change_pct", "Price": "price",
                "Volume": "volume", "30D": "return_30d", "365D": "return_365d",
            }
            sk2 = sort_map.get(u_sort, "change_pct")
            uni_quotes_s = sorted(uni_quotes, key=lambda x: float(x.get(sk2) or 0), reverse=True)

            if u_filter:
                uni_quotes_s = [q for q in uni_quotes_s if u_filter.upper() in q["symbol"]]

            st.markdown(f'<div class="z-section">{u_label} — {len(uni_quotes_s)} stocks</div>', unsafe_allow_html=True)

            df_uni = pd.DataFrame([{
                "Symbol":     q["symbol"],
                "Price":      f"₹{float(q.get('price') or 0):,.2f}",
                "Change %":   f"{float(q.get('change_pct') or 0):+.2f}%",
                "Open":       f"₹{float(q.get('open') or 0):,.2f}",
                "High":       f"₹{float(q.get('high') or 0):,.2f}",
                "Low":        f"₹{float(q.get('low') or 0):,.2f}",
                "52W High":   f"₹{float(q.get('year_high') or 0):,.2f}",
                "52W Low":    f"₹{float(q.get('year_low') or 0):,.2f}",
                "Vol (L)":    f"{float(q.get('volume') or 0)/1e5:.1f}",
                "30D Ret%":   f"{float(q.get('return_30d') or 0):+.2f}%",
                "365D Ret%":  f"{float(q.get('return_365d') or 0):+.2f}%",
                "_chg":       float(q.get("change_pct") or 0),
            } for q in uni_quotes_s])

            def _style_uni(df):
                styles = pd.DataFrame("", index=df.index, columns=df.columns)
                for i, val in enumerate(df["_chg"]):
                    try:
                        c = GREEN if float(val) >= 0 else RED
                        styles.iloc[i, df.columns.get_loc("Change %")] = f"color:{c};font-weight:700"
                        r30 = df.iloc[i]["30D Ret%"]
                        c30 = GREEN if "+" in str(r30) else RED
                        styles.iloc[i, df.columns.get_loc("30D Ret%")] = f"color:{c30}"
                        r365 = df.iloc[i]["365D Ret%"]
                        c365 = GREEN if "+" in str(r365) else RED
                        styles.iloc[i, df.columns.get_loc("365D Ret%")] = f"color:{c365}"
                    except Exception:
                        pass
                return styles

            st.dataframe(
                df_uni.drop(columns=["_chg"]).style.apply(_style_uni, axis=None),
                use_container_width=True, hide_index=True, height=500,
            )
            st.download_button(
                "📥 Export CSV", df_uni.drop(columns=["_chg"]).to_csv(index=False),
                f"{u_universe.replace(' ','_')}_snapshot.csv", "text/csv",
            )
        else:
            st.warning("No data — NSE API may not cover this index via equity-stockIndices.")
    else:
        st.info("Select a universe and click **Load Universe** to see all stocks with live data.")

# ── Auto-refresh logic ────────────────────────────────────────────────────────
if auto_refresh:
    refresh_interval = 60
    placeholder = st.empty()
    for i in range(refresh_interval, 0, -1):
        placeholder.markdown(
            f'<div style="color:{TEXT_DIM};font-size:0.78rem;text-align:right">'
            f'Auto-refresh in {i}s…</div>',
            unsafe_allow_html=True,
        )
        time.sleep(1)
    st.cache_data.clear()
    st.rerun()
