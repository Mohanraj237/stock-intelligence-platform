"""
Learn — chart pattern library + technical / fundamental fundamentals reference.

Goal: a beginner-to-intermediate trader can open this page and learn what
each chart pattern looks like, what the major indicators mean, basic risk
management, and how to actually use the rest of the app.
"""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st
import plotly.graph_objects as go

from utils.theme import apply_theme, GREEN, RED, BLUE, CARD, BORDER, TEXT, TEXT_DIM, YELLOW, ORANGE
apply_theme()

from services.pattern_examples import PATTERN_LIBRARY, get_pattern_by_name

st.markdown("## 🎓 Learn")
st.markdown(
    f'<div style="color:{TEXT_DIM};font-size:0.88rem;margin-bottom:14px">'
    f'A self-study reference: chart patterns with visual examples, technical indicators, '
    f'fundamentals primer, risk management, and how to use this app effectively.'
    f'</div>',
    unsafe_allow_html=True,
)

tab_pat, tab_tech, tab_fund, tab_risk, tab_app = st.tabs([
    "📐 Chart Patterns",
    "📊 Technical Indicators",
    "💰 Fundamentals",
    "🛡️ Risk Management",
    "🧭 Using This App",
])

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 1 — Chart Pattern Library
# ═══════════════════════════════════════════════════════════════════════════════
with tab_pat:
    st.markdown(
        f'<div style="color:{TEXT};font-weight:600;font-size:1rem;margin-bottom:6px">'
        f'📐 Chart Pattern Library — {len(PATTERN_LIBRARY)} patterns</div>'
        f'<div style="color:{TEXT_DIM};font-size:0.85rem;margin-bottom:14px">'
        f'Every pattern includes a synthetic example chart, when to enter/exit, '
        f'target/stop logic, and confidence factors. Click any pattern below.'
        f'</div>',
        unsafe_allow_html=True,
    )

    # Filter controls
    fc1, fc2, fc3 = st.columns([2, 2, 1])
    with fc1:
        cats = sorted({p["category"] for p in PATTERN_LIBRARY})
        sel_cats = st.multiselect("Filter by category", cats, default=[], key="learn_cat")
    with fc2:
        directions = ["Bullish", "Bearish", "Either"]
        sel_dirs = st.multiselect("Filter by direction", directions, default=[], key="learn_dir")
    with fc3:
        sel_view = st.radio("View", ["Gallery", "Single"], horizontal=True, key="learn_view")

    filtered = [p for p in PATTERN_LIBRARY
                if (not sel_cats or p["category"] in sel_cats)
                and (not sel_dirs or p["direction"] in sel_dirs)]

    st.caption(f"Showing **{len(filtered)}** patterns")
    st.markdown("---")

    def _render_pattern_chart(pattern: dict, height: int = 240, key_suffix: str = ""):
        df = pattern["generator"]()
        fig = go.Figure(go.Candlestick(
            x=df.index, open=df["Open"], high=df["High"],
            low=df["Low"], close=df["Close"],
            increasing_line_color=GREEN, decreasing_line_color=RED,
            showlegend=False, name=pattern["name"],
        ))
        fig.update_layout(
            template="plotly_dark", paper_bgcolor=CARD, plot_bgcolor=CARD,
            xaxis_rangeslider_visible=False, height=height,
            margin=dict(l=0, r=0, t=4, b=0),
            xaxis=dict(gridcolor=BORDER, showticklabels=False),
            yaxis=dict(gridcolor=BORDER, side="right"),
        )
        st.plotly_chart(fig, use_container_width=True,
                        key=f"learn_chart_{pattern['name']}_{key_suffix}",
                        config={"displayModeBar": False})

    def _direction_badge(d: str) -> str:
        c = GREEN if d == "Bullish" else RED if d == "Bearish" else YELLOW
        return f'<span style="background:{c};color:#fff;padding:2px 8px;border-radius:10px;font-size:0.7rem;font-weight:700">{d.upper()}</span>'

    def _render_pattern_full(pattern: dict, key_suffix: str = ""):
        col_chart, col_meta = st.columns([3, 2])
        with col_chart:
            _render_pattern_chart(pattern, height=300, key_suffix=key_suffix)
        with col_meta:
            st.markdown(
                f'<div style="font-size:1.1rem;font-weight:700;color:{TEXT};margin-bottom:4px">'
                f'{pattern["name"]} {_direction_badge(pattern["direction"])}</div>'
                f'<div style="color:{TEXT_DIM};font-size:0.78rem;margin-bottom:8px">'
                f'<b>Category:</b> {pattern["category"]} &nbsp;·&nbsp; '
                f'<b>Best timeframes:</b> {pattern["best_timeframes"]}</div>',
                unsafe_allow_html=True,
            )
            st.markdown(
                f'<div style="color:{TEXT};font-size:0.85rem;margin-bottom:10px">'
                f'{pattern["description"]}</div>',
                unsafe_allow_html=True,
            )

        st.markdown(
            f'<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;margin-top:8px">'
            f'<div style="background:rgba(38,166,154,0.08);border-left:3px solid {GREEN};padding:10px 12px;border-radius:0 6px 6px 0">'
            f'<b style="color:{GREEN};font-size:0.82rem">▶ ENTRY</b><br>'
            f'<span style="color:{TEXT};font-size:0.83rem">{pattern["when_to_trade"]}</span></div>'
            f'<div style="background:rgba(33,150,243,0.08);border-left:3px solid {BLUE};padding:10px 12px;border-radius:0 6px 6px 0">'
            f'<b style="color:{BLUE};font-size:0.82rem">🎯 TARGET</b><br>'
            f'<span style="color:{TEXT};font-size:0.83rem">{pattern["target_rule"]}</span></div>'
            f'<div style="background:rgba(239,83,80,0.08);border-left:3px solid {RED};padding:10px 12px;border-radius:0 6px 6px 0">'
            f'<b style="color:{RED};font-size:0.82rem">🛑 STOP LOSS</b><br>'
            f'<span style="color:{TEXT};font-size:0.83rem">{pattern["stop"]}</span></div>'
            f'</div>',
            unsafe_allow_html=True,
        )

        st.markdown(
            f'<div style="margin-top:10px"><b style="color:{YELLOW};font-size:0.85rem">📋 Confidence Factors</b></div>',
            unsafe_allow_html=True,
        )
        for f in pattern["confidence_factors"]:
            st.markdown(
                f'<div style="color:{TEXT_DIM};font-size:0.83rem;padding:2px 0">• {f}</div>',
                unsafe_allow_html=True,
            )

    if sel_view == "Single":
        names = [p["name"] for p in filtered]
        if names:
            chosen = st.selectbox("Pick a pattern", names, key="learn_pick")
            pat = get_pattern_by_name(chosen)
            if pat:
                _render_pattern_full(pat, key_suffix="single")
        else:
            st.info("No patterns match the current filters.")
    else:
        # Gallery view — 2 patterns per row, expandable
        for i in range(0, len(filtered), 2):
            cols = st.columns(2)
            for j, col in enumerate(cols):
                if i + j >= len(filtered):
                    break
                pat = filtered[i + j]
                with col:
                    st.markdown(
                        f'<div style="font-weight:700;color:{TEXT};font-size:1rem">'
                        f'{pat["name"]} {_direction_badge(pat["direction"])}</div>'
                        f'<div style="color:{TEXT_DIM};font-size:0.74rem;margin-bottom:4px">'
                        f'{pat["category"]}</div>',
                        unsafe_allow_html=True,
                    )
                    _render_pattern_chart(pat, height=200, key_suffix=f"gal_{i}_{j}")
                    with st.expander(f"📖 Learn this pattern", expanded=False):
                        st.markdown(pat["description"])
                        st.markdown(f"**Entry:** {pat['when_to_trade']}")
                        st.markdown(f"**Target:** {pat['target_rule']}")
                        st.markdown(f"**Stop:** {pat['stop']}")
                        st.markdown("**Confidence factors:**")
                        for cf in pat["confidence_factors"]:
                            st.markdown(f"- {cf}")
                        st.markdown(f"**Best timeframes:** {pat['best_timeframes']}")

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 2 — Technical Indicators
# ═══════════════════════════════════════════════════════════════════════════════
with tab_tech:
    st.markdown(
        f'<div style="color:{TEXT};font-weight:600;font-size:1rem;margin-bottom:14px">'
        f'📊 Technical Indicators — what they mean and when to use them</div>',
        unsafe_allow_html=True,
    )

    INDICATORS = [
        {
            "name": "RSI (Relative Strength Index)",
            "what": "Momentum oscillator — measures speed of price changes. 0-100 scale.",
            "key_levels": "**>70 = overbought** (potential pullback) · **<30 = oversold** (potential bounce) · **50 = neutral**",
            "how_to_use": (
                "1. **Trend confirmation:** RSI staying above 50 = uptrend. Below 50 = downtrend.\n"
                "2. **Reversal signals:** Oversold (<30) + bullish candlestick = high-probability bounce.\n"
                "3. **Divergence:** Price makes new high but RSI doesn't = weakening momentum (bearish divergence)."
            ),
            "pitfall": "In strong trends, RSI can stay overbought/oversold for weeks — don't fight the trend.",
        },
        {
            "name": "MACD (Moving Average Convergence Divergence)",
            "what": "Trend-following momentum indicator showing relationship between two EMAs (12 and 26).",
            "key_levels": "**MACD line crosses above Signal line** = bullish · **MACD crosses below** = bearish · **Histogram** shows momentum strength",
            "how_to_use": (
                "1. **Bullish crossover:** MACD crosses above Signal — momentum turning up.\n"
                "2. **Zero-line cross:** MACD crossing 0 = trend change confirmation.\n"
                "3. **Divergence:** Price up, MACD down = bearish divergence (momentum weakening)."
            ),
            "pitfall": "Lagging indicator — it confirms trends after they start, not before.",
        },
        {
            "name": "ADX (Average Directional Index)",
            "what": "Measures **trend strength** (not direction). 0-100 scale, but typically 0-50.",
            "key_levels": "**ADX < 20:** weak trend / sideways · **20-25:** developing trend · **>25:** strong trend · **>40:** very strong",
            "how_to_use": (
                "1. **Filter trades:** Only take trend-following setups when ADX > 25.\n"
                "2. **Range-bound markets:** ADX < 20 = avoid breakout trades, look for mean-reversion.\n"
                "3. **+DI vs -DI:** +DI > -DI confirms uptrend; -DI > +DI confirms downtrend."
            ),
            "pitfall": "ADX tells you a trend is strong but never which direction.",
        },
        {
            "name": "EMA / SMA (Moving Averages)",
            "what": "Smoothed price line. EMA weights recent prices more (faster); SMA equal weight (slower).",
            "key_levels": "**Price > 200 SMA** = long-term bullish · **Price < 200 SMA** = long-term bearish · **EMA stack** (20>50>200) = strongest uptrend",
            "how_to_use": (
                "1. **Trend identification:** Use 50 EMA as medium-term trend, 200 SMA as long-term.\n"
                "2. **Dynamic support/resistance:** Price often pulls back to 20 or 50 EMA in trends.\n"
                "3. **Golden Cross:** 50 SMA crosses above 200 SMA = major bullish shift."
            ),
            "pitfall": "Choppy markets cause whipsaws — moving averages don't work in sideways ranges.",
        },
        {
            "name": "Bollinger Bands",
            "what": "Three lines: middle SMA(20), upper = +2σ, lower = -2σ. Measures volatility-adjusted price.",
            "key_levels": "**Touch upper band** = stretched up · **Touch lower band** = stretched down · **Bands squeeze** = volatility about to expand",
            "how_to_use": (
                "1. **Mean reversion:** Touching outer bands often reverses to the middle.\n"
                "2. **Squeeze breakouts:** Tight bands precede big moves — trade breakout direction.\n"
                "3. **Trend continuation:** In strong trends, price 'walks' the upper or lower band."
            ),
            "pitfall": "Don't short just because price touched upper band — strong trends keep walking it.",
        },
        {
            "name": "Stochastic Oscillator",
            "what": "Momentum oscillator comparing close to recent range. 0-100 scale.",
            "key_levels": "**>80 = overbought** · **<20 = oversold** · **%K crossing %D** = signal",
            "how_to_use": "Same as RSI — useful for spotting overbought/oversold + bullish/bearish crosses.",
            "pitfall": "Very noisy — often combined with RSI for confirmation.",
        },
        {
            "name": "Volume",
            "what": "Number of shares traded. The 'fuel' behind every price move.",
            "key_levels": "**Breakout + 1.5× avg volume** = real · **Breakout on low volume** = likely fake",
            "how_to_use": (
                "1. **Confirms breakouts:** Always check volume on a breakout — no volume = no participation.\n"
                "2. **Accumulation:** Sideways price + rising volume = institutional buying.\n"
                "3. **Distribution:** Sideways + selling on volume = institutions exiting."
            ),
            "pitfall": "Volume is the most overlooked indicator — but the most important for confirmation.",
        },
    ]

    for ind in INDICATORS:
        with st.expander(f"**{ind['name']}**", expanded=False):
            st.markdown(f"**What it is:** {ind['what']}")
            st.markdown(f"**Key levels:** {ind['key_levels']}")
            st.markdown("**How to use:**")
            st.markdown(ind["how_to_use"])
            st.markdown(
                f'<div style="background:rgba(245,197,66,0.08);border-left:3px solid {YELLOW};'
                f'padding:8px 12px;margin-top:8px;border-radius:0 6px 6px 0;font-size:0.85rem">'
                f'<b style="color:{YELLOW}">⚠ Pitfall:</b> {ind["pitfall"]}</div>',
                unsafe_allow_html=True,
            )

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 3 — Fundamentals primer
# ═══════════════════════════════════════════════════════════════════════════════
with tab_fund:
    st.markdown(
        f'<div style="color:{TEXT};font-weight:600;font-size:1rem;margin-bottom:14px">'
        f'💰 Fundamentals — what makes a company quality vs junk</div>',
        unsafe_allow_html=True,
    )

    FUND = [
        ("**P/E (Price-to-Earnings)**",
         "How much you pay per ₹1 of earnings. **Lower = cheaper.**",
         "Compare to **sector median** — IT trades at 25–35x, FMCG at 50–80x, banks at 10–15x.",
         "**< 15:** typically value · **15-25:** fair · **25-40:** growth premium · **> 40:** expensive"),
        ("**P/B (Price-to-Book)**",
         "Price vs net assets per share. Useful for asset-heavy businesses (banks, real estate).",
         "**< 1:** trading below book value (deep value) · **1-3:** normal · **> 5:** asset-light or richly valued.",
         "Pair with ROE — high ROE justifies high P/B."),
        ("**ROE (Return on Equity)**",
         "Profit generated per ₹1 of shareholder equity. **The single most important quality metric.**",
         "**> 20%:** excellent · **15-20%:** good · **10-15%:** average · **< 10%:** weak.",
         "Sustained ROE > 20% over 5+ years = compounder."),
        ("**ROCE (Return on Capital Employed)**",
         "Profit per ₹1 of total capital (equity + debt). Measures capital efficiency including borrowed money.",
         "**> 25%:** excellent · **15-25%:** good · **< 12%:** weak.",
         "ROCE > ROE = company is using debt efficiently."),
        ("**D/E (Debt-to-Equity)**",
         "Total borrowings / total equity. Measures leverage risk.",
         "**< 0.5:** conservative · **0.5-1.0:** moderate · **> 2.0:** risky.",
         "Banks/NBFCs naturally have high D/E — context matters."),
        ("**OPM (Operating Profit Margin)**",
         "Operating profit / sales × 100. Pricing power proxy.",
         "**> 20%:** strong moat · **10-20%:** average · **< 5%:** commodity-like.",
         "Rising OPM over years = improving business."),
        ("**Sales Growth & Profit Growth**",
         "Year-over-year revenue and profit growth.",
         "**> 20%:** high-growth · **10-20%:** healthy · **< 5%:** mature/slow.",
         "Profit growth > sales growth = operating leverage kicking in (bullish)."),
        ("**Promoter Holding**",
         "% of shares held by founders. **High = aligned interests.**",
         "**> 50%:** strong promoter conviction · **< 25%:** caution.",
         "Pledge > 15% = warning sign."),
        ("**Dividend Yield**",
         "Annual dividend / price × 100.",
         "**> 4%:** income stock · **1-3%:** balanced · **0%:** growth-stage.",
         "Sustainable yield needs consistent profit + low payout ratio."),
    ]
    for name, what, ranges, extra in FUND:
        st.markdown(
            f'<div style="background:{CARD};border-left:3px solid {BLUE};padding:10px 14px;margin:6px 0;border-radius:0 6px 6px 0">'
            f'<div style="color:{TEXT};font-size:0.95rem;margin-bottom:4px">{name}</div>'
            f'<div style="color:{TEXT_DIM};font-size:0.83rem">{what}</div>'
            f'<div style="color:{TEXT};font-size:0.83rem;margin-top:4px"><b>Ranges:</b> {ranges}</div>'
            f'<div style="color:{TEXT_DIM};font-size:0.8rem;margin-top:2px"><i>{extra}</i></div>'
            f'</div>',
            unsafe_allow_html=True,
        )

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 4 — Risk management
# ═══════════════════════════════════════════════════════════════════════════════
with tab_risk:
    st.markdown(
        f'<div style="color:{TEXT};font-weight:600;font-size:1rem;margin-bottom:14px">'
        f'🛡️ Risk Management — survive long enough to win</div>',
        unsafe_allow_html=True,
    )

    st.markdown(
        f'<div style="background:rgba(33,150,243,0.08);border:1px solid {BLUE};border-radius:8px;'
        f'padding:14px 18px;margin-bottom:14px;color:{TEXT};font-size:0.95rem">'
        f'<b style="color:{BLUE};font-size:1.05rem">The single most important rule:</b><br>'
        f'<b>Never risk more than 1–2% of your capital on any single trade.</b><br>'
        f'<span style="color:{TEXT_DIM};font-size:0.85rem">'
        f'A 50%-win-rate strategy with 2% risk per trade can lose 10 in a row and still survive (~80% capital left). '
        f'A 5% risk strategy goes broke after the same losing streak.</span></div>',
        unsafe_allow_html=True,
    )

    RISK = [
        ("**Position Sizing Formula**",
         "Shares to buy = (Capital × Risk%) ÷ (Entry – Stop Loss)\n\n"
         "**Example:** ₹5,00,000 capital, 1% risk, entry ₹2,500, stop ₹2,400 → "
         "Risk per share = ₹100 → Shares = ₹5,000 ÷ ₹100 = **50 shares**"),
        ("**Risk : Reward Ratio**",
         "Always know your R:R before entering.\n\n"
         "**Minimum acceptable:** 1:1.5 · **Good:** 1:2 · **Excellent:** 1:3+\n\n"
         "Even with 40% win rate, a 1:2 R:R strategy makes money."),
        ("**Stop Loss Discipline**",
         "**Set the stop BEFORE entering.** Use the chart's structure (below support, "
         "below recent swing low, below pattern boundary) — never an arbitrary % number.\n\n"
         "**Once set, never widen it.** If you can't stomach the loss, your position is too big."),
        ("**Diversification**",
         "Don't put more than **20-25% in any single stock** even with a perfect setup.\n\n"
         "Don't put more than **40% in any single sector**. Sector-wide selloffs happen."),
        ("**Trailing Stops**",
         "Once a trade moves in your favor, trail your stop up (long) to lock in profit.\n\n"
         "Common methods: 50 EMA (medium-term swings), prior swing low, or chandelier exit (3× ATR below recent high)."),
        ("**Max Daily / Weekly Drawdown**",
         "Set hard rules: stop trading after losing **3% in a day** or **5% in a week**.\n\n"
         "Drawdowns compound — when you're losing, the brain wants revenge trades. Step away."),
    ]
    for name, body in RISK:
        with st.expander(name, expanded=False):
            st.markdown(body)

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 5 — Using this app
# ═══════════════════════════════════════════════════════════════════════════════
with tab_app:
    st.markdown(
        f'<div style="color:{TEXT};font-weight:600;font-size:1rem;margin-bottom:14px">'
        f'🧭 How to actually use this app — recommended workflow</div>',
        unsafe_allow_html=True,
    )

    workflow = [
        ("📊 **Dashboard**",
         "Start here every day. See market state (open/closed), index levels, advance/decline, "
         "sector heatmap, FII/DII flows. Sets your bias for the day."),
        ("🌐 **Universe Explorer**",
         "Browse all stocks in any NSE index with live prices, RSI, MACD, EMAs, returns. "
         "Sort/filter to spot what's moving."),
        ("📡 **Scanner**",
         "Pre-built scans (Breakout, Oversold Bounce, Quality Growth, Techno-Funda, etc). "
         "Pick a scan type → run on any universe → AI scores each match."),
        ("🧬 **Pattern Lab**",
         "Multi-timeframe pattern detection. Stocks with patterns confirming on multiple "
         "timeframes (1d + 1w + 1mo) = strongest signals."),
        ("🔍 **Stock Analyzer**",
         "Deep-dive any stock — chart, AI verdict, indicators, fundamentals, quarterly results, "
         "balance sheet, shareholding, peers + AI Chart Analysis (rule-based 14-section report)."),
        ("💰 **Position Sizing**",
         "Once you've picked stocks: compute exact qty (single-stock or AI-allocate across "
         "your shortlist with capital splitting + risk budgeting)."),
        ("📅 **Earnings Calendar**",
         "See upcoming results announcements + recent earnings sentiment per stock. "
         "Avoid trades into binary earnings events."),
        ("📰 **News**",
         "Aggregated headlines from Moneycontrol, ET, Business Standard, LiveMint + NSE "
         "corporate announcements. Filter by sentiment."),
        ("📊 **Backtest**",
         "Validate any pattern strategy across history before risking capital. "
         "Reports win rate, expectancy, max drawdown, equity curve."),
        ("⭐ **Watchlist** + **Portfolio**",
         "Track stocks you're watching and your live holdings."),
        ("⚙️ **Rule Engine** + **Compare** + **Reports**",
         "Build custom screeners, compare 4 stocks side-by-side, generate PDF reports."),
    ]

    for title, body in workflow:
        st.markdown(
            f'<div style="background:{CARD};border:1px solid {BORDER};border-radius:8px;'
            f'padding:10px 14px;margin:6px 0">'
            f'<div style="color:{TEXT};font-size:0.95rem">{title}</div>'
            f'<div style="color:{TEXT_DIM};font-size:0.85rem;margin-top:3px">{body}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    st.markdown(
        f'<div style="background:rgba(38,166,154,0.08);border-left:3px solid {GREEN};'
        f'padding:12px 16px;margin-top:16px;border-radius:0 8px 8px 0">'
        f'<b style="color:{GREEN}">Recommended swing-trader workflow (5 min/day):</b><br>'
        f'<span style="color:{TEXT};font-size:0.88rem">'
        f'1. Dashboard → market bias  →  '
        f'2. Scanner → run "Breakout Ready" or "Quality Growth" → AI scoring on  →  '
        f'3. Pattern Lab → confirm multi-timeframe alignment for top scanner picks  →  '
        f'4. Stock Analyzer → deep-dive 1-2 finalists → run AI Chart Analysis  →  '
        f'5. Position Sizing → compute exact qty with 1% risk  →  '
        f'6. Place trade with stop pre-set.</span></div>',
        unsafe_allow_html=True,
    )
