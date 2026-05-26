from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from utils.theme import apply_theme, GREEN, RED, BLUE, CARD, BORDER, TEXT, TEXT_DIM, YELLOW
apply_theme()

from services.backtest_service import (
    run_pattern_backtest, PATTERN_CATEGORIES, ALL_PATTERN_NAMES,
)
from services.universe_sync import (
    get_universe_symbols, get_all_universe_names, universe_display_map,
)

st.markdown("## 📊 Strategy Backtest")
st.markdown(
    f'<div style="color:{TEXT_DIM};font-size:0.85rem;margin-bottom:12px">'
    f'Pick a chart pattern. The engine scans historical OHLCV across the chosen universe, '
    f'finds every occurrence of that pattern, simulates each trade, and reports '
    f'win rate · avg return · expectancy · profit factor · max drawdown · equity curve.'
    f'</div>',
    unsafe_allow_html=True,
)

# ── Inputs ────────────────────────────────────────────────────────────────────
c1, c2 = st.columns([2, 2])
with c1:
    # Two-level pattern picker: category → pattern
    cat = st.selectbox("Pattern Category", list(PATTERN_CATEGORIES.keys()), key="bt_cat")
    pats = PATTERN_CATEGORIES[cat]
    pattern_name = st.selectbox("Pattern", pats, key="bt_pat")

with c2:
    disp_map  = universe_display_map()
    all_names = get_all_universe_names()
    labels    = [disp_map.get(n, n) for n in all_names]
    bt_label  = st.selectbox("Universe", labels, key="bt_uni")
    bt_uni    = all_names[labels.index(bt_label)]

c3, c4, c5, c6, c7 = st.columns(5)
with c3:
    bt_period = st.selectbox("Lookback period", ["1y", "2y", "5y", "max"], index=2, key="bt_period")
with c4:
    bt_max_syms = st.number_input("Max symbols to scan", min_value=5, max_value=500,
                                   value=50, step=5, key="bt_syms")
with c5:
    bt_min_conf = st.slider("Min confidence %", 40, 90, 60, step=5, key="bt_conf")
with c6:
    bt_holding = st.number_input("Max holding (bars)", min_value=5, max_value=200,
                                  value=60, step=5, key="bt_hold")
with c7:
    bt_step = st.number_input("Step (bars)", min_value=1, max_value=30, value=10,
                               step=1, key="bt_step",
                               help="Bars between detection calls. Smaller = more overlapping detections but slower.")

st.markdown("---")

run_bt = st.button(f"🔬 Run Backtest — {pattern_name}", type="primary", key="bt_run",
                    use_container_width=True)

# ── Execution ─────────────────────────────────────────────────────────────────
if run_bt:
    symbols = get_universe_symbols(bt_uni)[: int(bt_max_syms)]
    prog = st.progress(0.0, text=f"Starting backtest of {pattern_name} across {len(symbols)} stocks…")

    def _cb(done, total, cur_sym):
        prog.progress(done / max(total, 1), text=f"Processing {cur_sym} ({done}/{total})")

    result = run_pattern_backtest(
        symbols=symbols,
        pattern_name=pattern_name,
        period=bt_period,
        window=120,
        step=int(bt_step),
        min_confidence=int(bt_min_conf),
        max_holding=int(bt_holding),
        max_workers=6,
        progress_cb=_cb,
    )
    prog.empty()
    st.session_state["bt_result"] = result

result = st.session_state.get("bt_result")
if not result:
    st.info("Configure inputs above and click **Run Backtest**.")
    st.stop()

# ── Summary metrics ───────────────────────────────────────────────────────────
if result.total_trades == 0:
    st.warning(f"No occurrences of **{result.pattern}** found in {result.universe_size} symbols "
               f"with confidence ≥ {bt_min_conf}%. Try lowering the confidence threshold or "
               f"picking a different pattern.")
    with st.expander("🔎 Audit Log"):
        for line in result.audit:
            st.text(line)
    st.stop()

st.success(f"✅ Backtest complete — **{result.total_trades} trades** across "
           f"{result.symbols_with_patterns} symbols.")

# Headline stats
m1, m2, m3, m4, m5, m6 = st.columns(6)
m1.metric("Total Trades", result.total_trades)
m2.metric("Win Rate", f"{result.win_rate:.1f}%",
          f"{result.winners}W / {result.losers}L / {result.neutrals}N")
m3.metric("Avg Return", f"{result.avg_return_pct:+.2f}%")
m4.metric("Expectancy", f"{result.expectancy:+.2f}%",
          help="(WinRate × AvgWin) + (LossRate × AvgLoss)")
m5.metric("Profit Factor", f"{result.profit_factor:.2f}",
          help=">1.5 = good, >2 = excellent")
m6.metric("Max Drawdown", f"{result.max_drawdown_pct:.1f}%", delta_color="inverse")

mc1, mc2, mc3, mc4 = st.columns(4)
mc1.metric("Avg Winner", f"{result.avg_winner_pct:+.2f}%")
mc2.metric("Avg Loser", f"{result.avg_loser_pct:+.2f}%")
mc3.metric("Best Trade", f"{result.max_winner_pct:+.2f}%")
mc4.metric("Worst Trade", f"{result.max_loser_pct:+.2f}%")

