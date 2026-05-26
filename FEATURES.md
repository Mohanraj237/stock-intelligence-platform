# Stock Intelligence Platform — Features

A local-first Indian stock-market research, scanning, and analysis terminal for swing & positional traders. **No API keys required.** All data comes from free public sources (Yahoo Finance, NSE India, Screener.in, Moneycontrol/ET RSS).

---

## Quick start

```bash
pip install -r requirements.txt
streamlit run app/main.py
```

The app opens in your browser at `http://localhost:8501`. All data is cached locally under `storage/` — no database, no external service.

---

## Table of contents

- [App pages (16)](#app-pages-16)
  - [Market](#market) — Dashboard · Universe Explorer · News · Earnings Calendar
  - [Analysis](#analysis) — Stock Analyzer · Scanner · Pattern Lab · Compare · Backtest
  - [Tools](#tools) — Position Sizing · Rule Engine · Portfolio · Watchlist · Reports · Settings
  - [Help](#help) — Learn
- [Services](#services-16)
- [Engines](#engines)
- [Storage & cache](#storage--cache)
- [Charting stack](#charting-stack)
- [Data sources](#data-sources)
- [Tech stack](#tech-stack)
- [Recommended workflows](#recommended-workflows)
- [What's intentionally NOT included](#whats-intentionally-not-included)

---

## App pages (16)

### Market

#### 📊 Dashboard — `app/pages/1_Dashboard.py`

Market-wide situational awareness.

| Section | Details |
|---|---|
| **Market status banner** | Open / closed indicator, trade date, total market cap (₹ L Cr), GIFT Nifty futures with % change |
| **Index performance cards** | NIFTY 50, BANK, IT, PHARMA, MIDCAP 150, SMALLCAP 250 — each shows level, ₹ change, % change with up/down arrow. Auto-computes pct from change/last when NSE returns 0/None |
| **Overview tab** | Advance/decline counts, A/D ratio, breadth bar (stacked horiz), change % distribution histogram, top 5 stocks near 52W high, top 5 near 52W low |
| **Top Movers tab** | Per-universe top gainers / losers / volume leaders. Sortable by Change %, Volume, 30D, 365D. Bar chart of top 5 each side |
| **Sectors tab** | All 11 NSE sector indices as a treemap heatmap (color = % change), summary table with adv/dec per sector, bar chart |
| **FII/DII tab** | Latest day buy/sell/net for FII and DII (₹ Cr), 30-day net activity grouped bar chart, cumulative net trend |
| **Universe tab** | Full stock table for any index — Price, Change %, OHLC, 52W H/L, Volume, 30D Ret %, 1Y Ret %. CSV export |
| **Auto-refresh toggle** | 60-second refresh with countdown |

#### 🌐 Universe Explorer — `app/pages/2_Universe_Explorer.py`

Browse and filter all stocks in any of the 16+ NSE indices with live technicals.

- Sortable by Change %, RSI, ADX, Volume, 30D return, 1Y return, Symbol
- Filters: Market Signal (STRONG_BUY/BUY/NEUTRAL/SELL/STRONG_SELL), RSI range, Price > SMA50/SMA200, MACD bullish, Change % range
- Per-symbol audit log: shows pass/fail reason for every stock
- NSE fallback when Yahoo bulk-scan fails — automatically degrades to live quotes only
- Signal Distribution + RSI Distribution histograms
- RSI vs Change% scatter plot (color-coded)
- CSV export

#### 📰 News — `app/pages/14_News.py`

Aggregated news from 9 free RSS sources + NSE corporate announcements.

| Tab | Features |
|---|---|
| **Market News** | Headlines from Moneycontrol Markets/Business/Top, Economic Times Markets/Stocks/Economy, Business Standard Markets, LiveMint Markets/Money. Per-headline sentiment classifier (POSITIVE / MILDLY POSITIVE / NEUTRAL / MILDLY NEGATIVE / NEGATIVE). Filter by sentiment. Pie chart of overall market sentiment + bar chart by source |
| **Stock-Specific** | Filter aggregated headlines for any symbol — finds whole-word matches in title or summary |
| **NSE Announcements** | Corporate disclosures from NSE for any symbol or market-wide. Sentiment-classified by subject text |

#### 📅 Earnings Calendar — `app/pages/13_Earnings_Calendar.py`

Upcoming results from NSE board meetings + historical earnings sentiment.

| Tab | Features |
|---|---|
| **Upcoming Results** | Pull NSE board-meeting API for next 7/14/30/60 days. Shows date, symbol, company, agenda. Filtered to result-related meetings only. Grouped-by-date expanders |
| **Recent Earnings (Universe)** | For any universe, fetch last quarter from Screener.in, classify each as POSITIVE / MILDLY POSITIVE / NEUTRAL / MILDLY NEGATIVE / NEGATIVE based on YoY sales+profit growth. Pie chart of sentiment distribution + Profit YoY histogram |
| **Stock-Level History** | Last 8 quarters per stock with sales, net profit, OPM%, YoY growths, sentiment per quarter. Sales+Profit grouped bar chart. Sentiment timeline scatter |

---

### Analysis

#### 🔍 Stock Analyzer — `app/pages/3_Stock_Analyzer.py`

Single-stock deep dive across **11 tabs**, parallel-fetches data from 4 sources simultaneously with per-source timeouts.

| Tab | Content |
|---|---|
| **📈 Chart** | TradingView-style candlestick chart (lightweight-charts) with EMA20/50/200, Entry/Target/Stop horizontal lines, best-pattern trendlines, volume pane |
| **🤖 AI Analysis** | Verdict (STRONG_BUY/BUY/HOLD/SELL/STRONG_SELL), 0-100 composite score, Bull case / Bear case narratives, Risk flags, Score breakdown bar chart (Tech/Fund/Pattern/Momentum), all signals chain |
| **🧬 Patterns** | Detected chart patterns drawn on a candlestick chart with trendlines, target/stop horizontal lines, per-pattern expanders |
| **📊 Technicals** | 28+ indicators: Close, OHLC, RSI, AO, EMAs (20/50/100/200), SMAs (20/50/100/200), Bollinger Bands, MACD line/signal/hist, ADX +DI/-DI, Stochastic K/D, CCI 20 |
| **💰 Fundamentals** | Market cap, PE, PB, Book Value, Dividend Yield, EPS, ROE, ROCE, OPM, NPM, Sales/Profit Growth, D/E, Interest Coverage, Promoter Holding. About text. Pros/Cons |
| **📋 Quarterly** | Last 8 quarters: Sales+, Net Profit+, OPM% as grouped bar chart + full data table |
| **🏦 Balance Sheet** | Latest BS line items + Cash Flow line items |
| **📉 Ratio Trends** | 10-year historical ratios — multi-select + line chart |
| **👥 Shareholding** | Latest promoter/FII/DII/public/pledge breakdown + history line chart |
| **🔗 Peers** | Peer comparison table from Screener.in |
| **🎯 AI Chart Analysis** | Rule-based 14-section institutional report — Trend, Price Structure, Patterns, Moving Averages, S/R, Volume, Momentum, Risk Management with exact ₹ Entry/SL/Targets, Probability Scores (Breakout/Trend/RR/Overall × /10), Red Flags, Smart Money perspective, Final Verdict, Confidence, Pro Trader explanation. Switchable timeframe (Daily/Weekly/Monthly), data preview before sending. **No API key required — fully local** |

**Resilience:** Screener-down banner with "Retry" button; chart and technicals always work even when Screener fails. OHLCV-computed indicators kick in when Yahoo bulk-scanner is blocked.

#### 📡 Scanner — `app/pages/4_Scanner.py`

Run any of **12 pre-built scan types** across any universe with audit trail.

| Scan type | What it finds |
|---|---|
| All Stocks | Show everything |
| Breakout Ready | Price > SMA50, RSI 55-72, MACD bullish |
| Oversold Bounce | RSI < 35 — mean-reversion candidates |
| Strong Momentum | Price > SMA50 & SMA200, ADX > 20, RSI 50-75 |
| MACD Crossover | MACD just crossed signal up |
| Quality Growth | ROE > 15%, sales growth > 15%, low debt |
| Undervalued | PE < 20, PB < 3, ROE > 10% |
| Techno-Funda | PE < 30, ROE > 15%, RSI 45-70, Price > SMA50 |
| High Promoter Holding | Promoter > 55%, profit growth > 10% |
| Dividend Compounders | ROE > 12%, D/E < 1, promoter > 40% |
| 52W High Breakout | Price > SMA200, RSI 60-80 |
| Reversal Watch | RSI 25-40, MACD turning bullish |

- Customizable filters (PE, PB, D/E, ROE, ROCE, Sales Growth, Profit Growth, Promoter %, RSI min/max, ADX min, Price > SMA50/200, MACD bullish)
- Optional **AI scoring** — fetches Screener fundamentals in parallel and runs the AI verdict on every match (same engine as Stock Analyzer for consistency)
- Per-symbol audit log (60 entries) showing which filter rules each stock passed/failed
- Signal distribution + RSI distribution charts
- CSV export

#### 🧬 Pattern Lab — `app/pages/5_Pattern_Lab.py`

Multi-timeframe pattern detection with breakout-state classification.

**Bulk Pattern Scan tab:**
- Select universe + **multi-select chart patterns** from the Learn library (22 patterns)
- **Multi-select breakout state filter** — Verge of breakout / Fresh breakout (1 candle) / Confirmed breakout / Extended / Verge of breakdown / Fresh breakdown / Confirmed breakdown
- Direction filter (All / Bullish / Bearish)
- Min confidence slider
- Engine scans every stock at **1h · 1d · 1w · 1mo simultaneously**
- Results table with **Confluence score** (rewards multi-timeframe agreement + breakout state)
- Per-stock expanders with **inline timeframe switcher** (radio button) — chart re-renders with that timeframe's pattern overlays
- TradingView-style chart with EMAs, pattern trendlines, S/R levels, Entry/Target/Stop horizontal lines
- Per-pattern cards under each chart showing: pattern name, confidence, breakout state, distance %, volume confirmation, target, stop, entry rule (pulled from Learn library)

**Single-Stock Studio tab:**
- Multi-timeframe state cards (1h / 1d / 1w / 1mo) — each shows breakout label, level, distance %, volume confirmation
- Overall verdict combining all timeframes (e.g. "🟢 Ideal swing-buy setup — 1d confirmed + 1w fresh")
- AI verdict integration
- Studio chart with inline timeframe switcher
- Per-timeframe pattern grids
- AI signal chain (color-coded bull/bear/neutral)

#### ⚖️ Compare — `app/pages/11_Compare.py`

Side-by-side analysis of up to 4 stocks.

- Common metrics table (PE, PB, ROE, ROCE, OPM, D/E, Sales Growth, Profit Growth)
- Multi-stock price overlay chart
- Radar chart comparison

#### 📊 Backtest — `app/pages/15_Backtest.py`

Strategy-first historical pattern backtesting across the universe.

- Pick any of 39 chart patterns from 7 categories
- Select any universe
- Configure: lookback period (1y/2y/5y/max), max symbols, min confidence %, max holding bars, step size
- Engine walks forward through history per stock, finds every occurrence of the pattern, simulates trade with target hit / stop hit / time stop / end-of-data exit logic
- Outputs:
  - Win rate, avg return, expectancy, profit factor, max drawdown
  - Avg/best/worst winner & loser
  - Avg holding days
  - **Equity curve** (sequential 1% bet sizing)
  - **Return distribution histogram**
  - Top 10 winners + Top 10 losers tables
  - Full trade log with WIN/LOSS color coding
  - Verdict banner: 🟢 Tradeable edge / 🟡 Marginal / 🔴 No edge
- CSV export
- Audit log of every symbol scanned

---

### Tools

#### 💰 Position Sizing — `app/pages/12_Position_Sizing.py`

Three modes for capital deployment.

**Tab 1 — Single-Stock Sizing**
- Input: total capital, % risk per trade, entry, stop, target, max position cap %
- Output: exact share quantity, capital deployed, capital at risk, R:R ratio, full trade-order summary table, visual price diagram
- Warnings: poor R:R, >2% risk, capped at max position %, stop=entry edge case

**Tab 2 — Kelly Criterion**
- Input: capital, historical win rate, avg win %, avg loss %, Kelly fraction (Full / Half / Quarter)
- Output: Full Kelly %, Used Kelly %, exact ₹ to deploy
- Detects negative edge → "do NOT trade"

**Tab 3 — AI Capital Allocator**
- Input: universe, total capital, risk % per trade, top N stocks, max % per position, min AI score, weighting (linear / score-squared / equal), scan limit
- Engine: bulk Yahoo fetch → AI score every stock → pick top N → allocate capital weighted by score, capped at max %, with per-position entry, stop (ATR-based fallback), target (AI), qty
- Output: allocation table, capital distribution pie chart, risk-per-position bar chart, deployed/at-risk/cash buffer summary, CSV export

#### ⚙️ Rule Engine — `app/pages/6_Rule_Engine.py`

Build custom screeners with visual rules.

- Up to 10 conditions per rule, each: field × operator (>, >=, <, <=, ==, between) × value(s)
- AND / OR logic per rule
- Cross-rule AND / OR when applying multiple
- Save / load / export / delete rules (stored in `storage/config/rules.json`)
- Pre-built preset rules
- Apply to any universe, see matched stocks with rules-passed count

#### 💼 Portfolio — `app/pages/7_Portfolio.py`

Track holdings and live P&L.

- Add holding (symbol, qty, buy price, buy date)
- KPI row: Total Invested · Current Value · Total P&L · Holdings count
- Per-holding table with CMP, Today %, Invested, Current Val, P&L, P&L %, Signal, Buy Date
- Remove holdings
- CSV export

#### ⭐ Watchlist — `app/pages/8_Watchlist.py`

- Add stocks via index → multiselect dropdown
- Refresh live data: Price, Change %, RSI, MACD, SMA 50/200, Volume, Signal, Score
- Mini charts for top 4
- Per-stock remove buttons
- CSV export

#### 📄 Reports — `app/pages/9_Reports.py`

Generate full-fidelity **PDF research reports**.

Each PDF (~150 KB) contains:
- Cover page: stock name, company, sector, generated date, **verdict box** (BUY/HOLD/SELL + score + target + SL + confidence)
- AI score breakdown horizontal bar chart (Tech / Fund / Pattern / Momentum)
- **Daily candlestick chart** rendered with matplotlib — EMAs, pattern trendlines, Entry/Target/Stop horizontal lines, volume pane
- **Multi-timeframe breakout table** (1h / 1d / 1w / 1mo with state, level, distance %, volume confirmed)
- 12 technical indicators in two-column layout
- Detected patterns table (name, direction, confidence, status, target, stop)
- **Full AI Chart Analysis narrative** (all 14 sections rendered as paragraphs)
- Fundamentals snapshot
- Last 6 quarters of results (Sales / Net Profit / OPM)
- Strengths / Weaknesses / AI risk flags
- Disclaimer footer
- Dark theme matching the app

Library tab: list saved reports with download buttons.

#### 🛠️ Settings — `app/pages/10_Settings.py`

| Tab | Settings |
|---|---|
| **General** | Refresh interval, default universe, max parallel workers |
| **Data Sources** | Screener.in CSRF + session cookies (optional, for richer fundamentals); cache TTLs (Screener / Market data / Universe) |
| **Universe Sync** | Status table for all 16+ indices, sync-all button, clear universe cache |
| **Storage** | Per-directory file count + size; clear all caches / clear Screener cache buttons |
| **About** | App version + data sources |

Test buttons: Yahoo bulk fetch, Screener.in fetch, NSE India fetch — all show real sample output.

---

### Help

#### 🎓 Learn — `app/pages/16_Learn.py`

Self-study reference for new traders.

| Tab | Content |
|---|---|
| **📐 Chart Patterns** | **22-pattern library** with procedurally-generated synthetic candlestick examples for each. Each pattern has: visual chart, description, entry rule, target rule, stop rule, confidence factors, best timeframes. **Gallery view** (2-up grid) or **Single deep-dive view**. Filter by category and direction |
| **📊 Technical Indicators** | RSI, MACD, ADX, EMA/SMA, Bollinger Bands, Stochastic, Volume — what each is, key levels, how to use, common pitfalls |
| **💰 Fundamentals** | PE, PB, ROE, ROCE, D/E, OPM, growth rates, promoter holding, dividend yield — with healthy ranges per sector |
| **🛡️ Risk Management** | Position-sizing formula, R:R ratio guidance, stop-loss discipline, diversification rules, trailing stops, max daily/weekly drawdown limits |
| **🧭 Using This App** | Page-by-page workflow guide + recommended 5-min daily swing-trader workflow |

The 22 Learn patterns are the same names used by Pattern Lab's multi-select filter — they are pulled from `services/pattern_examples.py` on both pages.

---

## Services (16)

### `services/market_data_service.py`
**Replaces TradingView entirely.** Free Yahoo Finance OHLCV + locally-computed indicators using the `ta` library.

- `get_ohlcv_history(symbol, period, interval)` — supports `1h / 1d / 1W / 1M`
- `get_market_analysis(symbol)` — fetch + compute 28 indicators + derive recommendation
- `scan_market_bulk(symbols)` — parallel multi-symbol fetch
- `score_signal(rec)` — STRONG_BUY=100 / BUY=80 / NEUTRAL=50 / SELL=25 / STRONG_SELL=5
- Indicators: RSI, MACD (line/signal/hist), ADX (+DI/-DI), ATR, Bollinger Bands, Stochastic K/D, CCI 20, SMA/EMA at 20/50/100/200
- Recommendation derived from 6+ signal aggregation (RSI, MACD, EMA stack, SMA50/200, ADX direction)

### `services/nse_service.py`
Live NSE India data with thread-safe session.

- `get_market_status()` — open/closed, NIFTY level, market cap, GIFT Nifty
- `get_index_performance()` — top 6 indices with pct auto-computed if NSE returns null
- `get_index_quotes(universe)` — all stocks in any index with price, OHLC, 52W H/L, returns
- `get_sector_performance()` — 11 sector indices with adv/dec counts
- `get_fii_dii_data()` — parses NSE's category-rows-per-date format, groups into one row per date
- `get_quote(symbol)` — single-stock detailed quote
- `get_bulk_quotes(symbols)` — parallel
- Session cookie auto-refresh every 5 min, threading.Lock for safety

### `services/screener_service.py`
Screener.in fundamentals scraper with **circuit breaker**.

- `get_full_screener_data(symbol)` — name, sector, industry, ratios, P&L (annual + quarterly), balance sheet, cash flow, historical ratios, shareholding, peers, pros/cons, insights
- 12 derived ratios (PE, PB, ROE, ROCE, OPM, NPM, D/E, interest coverage, sales/profit growth, promoter holding, etc.)
- **Circuit breaker:** opens after 3 consecutive failures for 5 min — every subsequent call returns instantly with `error` field. Manual `reset_circuit_breaker()` available. Per-request timeout (5s connect, 8s read). `is_screener_healthy()` for UI banner. Result: app never hangs when Screener is down — chart/technicals always work.
- Optional auth via cookies (richer data when authenticated)

### `services/ai_service.py`
**Rule-based composite scoring** (no API key, no LLM). Returns `AIVerdict` dataclass.

- `analyze_stock(symbol, tv, screener, patterns)` returns:
  - **Verdict**: STRONG_BUY / BUY / HOLD / SELL / STRONG_SELL
  - **Composite score** (0-100) weighted: Technical 35% + Fundamental 35% + Pattern 15% + Momentum 15%
  - **Tech score** from RSI / MACD / EMA stack / SMA crossovers / ADX / Stochastic / Bollinger / change %
  - **Fund score** from PE / PB / ROE / ROCE / OPM / D/E / promoter / sales growth / profit growth / interest coverage
  - **Pattern score** from confluence of detected bullish vs bearish patterns (case-normalized — fixes the historical "no bullish stocks" bug)
  - **Momentum score** from intraday move + EMA alignment + AO + pledge
  - **Confidence** (Low / Medium / High) gated on data availability
  - **Price target** + **stop loss** (ATR-based, score-scaled)
  - **Risk flags** (PE>60, D/E>2, low promoter, RSI extremes, etc.)
  - **Bull case** + **Bear case** narratives
  - Top 10 signal explanations

### `services/chart_analysis_service.py`
**Rule-based 14-section institutional analyzer.** No API key required.

- `analyze_chart_data(symbol, timeframe, ohlcv_df, indicators, patterns, fundamentals, ...)`
- Sections: Trend Analysis, Price Structure, Chart Patterns, Moving Averages, Support & Resistance, Volume Analysis, Momentum, Risk Management (with exact ₹ entries/SL/targets), Probability Scores (out of 10), Red Flags, Smart Money Perspective, Fundamentals Snapshot, Final Verdict, Confidence, Pro Trader Explanation
- `resample_ohlcv(df, "Daily/Weekly/Monthly")`
- `compute_indicators_from_ohlcv(df)` — produces the same 26-indicator dict regardless of source

### `services/breakout_service.py`
Per-candle breakout state classifier.

- `classify_breakout(df, level_override=, direction="auto")` returns:
  - **State**: `VERGE_BREAKOUT` (within 2%) / `FRESH_BREAKOUT` (1 candle ago) / `CONFIRMED_BREAKOUT` (2-5 candles ago) / `EXTENDED` (>5 candles) / `NO_BREAKOUT` and bearish equivalents
  - **Level** auto-detected as 60-bar high (or override with pattern's resistance)
  - **Distance %** from level
  - **Bars since breakout**
  - **Volume confirmed** (recent vol > 1.4× 20-bar avg)
- `classify_multi_timeframe(symbol, fetch_fn)` — runs 1h/1d/1w/1mo, returns per-tf classification + an "overall" verdict per the user's rules (1d expects confirmed, 1w expects single-candle-fresh)

### `services/position_sizing_service.py`
- `calculate_position(total_capital, risk_pct, entry, stop, target?, max_position_pct=25)` → `PositionSize` dataclass with qty, deployed, at-risk, R:R, notes
- `kelly_position(capital, win_rate, avg_win_pct, avg_loss_pct, fractional=0.5)` → Half-Kelly default
- `ai_allocate_capital(total, candidates, risk_pct, max_position_pct, min_score_threshold, weighting)` — weights `score | score_squared | equal`

### `services/earnings_service.py`
- `get_upcoming_results(days_ahead=14)` — NSE board-meetings API, filtered to result-related agendas
- `get_recent_earnings(symbol, n_quarters=4)` — Screener-backed quarterly P&L with YoY growth + sentiment classifier
- `get_earnings_calendar(symbols, fetch_recent=True)` — combined view
- `classify_earnings(sales_growth_pct, profit_growth_pct)` — POSITIVE / MILDLY POSITIVE / NEUTRAL / MILDLY NEGATIVE / NEGATIVE

### `services/news_service.py`
- 9 free RSS feeds (Moneycontrol × 3, Economic Times × 3, Business Standard, LiveMint × 2)
- `get_market_news(limit, sources)` — parallel fetch via `feedparser`, de-duped by title, sorted newest-first
- `get_stock_news(symbol, limit)` — whole-word title/summary match
- `get_nse_announcements(symbol?)` — NSE corporate disclosures
- `classify_sentiment(text)` — keyword-based (60+ positive/negative tokens) → POSITIVE / MILDLY POSITIVE / NEUTRAL / MILDLY NEGATIVE / NEGATIVE

### `services/backtest_service.py`
- `run_pattern_backtest(symbols, pattern_name, period, window, step, min_confidence, max_holding)` → `BacktestResult`
- Walks forward through history, runs `detect_patterns` on rolling window, simulates each entry with target/stop/time-stop logic
- Returns: win rate, avg return, avg/max winner+loser, expectancy, profit factor, max drawdown, equity curve, full trade log
- Pattern engine direction case-bug fixed (was treating all bearish as bullish)

### `services/universe_sync.py`
Sync NSE-published index constituents to local JSON.

- 16+ universes: NIFTY 50/100/200/500, MIDCAP 50/100/150/SELECT, SMALLCAP 50/100/250, BANK, IT, PHARMA, AUTO, FMCG, METAL, ENERGY, PSU BANK, REALTY, MEDIA, INFRA, CONSUMPTION, MNC
- `startup_sync(parallel=True)` runs in background thread on app start
- Fallback symbol lists when NSE is unreachable

### `services/pattern_examples.py`
22-pattern Learn library with procedural OHLCV generators.

Each pattern has: name, category, direction, generator (returns ~100-bar synthetic DataFrame visualizing the pattern), description, entry rule, target rule, stop, confidence factors, best timeframes.

Patterns: Bull/Bear Flag, Ascending/Descending/Symmetrical Triangle, Double Top/Bottom, Head & Shoulders + Inverse, Cup & Handle, Rounding Bottom, Rising/Falling Wedge, Rectangle Breakout, Channel Breakout, Hammer, Shooting Star, Bullish/Bearish Engulfing, Morning/Evening Star, 52W High Breakout.

### `services/pdf_report_service.py`
Multi-page institutional PDF generator.

- Matplotlib renders dark-themed candlestick + volume + EMA chart with overlays
- ReportLab assembles: cover, verdict box, score bar, chart, multi-tf table, indicators, patterns, AI narrative, fundamentals, quarterly, pros/cons/risk-flags, disclaimer
- Dark page background matching app theme
- Verified: 149 KB PDF for RELIANCE in regression tests

### `services/tradingview_service.py`
**Backwards-compatibility shim only.** Re-exports `market_data_service` functions under old names (`scan_symbols_bulk`, `get_tv_analysis`, `tv_score`, etc.). All TV widget HTML functions return empty strings. No `tradingview-ta` dependency.

---

## Engines

### `engines/pattern_engine.py`
**39 chart patterns** across 7 categories.

Categories: Trend Continuation, Reversal, Candlestick, Breakout/Momentum, Mean Reversion, Support & Resistance, Volume.

Returns `list[dict]` with: name, category, direction (Bullish/Bearish/Neutral), confidence (0-100), status, description, key_levels (target/stop/support/resistance), points, lines (for chart overlay), zones.

### `engines/filter_engine.py`
- `FilterCriteria` dataclass (PE, PB, D/E, ROE, ROCE, growth, RSI, ADX, MACD bullish, price > SMAs, etc.)
- `apply_filters(rows, criteria)` — applies in-memory filtering
- `FILTER_PRESETS` — 8 pre-built scan profiles

### `engines/rule_engine.py`
- `Rule` (logic AND/OR) of N `RuleCondition` (field, op, value, value2)
- 6 operators: `>`, `>=`, `<`, `<=`, `==`, `between`
- `evaluate_rules(rules, stock, logic)` — returns list of pass/fail per rule
- `apply_rules_to_universe(rules, stocks, logic)` — bulk apply
- `PRESET_RULES` — sample rule library

### `engines/scoring_engine.py`
Builds a `stock_snapshot` dict combining technical + fundamental + market signals into a Final Score (used by Reports + Rule Engine).

---

## Storage & cache

### `storage/file_store.py`
Local JSON storage. All app state lives under `storage/`.

| Path | Contents |
|---|---|
| `storage/cache/` | Per-prefix cache files (TTL-controlled) |
| `storage/data/` | Reserved for app data |
| `storage/reports/` | Generated PDF + JSON reports |
| `storage/config/` | Settings, watchlist, portfolio, rules, saved scans, reports index |
| `storage/sessions/` | Per-session metadata |
| `storage/logs/` | JSONL append-only logs |
| `storage/universe/` | Cached index constituents |

Plus: legacy-key sanitizer in `get_settings()` strips removed fields (`anthropic_api_key`, `tv_session`) automatically.

### `storage/cache_manager.py`
- TTL-based JSON cache: `get_cached(prefix, key)`, `set_cached(prefix, key, data)`, `invalidate(prefix, key)`, `invalidate_prefix(prefix)`
- TTL defaults: universe 24h, screener 6h, tv_analysis 15m, quote 5m, peers 12h, P&L/BS/CF/shareholding 24h
- Refuses to cache `None` / empty dict / empty list
- `@cached(prefix, ttl)` decorator for symbol-keyed functions

---

## Charting stack

### Primary: TradingView Lightweight Charts (free, MIT)
[`utils/tv_chart.py`](utils/tv_chart.py) — `render_tv_chart()` — TradingView's own open-source charting engine via `streamlit-lightweight-charts`. Used by Stock Analyzer Chart tab + Pattern Lab studio chart.

Features: native candlesticks, volume pane, EMA overlays, Entry/Target/Stop price lines with labels, pattern trendlines, magnet crosshair, smooth zoom, dark theme.

### Secondary: Plotly
Used for: Dashboard treemap/histograms/breadth bars, Universe Explorer scatters/histograms, Scanner signal/RSI distributions, Backtest equity curve + return histogram, Compare radar charts, Position Sizing pie/bar charts, News sentiment pie/bar.

### Server-side (PDF): Matplotlib
Renders dark-themed candlestick + volume charts as PNG bytes for embedding in `pdf_report_service`.

---

## Data sources

**100% free, no API keys required:**

| Source | What we get |
|---|---|
| **Yahoo Finance** | OHLCV history at 1h / 1d / 1W / 1M intervals (used by everything technical) |
| **NSE India** | Live quotes, index constituents, market status, FII/DII flows, sector indices, board meetings, corporate announcements |
| **Screener.in** | Company fundamentals, P&L (annual + quarterly), balance sheet, cash flow, shareholding history, peers, pros/cons. Optional cookies for richer data. Has circuit breaker so failures never block the app |
| **Moneycontrol RSS** | Markets / Business / Top news headlines |
| **Economic Times RSS** | Markets / Stocks / Economy headlines |
| **Business Standard RSS** | Markets headlines |
| **LiveMint RSS** | Markets / Money headlines |

---

## Tech stack

| Library | Purpose |
|---|---|
| `streamlit==1.44.1` | UI framework |
| `pandas==2.2.3` + `numpy==2.2.4` | Data |
| `plotly==6.0.1` | General charts |
| `streamlit-lightweight-charts>=0.7.21` | TradingView-style price charts |
| `matplotlib>=3.7` | PDF chart rendering |
| `ta==0.11.0` | Technical indicators (RSI, MACD, ADX, BB, Stochastic, CCI, ATR) |
| `beautifulsoup4==4.13.3` + `lxml==5.2.1` | HTML scraping (Screener.in) |
| `requests==2.32.3` + `httpx==0.27.0` | HTTP |
| `feedparser==6.0.11` | RSS news feeds |
| `reportlab==4.3.1` | PDF generation |
| `pydantic==2.11.3` + `pydantic-settings==2.8.1` | Config |
| `chardet==5.2.0` | Encoding detection |
| `python-dotenv==1.1.0` + `aiofiles==23.2.1` | Misc |

**Removed:** `anthropic`, `tradingview-ta`, `kaleido` — none required anymore.

---

## Recommended workflows

### Daily 5-min swing-trader scan

1. **Dashboard** — eyeball market bias (open/close, advance/decline, sectors, FII/DII)
2. **Scanner** — run **Breakout Ready** or **Quality Growth** on NIFTY 100; toggle AI Scoring
3. **Pattern Lab** — confirm multi-timeframe alignment for the top scanner picks (looking for 1d confirmed + 1w fresh)
4. **Stock Analyzer** — deep-dive 1-2 finalists, run **AI Chart Analysis**
5. **Position Sizing** — compute exact qty with 1% risk
6. Place trade with stop pre-set

### Weekly portfolio review

1. **Portfolio** → live P&L
2. **News** stock-specific tab for each holding
3. **Earnings Calendar** — check upcoming results in your holdings
4. **Reports** → generate PDF for any holding showing concerns

### Strategy validation

1. **Backtest** → pick the pattern your strategy depends on
2. Run on NIFTY 500 over 5y
3. Reject if expectancy ≤ 0 or profit factor < 1.5
4. **Pattern Lab** → live-scan for the same pattern across the universe

### Learning

1. **Learn → Chart Patterns** gallery — work through patterns visually
2. **Pattern Lab** with that pattern selected — see live examples on real stocks
3. **Stock Analyzer → AI Chart Analysis** for trades you're considering
4. **Learn → Risk Management** before you trade

---

## What's intentionally NOT included

Honest gap list — these are deliberate omissions, not oversights:

- ❌ **Real-time intraday tick streaming** (no WebSocket; scans hit Yahoo per-symbol)
- ❌ **Broker integration** (no order placement; Kite Connect / Upstox left for after-MVP)
- ❌ **Real-time alerts** (no email/Telegram notifications — explicitly removed per requirements)
- ❌ **Options chain analysis** (OI, max pain, PCR not yet integrated)
- ❌ **Multi-user / authentication** (single-user Streamlit app)
- ❌ **Tax module** (STCG/LTCG/F&O reporting)
- ❌ **Mobile UI** (Streamlit is desktop-first)
- ❌ **Institutional features** (sector rotation models, factor screens, DCF, Sharpe/Sortino, correlation matrices)
- ❌ **Cloud sync / collaboration** (everything is local JSON)

---

## File map

```
stock-intelligence-platform/
├── app/
│   ├── main.py                  # Navigation + startup
│   ├── components/              # Shared UI helpers
│   └── pages/                   # 16 Streamlit pages
├── engines/                     # Pattern · Filter · Rule · Scoring engines
├── services/                    # 16 service modules
├── storage/                     # Local JSON state + cache + reports
├── utils/                       # Theme · charts · formatting · TV chart helper
├── requirements.txt
├── README.md
└── FEATURES.md                  # ← this file
```

---

*Last updated: 2026-04-25*
