from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from concurrent.futures import ThreadPoolExecutor, as_completed

from utils.theme import apply_theme, GREEN, RED, BLUE, CARD, BORDER, TEXT, TEXT_DIM, YELLOW
apply_theme()

from services.position_sizing_service import (
    calculate_position, kelly_position, ai_allocate_capital,
)
from services.universe_sync import get_universe_symbols, get_all_universe_names, universe_display_map
from services.market_data_service import scan_market_bulk
from services.ai_service import analyze_stock

st.markdown("## 💰 Position Sizing & Capital Allocation")

tab_single, tab_kelly, tab_ai = st.tabs([
    "🎯 Single-Stock Sizing", "📈 Kelly Criterion", "🤖 AI Capital Allocator"
])

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 1 — Single-stock position sizing
# ═══════════════════════════════════════════════════════════════════════════════
with tab_single:
    st.markdown(
        f'<div style="color:{TEXT_DIM};font-size:0.85rem;margin-bottom:10px">'
        f'Calculate exact share quantity using % risk per trade and stop-loss distance.</div>',
        unsafe_allow_html=True,
    )

    s1, s2, s3 = st.columns(3)
    with s1:
        symbol_in = st.text_input("Symbol (optional)", value="RELIANCE", key="ps_sym")
        total_cap = st.number_input("Total Capital (₹)", min_value=1000.0,
                                     value=500000.0, step=10000.0, key="ps_cap")
    with s2:
        risk_pct = st.number_input("Risk per Trade (%)", min_value=0.1, max_value=10.0,
                                    value=1.0, step=0.1, key="ps_risk")
        max_pos_pct = st.number_input("Max Position (% of capital)", min_value=5.0,
                                       max_value=100.0, value=25.0, step=5.0, key="ps_max")
    with s3:
        entry = st.number_input("Entry Price (₹)", min_value=0.0, value=2500.0, step=1.0, key="ps_entry")
        stop = st.number_input("Stop Loss (₹)", min_value=0.0, value=2400.0, step=1.0, key="ps_stop")
        target = st.number_input("Target (₹, optional)", min_value=0.0, value=2700.0, step=1.0, key="ps_tgt")

    if st.button("🧮 Calculate Position Size", type="primary", key="ps_calc"):
        pos = calculate_position(
            total_capital=total_cap, risk_pct=risk_pct,
            entry=entry, stop_loss=stop,
            target=target if target > 0 else None,
            symbol=symbol_in, max_position_pct=max_pos_pct,
        )

        st.markdown("### Position Plan")
        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Quantity", f"{pos.qty:,}")
        m2.metric("Capital Deployed", f"₹{pos.capital_deployed:,.0f}",
                  f"{pos.capital_deployed/total_cap*100:.1f}% of capital")
        m3.metric("Capital at Risk", f"₹{pos.capital_at_risk:,.0f}",
                  f"{pos.risk_pct_of_total:.2f}% of capital")
        m4.metric("Risk per Share", f"₹{pos.risk_per_share:,.2f}")
        m5.metric("R:R Ratio", f"1 : {pos.rr_ratio:.2f}" if pos.rr_ratio else "—")

        st.markdown("---")
        # Visual entry / SL / target diagram
        fig = go.Figure()
        levels = [
            ("Stop Loss", pos.stop_loss, RED),
            ("Entry",     pos.entry,     BLUE),
        ]
        if pos.target:
            levels.append(("Target", pos.target, GREEN))
        for label, val, color in levels:
            fig.add_hline(y=val, line_color=color, line_width=2,
                          annotation_text=f"{label}: ₹{val:,.2f}",
                          annotation_position="right",
                          annotation_font=dict(color=color))
        fig.add_trace(go.Scatter(
            x=[0], y=[pos.entry], mode="markers",
            marker=dict(size=14, color=BLUE),
            name="Entry", showlegend=False,
        ))
        fig.update_layout(
            template="plotly_dark", paper_bgcolor=CARD, plot_bgcolor=CARD,
            height=300, showlegend=False,
            xaxis=dict(visible=False),
            yaxis=dict(title="Price (₹)", gridcolor=BORDER),
            margin=dict(l=10, r=120, t=10, b=10),
        )
        st.plotly_chart(fig, use_container_width=True)

        if pos.notes:
            for n in pos.notes:
                st.markdown(
                    f'<div style="background:rgba(245,197,66,0.08);border-left:3px solid {YELLOW};'
                    f'padding:8px 12px;margin:4px 0;font-size:0.85rem">{n}</div>',
                    unsafe_allow_html=True,
                )

        st.markdown("---")
        st.markdown("### Trade Order Summary")
        order_df = pd.DataFrame([{
            "Field": "Symbol",          "Value": pos.symbol or "—"},
            {"Field": "Action",          "Value": "BUY"},
            {"Field": "Quantity",        "Value": f"{pos.qty:,} shares"},
            {"Field": "Entry Price",     "Value": f"₹{pos.entry:,.2f}"},
            {"Field": "Stop Loss",       "Value": f"₹{pos.stop_loss:,.2f}"},
            {"Field": "Target",          "Value": f"₹{pos.target:,.2f}" if pos.target else "—"},
            {"Field": "Capital Used",    "Value": f"₹{pos.capital_deployed:,.0f}"},
            {"Field": "Max Loss if SL",  "Value": f"₹{pos.capital_at_risk:,.0f} ({pos.risk_pct_of_total:.2f}% of capital)"},
            {"Field": "Reward if Target","Value": f"₹{(pos.reward_per_share or 0)*pos.qty:,.0f}" if pos.reward_per_share else "—"},
        ])
        st.dataframe(order_df, use_container_width=True, hide_index=True)

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 2 — Kelly Criterion sizing
# ═══════════════════════════════════════════════════════════════════════════════
with tab_kelly:
    st.markdown(
        f'<div style="color:{TEXT_DIM};font-size:0.85rem;margin-bottom:10px">'
        f'For traders with a known historical edge — sizes positions optimally based on '
        f'win rate and average win/loss. <b>Half-Kelly</b> is recommended (less variance).</div>',
        unsafe_allow_html=True,
    )

    k1, k2, k3 = st.columns(3)
    with k1:
        k_cap     = st.number_input("Total Capital (₹)", min_value=1000.0,
                                     value=500000.0, step=10000.0, key="kelly_cap")
        k_winrate = st.slider("Historical Win Rate (%)", 30, 90, 55, key="kelly_wr") / 100.0
    with k2:
        k_avg_win  = st.number_input("Avg Win (%)",   min_value=0.5, value=8.0,  step=0.5, key="kelly_aw")
        k_avg_loss = st.number_input("Avg Loss (%)",  min_value=0.5, value=4.0,  step=0.5, key="kelly_al")
    with k3:
        k_frac = st.selectbox("Kelly Fraction",
                              [("Full Kelly (aggressive)", 1.0),
                               ("Half Kelly (recommended)", 0.5),
                               ("Quarter Kelly (conservative)", 0.25)],
                              index=1, format_func=lambda x: x[0], key="kelly_frac")[1]

    if st.button("🧮 Compute Kelly Size", type="primary", key="kelly_btn"):
        k_res = kelly_position(k_cap, k_winrate, k_avg_win, k_avg_loss, fractional=k_frac)
        kp1, kp2, kp3 = st.columns(3)
        kp1.metric("Full Kelly %", f"{k_res['kelly_full']:.2f}%")
        kp2.metric("Used Kelly %", f"{k_res['kelly_used_pct']:.2f}%")
        kp3.metric("Capital to Deploy", f"₹{k_res['capital_to_deploy']:,.0f}")
        st.markdown(
            f'<div style="background:rgba(33,150,243,0.08);border-left:3px solid {BLUE};'
            f'padding:10px 14px;margin-top:10px;font-size:0.88rem">{k_res["note"]}</div>',
            unsafe_allow_html=True,
        )
        if k_res["kelly_full"] <= 0:
            st.error("Negative edge — strategy expectancy is unfavorable. Do NOT trade.")

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 3 — AI Capital Allocator
# ═══════════════════════════════════════════════════════════════════════════════
with tab_ai:
    st.markdown(
        f'<div style="color:{TEXT_DIM};font-size:0.85rem;margin-bottom:10px">'
        f'Pick a universe, set your capital — the engine fetches live data, scores each stock '
        f'with the AI engine, then splits your capital across the top-ranked stocks with '
        f'per-position entry, SL, target, qty, and risk.</div>',
        unsafe_allow_html=True,
    )

    a1, a2, a3 = st.columns([2, 1, 1])
    with a1:
        disp_map  = universe_display_map()
        all_names = get_all_universe_names()
        labels    = [disp_map.get(n, n) for n in all_names]
        ai_label = st.selectbox("Universe to scan", labels, key="alloc_uni")
        ai_uni   = all_names[labels.index(ai_label)]
    with a2:
        ai_cap   = st.number_input("Total Capital (₹)", min_value=10000.0,
                                    value=500000.0, step=10000.0, key="alloc_cap")
        risk_pt  = st.number_input("Risk % per trade", min_value=0.25, max_value=5.0,
                                    value=1.0, step=0.25, key="alloc_risk")
    with a3:
        top_n      = st.number_input("Top N to allocate", min_value=2, max_value=20,
                                      value=5, step=1, key="alloc_topn")
        max_per    = st.number_input("Max % per position", min_value=5.0, max_value=50.0,
                                      value=25.0, step=5.0, key="alloc_max")

    a4, a5, a6 = st.columns(3)
    with a4:
        min_score = st.slider("Min AI Score", 40, 80, 55, key="alloc_minscore")
    with a5:
        weighting = st.selectbox("Weighting", ["score", "score_squared", "equal"],
                                  format_func=lambda x: {
                                      "score": "Linear (proportional to score)",
                                      "score_squared": "Concentrated (top scorers get more)",
                                      "equal": "Equal weight (1/N)",
                                  }[x], key="alloc_weight")
    with a6:
        scan_limit = st.number_input("Symbols to scan", min_value=10, max_value=500,
                                      value=50, step=10, key="alloc_scan")

    run_alloc = st.button("🚀 Build AI Portfolio", type="primary", key="alloc_run")

    if run_alloc:
        symbols = get_universe_symbols(ai_uni)[:scan_limit]
        st.info(f"Fetching market data + AI scoring for {len(symbols)} stocks…")

        # Step 1: bulk market data
        prog = st.progress(0.2, text=f"Fetching market data for {len(symbols)} stocks…")
        market_data = scan_market_bulk(symbols, max_workers=8)
        prog.progress(0.5, text=f"AI scoring {len(market_data)} stocks…")

        # Step 2: AI score each
        candidates = []
        for sym, md in market_data.items():
            try:
                v = analyze_stock(sym, tv=md, screener={}, patterns=[])
                ind = (md.get("indicators") or {})
                close = ind.get("close")
                atr   = ind.get("atr") or (close * 0.02 if close else 0)
                if close and atr:
                    candidates.append({
                        "symbol":    sym,
                        "name":      sym,
                        "score":     v.score,
                        "verdict":   v.verdict,
                        "entry":     close,
                        "stop_loss": v.stop_loss or (close - atr * 2),
                        "target":    v.price_target or (close + atr * 4),
                    })
            except Exception:
                continue

        prog.progress(0.85, text="Allocating capital…")

        # Take top N
        candidates.sort(key=lambda c: c["score"], reverse=True)
        top_candidates = candidates[:top_n]

        result = ai_allocate_capital(
            total_capital=ai_cap,
            candidates=top_candidates,
            risk_pct_per_trade=risk_pt,
            max_position_pct=max_per,
            min_score_threshold=min_score,
            weighting=weighting,
        )
        prog.empty()

        st.success(result["summary"])

        if not result["allocations"]:
            st.info("No stocks met the criteria. Try lowering the min AI score or scanning more symbols.")
        else:
            # Summary metrics
            sm1, sm2, sm3, sm4 = st.columns(4)
            sm1.metric("Stocks Allocated", len(result["allocations"]))
            sm2.metric("Capital Deployed", f"₹{result['total_deployed']:,.0f}",
                       f"{result['total_deployed']/ai_cap*100:.1f}%")
            sm3.metric("Total at Risk", f"₹{result['total_at_risk']:,.0f}",
                       f"{result['total_at_risk']/ai_cap*100:.2f}% of capital")
            sm4.metric("Cash Buffer", f"₹{result['capital_left']:,.0f}")

            st.markdown("---")

            # Allocation table
            rows = []
            for a in result["allocations"]:
                rr = a.get("rr_ratio")
                rows.append({
                    "Symbol":   a["symbol"],
                    "Score":    f"{a.get('score',0):.0f}",
                    "Verdict":  a.get("verdict", ""),
                    "Weight %": f"{a.get('weight_pct', 0):.1f}%",
                    "Qty":      f"{a['qty']:,}",
                    "Entry":    f"₹{a['entry']:,.2f}",
                    "Stop":     f"₹{a['stop_loss']:,.2f}",
                    "Target":   f"₹{a['target']:,.2f}" if a.get("target") else "—",
                    "R:R":      f"1:{rr:.2f}" if rr else "—",
                    "Deployed": f"₹{a['capital_deployed']:,.0f}",
                    "At Risk":  f"₹{a['capital_at_risk']:,.0f}",
                })
            df_alloc = pd.DataFrame(rows)

            def _style_alloc(df):
                styles = pd.DataFrame("", index=df.index, columns=df.columns)
                for i in range(len(df)):
                    v = str(df.iloc[i]["Verdict"])
                    if "BUY" in v:
                        styles.iloc[i, df.columns.get_loc("Verdict")] = f"color:{GREEN};font-weight:700"
                    elif "SELL" in v:
                        styles.iloc[i, df.columns.get_loc("Verdict")] = f"color:{RED};font-weight:700"
                return styles

            st.dataframe(
                df_alloc.style.apply(_style_alloc, axis=None),
                use_container_width=True, hide_index=True, height=420,
            )

            # Pie chart of capital distribution
            ch1, ch2 = st.columns(2)
            with ch1:
                fig_pie = go.Figure(go.Pie(
                    labels=[a["symbol"] for a in result["allocations"]] + ["Cash"],
                    values=[a["capital_deployed"] for a in result["allocations"]] + [result["capital_left"]],
                    hole=0.5,
                    marker=dict(colors=["#4caf50", "#2196f3", "#ff9800", "#9c27b0",
                                        "#00bcd4", "#ff5722", "#cddc39", "#795548",
                                        "#607d8b", "#e91e63", TEXT_DIM]),
                    textinfo="label+percent",
                ))
                fig_pie.update_layout(
                    title="Capital Distribution",
                    template="plotly_dark", paper_bgcolor=CARD, plot_bgcolor=CARD,
                    height=380, margin=dict(l=10, r=10, t=40, b=10),
                )
                st.plotly_chart(fig_pie, use_container_width=True)

            with ch2:
                fig_risk = go.Figure(go.Bar(
                    x=[a["symbol"] for a in result["allocations"]],
                    y=[a["capital_at_risk"] for a in result["allocations"]],
                    marker_color=RED,
                    text=[f"₹{a['capital_at_risk']:,.0f}" for a in result["allocations"]],
                    textposition="outside",
                ))
                fig_risk.update_layout(
                    title="Risk per Position (₹)",
                    template="plotly_dark", paper_bgcolor=CARD, plot_bgcolor=CARD,
                    height=380, margin=dict(l=10, r=10, t=40, b=10),
                    xaxis=dict(gridcolor=BORDER), yaxis=dict(gridcolor=BORDER),
                )
                st.plotly_chart(fig_risk, use_container_width=True)

            st.markdown("---")
            st.download_button(
                "📥 Export Allocation CSV",
                df_alloc.to_csv(index=False),
                f"allocation_{ai_uni.replace(' ','_')}_{int(ai_cap)}.csv",
                "text/csv",
            )