# Verdict banner
if result.expectancy > 1.5 and result.win_rate > 55 and result.profit_factor > 1.5:
    verdict_msg, verdict_color = "🟢 **Tradeable edge detected** — positive expectancy, healthy win rate, good profit factor.", GREEN
elif result.expectancy > 0 and result.win_rate > 45:
    verdict_msg, verdict_color = "🟡 **Marginal edge** — positive but thin. Needs tighter filters or risk control.", YELLOW
else:
    verdict_msg, verdict_color = "🔴 **No edge** — pattern doesn't produce profitable trades under current rules.", RED

st.markdown(
    f'<div style="background:{CARD};border:1px solid {verdict_color};border-radius:8px;'
    f'padding:12px 16px;margin:12px 0;font-size:0.95rem;color:{TEXT}">{verdict_msg}</div>',
    unsafe_allow_html=True,
)

st.markdown("---")

# ── Charts ────────────────────────────────────────────────────────────────────
ch1, ch2 = st.columns(2)

# Equity curve
with ch1:
    fig_eq = go.Figure(go.Scatter(
        x=list(range(len(result.equity_curve))),
        y=result.equity_curve,
        mode="lines",
        line=dict(color=GREEN if result.equity_curve[-1] >= 100 else RED, width=2),
        fill="tozeroy", fillcolor="rgba(38,166,154,0.08)",
    ))
    fig_eq.add_hline(y=100, line_color=TEXT_DIM, line_dash="dash")
    fig_eq.update_layout(
        title=f"Equity Curve — starting at 100 (sequential 1% trades)",
        template="plotly_dark", paper_bgcolor=CARD, plot_bgcolor=CARD,
        height=340, margin=dict(l=10, r=10, t=40, b=20),
        xaxis=dict(title="Trade #", gridcolor=BORDER),
        yaxis=dict(title="Equity", gridcolor=BORDER),
    )
    st.plotly_chart(fig_eq, use_container_width=True)

# Return distribution
with ch2:
    returns = [t["return_pct"] for t in result.trades]
    fig_h = go.Figure(go.Histogram(
        x=returns, nbinsx=24,
        marker_color=[GREEN if v >= 0 else RED for v in returns],
    ))
    fig_h.add_vline(x=0, line_color=TEXT_DIM, line_dash="dash")
    fig_h.add_vline(x=result.avg_return_pct, line_color=BLUE, line_dash="dot",
                     annotation_text=f"Avg {result.avg_return_pct:+.1f}%",
                     annotation_font_color=BLUE)
    fig_h.update_layout(
        title="Trade Return Distribution",
        template="plotly_dark", paper_bgcolor=CARD, plot_bgcolor=CARD,
        height=340, margin=dict(l=10, r=10, t=40, b=20),
        xaxis=dict(title="Return %", gridcolor=BORDER),
        yaxis=dict(title="Count", gridcolor=BORDER),
    )
    st.plotly_chart(fig_h, use_container_width=True)

# Top performers & worst trades
st.markdown('<div class="z-section">Top 10 Winners</div>', unsafe_allow_html=True)
df_top = pd.DataFrame(sorted(result.trades, key=lambda t: t["return_pct"], reverse=True)[:10])
if not df_top.empty:
    st.dataframe(df_top[["symbol","entry_date","exit_date","holding_days",
                          "entry_price","exit_price","return_pct","exit_reason","confidence"]],
                  use_container_width=True, hide_index=True)

st.markdown('<div class="z-section">Top 10 Losers</div>', unsafe_allow_html=True)
df_bot = pd.DataFrame(sorted(result.trades, key=lambda t: t["return_pct"])[:10])
if not df_bot.empty:
    st.dataframe(df_bot[["symbol","entry_date","exit_date","holding_days",
                          "entry_price","exit_price","return_pct","exit_reason","confidence"]],
                  use_container_width=True, hide_index=True)

st.markdown("---")

# ── Full trade log ────────────────────────────────────────────────────────────
st.markdown('<div class="z-section">Full Trade Log</div>', unsafe_allow_html=True)
df_all = pd.DataFrame(result.trades)

def _style_outcome(df):
    styles = pd.DataFrame("", index=df.index, columns=df.columns)
    for i in range(len(df)):
        o = df.iloc[i]["outcome"]
        c = GREEN if o == "WIN" else RED if o == "LOSS" else YELLOW
        styles.iloc[i, df.columns.get_loc("outcome")] = f"color:{c};font-weight:700"
        r = df.iloc[i]["return_pct"]
        try:
            rc = GREEN if float(r) >= 0 else RED
            styles.iloc[i, df.columns.get_loc("return_pct")] = f"color:{rc};font-weight:600"
        except Exception:
            pass
    return styles

st.dataframe(df_all.style.apply(_style_outcome, axis=None),
              use_container_width=True, hide_index=True, height=420)

st.download_button(
    "📥 Export Trades CSV",
    df_all.to_csv(index=False),
    f"backtest_{pattern_name.replace(' ','_')}_{bt_uni.replace(' ','_')}.csv",
    "text/csv",
)

# Audit log
with st.expander("🔎 Backtest Audit Log"):
    for line in result.audit[:200]:
        st.text(line)
    if len(result.audit) > 200:
        st.text(f"... {len(result.audit)-200} more lines ...")
