# Stock Intelligence Platform — Indian F&O Feature Analysis

> **Region:** NSE / BSE India  
> **Stack:** FastAPI (Python) + Next.js (TypeScript)  
> **Data sources:** NSE public APIs, Yahoo Finance REST, Screener.in  
> **AI engine:** Rule-based composite scorer + Claude AI (Anthropic SDK)

---

## Table of Contents

1. [Platform Overview](#1-platform-overview)
2. [Data Architecture](#2-data-architecture)
3. [F&O Universe & Instruments](#3-fo-universe--instruments)
4. [Option Chain Engine](#4-option-chain-engine)
5. [Futures Dashboard](#5-futures-dashboard)
6. [Put-Call Ratio & Sentiment](#6-put-call-ratio--sentiment)
7. [OI Analytics](#7-oi-analytics)
8. [India VIX Integration](#8-india-vix-integration)
9. [Expiry Heatmap](#9-expiry-heatmap)
10. [Live F&O Scanner (Confluence Model)](#10-live-fo-scanner-confluence-model)
11. [Options Buying Scanner (Madras Trader Model)](#11-options-buying-scanner-madras-trader-model)
12. [F&O AI Advisor](#12-fo-ai-advisor)
13. [Option Plan Advisor](#13-option-plan-advisor)
14. [Paper Trading Engine](#14-paper-trading-engine)
15. [Greeks Calculator](#15-greeks-calculator)
16. [Greeks Portfolio Tracker](#16-greeks-portfolio-tracker)
17. [Pattern Detection (Live Scanner)](#17-pattern-detection-live-scanner)
18. [Multi-Timeframe Analysis](#18-multi-timeframe-analysis)
19. [Backtesting Engine](#19-backtesting-engine)
20. [Position Sizing & Risk Management](#20-position-sizing--risk-management)
21. [Technical Indicators Available](#21-technical-indicators-available)
22. [Market Dashboard (F&O Context)](#22-market-dashboard-fo-context)
23. [F&O Education Page](#23-fo-education-page)
24. [API Reference — All F&O Endpoints](#24-api-reference--all-fo-endpoints)
25. [Storage & Persistence](#25-storage--persistence)
26. [Known Limitations & Gaps](#26-known-limitations--gaps)

---

## 1. Platform Overview

The Stock Intelligence Platform is a self-hosted, full-stack trading research tool targeting Indian equity derivatives (NSE F&O). It aggregates live market data, computes multi-dimensional technical and fundamental scores, and generates concrete option trade plans — all without paid data vendors. The platform intentionally avoids any live order routing; it is a research and paper-trading tool only.

### Core design principles

| Principle | How it's implemented |
|-----------|----------------------|
| No paid APIs | NSE public endpoints + Yahoo Finance REST + Screener.in scraper |
| India-first | INR throughout, lot sizes from NSE F&O list, weekly/monthly expiry calendars |
| Full-stack | FastAPI backend → Next.js frontend, no intermediate BFF |
| File-based storage | JSON files for watchlist, portfolio, paper trades, universe index files |
| Composable AI | Rule-based scorer (0-100) feeds Claude AI for narrative analysis |

---

## 2. Data Architecture

### Data sources

| Source | What's fetched | Caching |
|--------|----------------|---------|
| `nseindia.com` public API | Option chain, futures quotes, OI analytics, VIX, F&O securities list, index data, FII/DII flows | 60 s TTL for live data; 1 h for F&O stock list |
| Yahoo Finance REST (`query1` + `query2` fallback) | OHLCV (1m/5m/15m/1h/1d/1wk), market cap, fundamentals | File-based cache in `storage/cache/` |
| Screener.in (HTTP scraper) | P/E, P/B, ROE, debt-to-equity, quarterly P&L, shareholding, peers | In-memory cache; circuit-breaker on repeated failures |
| NSE RSS feeds | Corporate announcements, results calendar | Parsed via feedparser |

### NSE session management

The service maintains a persistent `requests.Session` with NSE cookies refreshed every 5 minutes. It seeds the session by visiting `nseindia.com` and `market-data/equity-derivatives-watch` to acquire valid session cookies before calling any API endpoint. On 401/403 responses, the session timestamp is zeroed to force an immediate refresh on the next request.

### Symbol normalisation

All symbols are stored and resolved in UPPER CASE. NSE equity symbols are mapped to Yahoo Finance by appending `.NS` (e.g. `RELIANCE` → `RELIANCE.NS`). Index symbols have explicit mappings:

| NSE symbol | Yahoo Finance ticker |
|------------|----------------------|
| NIFTY | `^NSEI` |
| BANKNIFTY | `^NSEBANK` |
| FINNIFTY | `NIFTY_FIN_SERVICE.NS` |
| SENSEX | `^BSESN` |

MIDCPNIFTY and BANKEX have no reliable Yahoo Finance ticker and are excluded from intraday scanning.

---

## 3. F&O Universe & Instruments

### Index derivatives

| Index | Expiry cycle | Lot size | Strike interval |
|-------|-------------|----------|-----------------|
| NIFTY | Weekly (Thursday) | 75 | 50 |
| BANKNIFTY | Weekly (Wednesday) | 15 | 100 |
| FINNIFTY | Weekly (Tuesday) | 40 | 50 |
| MIDCPNIFTY | Weekly (Thursday) | 75 | 25 |
| SENSEX | Weekly | 10 | 100 |
| BANKEX | Weekly | 15 | 100 |

### Equity F&O stock list

The platform maintains a hardcoded `LOT_SIZES` dictionary of ~65 large-cap F&O stocks with their correct lot sizes (updated for the 2024-25 NSE revision). At startup and on demand, the live F&O securities list is fetched from NSE's `equity-stockIndices?index=SECURITIES+IN+F%26O` endpoint and merged with the static list. The combined list drives:

- The live scanner universe (`stocks` preset = all ~180 NSE F&O equities)
- Strike interval computation (spot price-based ladder)
- Lot-size lookup for position sizing and plan cards

Notable exclusions from the live scanner: TATAMOTORS and ZOMATO (no stable Yahoo Finance ticker).

---

## 4. Option Chain Engine

### Endpoint

```
GET /api/fno/option-chain?symbol=NIFTY&expiry=25-Jun-2025
```

### Live chain (NSE)

The service calls NSE's `/api/option-chain-indices` (for indices) or `/api/option-chain-equities` (for stocks). It parses the `records.data[]` array, flattening each strike row into:

| Field group | Fields extracted |
|-------------|-----------------|
| Strike metadata | `strike`, `expiry` |
| CE side | `CE_oi`, `CE_oi_chg`, `CE_oi_chg_pct`, `CE_vol`, `CE_iv`, `CE_ltp`, `CE_chg`, `CE_chg_pct`, `CE_bid_qty`, `CE_bid`, `CE_ask_qty`, `CE_ask` |
| PE side | Same 12 fields with `PE_` prefix |

The `meta` object returned alongside the chain DataFrame includes:

- `expiry_dates` — all available expiry dates, sorted chronologically
- `strike_prices` — full strike list
- `underlying` — spot price at time of fetch
- `timestamp` — NSE data timestamp
- `total_ce_oi`, `total_pe_oi`, `total_ce_vol`, `total_pe_vol` — aggregate OI and volume

### Synthetic chain fallback (Black-Scholes)

When NSE is unavailable (rate-limited, market hours restriction), the service generates a fully synthetic chain:

1. Fetches spot price from NSE `/api/allIndices` or `get_fno_quote()`
2. Reads India VIX from `/api/allIndices` (fallback: 15%)
3. Computes ATM strike from the symbol-appropriate interval
4. Generates ±20 strikes around ATM
5. Applies IV skew: `IV = ATM_IV × exp(−0.4 × moneyness)` where `moneyness = ln(K/S)`
6. Computes CE and PE premiums via closed-form Black-Scholes with RBI-aligned risk-free rate of 6.5%
7. Models OI as a Gaussian bell curve centred 1 strike OTM on each side; doubles OI at round strikes (×1.9 for multiples of 10 intervals, ×1.4 for multiples of 5)
8. Generates realistic expiry dates: weekly for indices (correct day-of-week per instrument), monthly last-Thursday for equities
9. Sets `meta.synthetic = true` so the frontend can show a disclaimer

The synthetic chain covers 4-5 expiry dates simultaneously, enabling the expiry heatmap to function even when NSE is unreachable.

---

## 5. Futures Dashboard

### Endpoint

```
GET /api/fno/index-futures
```

Fetches near-month futures contracts for NIFTY, BANKNIFTY, FINNIFTY, and MIDCPNIFTY concurrently (4-thread pool) from NSE's `/api/quote-derivative` endpoint.

Each result card includes:

| Field | Description |
|-------|-------------|
| `symbol` | Index symbol |
| `index_name` | Full index name |
| `spot` | Current underlying value |
| `futures_ltp` | Near-month futures last traded price |
| `basis` | `futures_ltp − spot` (₹) |
| `basis_pct` | Basis as % of spot (3 decimal places) |
| `change` | Absolute price change |
| `change_pct` | % price change |
| `oi` | Open interest (contracts) |
| `vol` | Number of contracts traded |
| `expiry` | Contract expiry date |

**Equity futures quotes** are also available per-symbol via `GET /api/fno/underlying-quotes`, which iterates the F&O watchlist and fetches individual `quote-derivative` data for each stock.

---

## 6. Put-Call Ratio & Sentiment

### Endpoint

```
GET /api/fno/pcr?symbol=NIFTY
```

PCR is computed from live option chain aggregate OI and volume:

```
PCR_OI  = total_PE_OI  / total_CE_OI
PCR_Vol = total_PE_Vol / total_CE_Vol
```

### Interpretation thresholds (frontend display)

| PCR range | Market interpretation |
|-----------|-----------------------|
| > 1.3 | Strongly bullish (put writers dominant) |
| 1.0–1.3 | Mildly bullish |
| 0.7–1.0 | Neutral |
| 0.5–0.7 | Mildly bearish |
| < 0.5 | Strongly bearish |

### Historical PCR tracking

The service appends a daily PCR snapshot to `storage/data/fno_history.json` on first load each day:

```json
{
  "pcr":  [{"date": "2026-06-09", "nifty_pcr": 1.12, "banknifty_pcr": 0.94}],
  "vix":  [{"date": "2026-06-09", "vix": 13.5}]
}
```

The last 60 trading days are retained. This powers the **PCR Sentiment** page's historical chart.

### PCR Sentiment page (`/pcr-sentiment`)

Displays PCR for NIFTY and BANKNIFTY with:

- Current PCR_OI and PCR_Vol values
- 60-day rolling PCR history chart
- Sentiment interpretation badge
- CE vs PE total OI/volume comparison table

---

## 7. OI Analytics

### Endpoints

```
GET /api/fno/oi-spurts
GET /api/fno/oi-variations
```

### OI Spurts

Fetches NSE's live-analysis OI spurt endpoint (`/api/live-analysis-oi-spurts-underlyings`). Returns a DataFrame of underlyings with unusual OI build-up, normalised to:

| Field | Meaning |
|-------|---------|
| `symbol` | Stock/Index symbol |
| `oi_current` | Current open interest |
| `oi_prev` | Previous session OI |
| `oi_change` | Absolute OI change |
| `oi_change_pct` | % OI change |
| `ltp` | Last traded price |
| `price_chg_pct` | Price change % |

### OI Variations — Long/Short Buildup Classification

Fetches NSE's `/api/live-analysis-variations` and merges three categories:

| Category | Condition | Interpretation |
|----------|-----------|----------------|
| Long Buildup | Price ↑ + OI ↑ | Fresh longs being added |
| Short Buildup | Price ↓ + OI ↑ | Fresh shorts being added |
| Long Unwinding | Price ↓ + OI ↓ | Longs exiting |
| Short Covering | Price ↑ + OI ↓ | Shorts exiting |

The OI Analytics page (`/oi-analytics`) renders these four quadrants as sortable tables with colour-coded directional arrows.

---

## 8. India VIX Integration

### Endpoint

```
GET /api/fno/vix
```

Reads India VIX from NSE's `/api/allIndices` by matching any index with "VIX" and "INDIA" in the name. Returns:

- `vix` — current value
- `change` — absolute change (variation)
- `change_pct` — % change
- `open`, `high`, `low`, `prev_close` — OHLC for the session

VIX feeds into:

1. **Synthetic option chain** — ATM IV = VIX / 100
2. **Option plan advisor** — `iv_rank` used to decide buy vs sell strategy
3. **F&O dashboard** — VIX banner/card with context (low < 13, elevated 18-22, extreme > 25)
4. **Historical VIX chart** — stored in `fno_history.json`, 60-day rolling window

---

## 9. Expiry Heatmap

### Page: `/expiry-heatmap`

Visualises open interest across the full strike × expiry matrix as a colour-coded grid:

- **X-axis:** Strike prices (symmetric around ATM, ±20 strikes)
- **Y-axis:** Expiry dates (near-month to far-month)
- **Cell colour:** OI intensity (dark = high OI, light = low OI), separately for CE and PE
- **ATM row/column:** Highlighted with a different colour to orient the viewer

Data comes from `get_option_chain()` with no expiry filter, which returns all expiry rows simultaneously. When NSE is unavailable, the synthetic chain covers all 4-5 upcoming expiries with realistic OI decay (near-term: 100%, next: 55%, then 35%, 22%, 14%).

The heatmap helps identify:

- **Max pain** strike — where total option writers' pain is minimised
- **CE/PE OI walls** — key resistance/support levels from market maker positioning
- **OI concentration** — where large bets are parked across expiries

---

## 10. Live F&O Scanner (Confluence Model)

The live scanner is the platform's primary active-trading tool. It scans all F&O symbols across four timeframes simultaneously and applies a four-category confluence scoring model.

### Endpoint

```
GET  /api/live-scanner/scan?universe=top30&threshold=65
GET  /api/live-scanner/scan/stream?universe=top30&threshold=65   ← SSE streaming
GET  /api/live-scanner/chart-data?symbol=NIFTY&interval=5m&bars=80
GET  /api/live-scanner/universe
GET  /api/live-scanner/health
```

### Universe presets

| Preset | Contents |
|--------|----------|
| `indices` | NIFTY, BANKNIFTY, FINNIFTY, SENSEX (4 symbols) |
| `top30` | Top 30 high-liquidity F&O stocks |
| `stocks` | All live NSE F&O eligible equities (~180 symbols, fetched from NSE) |

### Timeframes scanned

`5m`, `15m`, `1h`, `1d` (four independent scans per symbol)

Data range fetched per interval:

| Interval | Lookback range |
|----------|----------------|
| 5m | 5 trading days |
| 15m | 15 calendar days |
| 1h | 60 calendar days |
| 1d | 1 year |

### Confluence Scoring Model (0–100)

#### Category 1 — Trend / Structure (0–30 pts)

Votes cast for bullish/bearish direction; 5 pts per vote, capped at 30:

| Signal | Bullish vote | Bearish vote |
|--------|-------------|-------------|
| Price vs EMA-20 | Price > EMA-20 | Price < EMA-20 |
| Price vs EMA-50 | Price > EMA-50 | Price < EMA-50 |
| EMA crossover | EMA-20 > EMA-50 | EMA-50 > EMA-20 |
| Price vs VWAP | Price > VWAP | Price < VWAP |
| 10-bar swing | New 10-bar high | New 10-bar low |

VWAP is computed as a session-based resetting VWAP (resets at each calendar date for intraday; each bar is its own session for daily data).

#### Category 2 — Momentum (0–25 pts)

| Condition | Points |
|-----------|--------|
| RSI 45–70 (bullish direction) | 12 |
| RSI > 70 overbought (bullish) | 4 |
| RSI 50–70 (bullish) | 8 |
| RSI 30–55 (bearish direction) | 12 |
| RSI < 30 oversold (bearish) | 4 |
| MACD histogram rising (bullish) | 13 |
| MACD histogram falling (bearish) | 13 |
| MACD histogram increasing in magnitude (either direction) | 6 |

#### Category 3 — Volume Confirmation (0–20 pts)

| Relative Volume | Points |
|-----------------|--------|
| ≥ 2.5× average | 20 — "Vol surge" |
| 1.8–2.5× average | 15 — "High vol" |
| 1.3–1.8× average | 10 — "Above avg" |
| < 1.3× average | 4 |
| No volume data (index) | 8 (neutral) |

Relative volume = current bar volume / 20-bar rolling average volume.

#### Category 4 — Candle Trigger (0–25 pts)

Pattern detection runs on the last 1–3 bars (see Section 17). If the detected pattern direction aligns with the trend direction, full points are awarded:

| Pattern strength | Points (aligned) |
|-----------------|-----------------|
| Weak (1) | 8 |
| Medium (2) | 16 |
| Strong (3) | 25 |

If the pattern contradicts the trend direction by strength ≥ 2, a 15-point penalty is applied to the total score.

If `trend_dir == "range"` but a pattern is detected, the pattern direction upgrades the final direction.

#### Final direction and total

```
total = trend_pts + momentum_pts + volume_pts + candle_pts
final_direction = trend_dir (upgraded by pattern if trend was "range")
```

Only setups with `total ≥ threshold` (default 65) are surfaced.

### Output: Setup Card

Each qualifying setup card contains:

| Field | Description |
|-------|-------------|
| `symbol` | NSE symbol |
| `timeframe` | `5m` / `15m` / `1h` / `1d` |
| `direction` | `bullish` / `bearish` / `range` |
| `confluence_score` | 0–100 |
| `score_breakdown` | `{trend, momentum, volume, candle}` |
| `pattern` | Detected candle pattern name |
| `trigger_price` | Spot price at scan time |
| `atr` | ATR at scan time |
| `rel_vol` | Relative volume (×) |
| `reasons` | Human-readable list of scoring signals |
| `plan` | `OptionPlan` object (see Section 13) |
| `backtest` | `{hit_rate, sample_size}` from 6-month daily backtest |

### SSE Streaming

The `/scan/stream` endpoint uses Server-Sent Events (SSE) to emit per-symbol progress in real time:

| Event type | Payload |
|------------|---------|
| `start` | `{total, universe}` |
| `progress` | `{symbol, found, done, total, setups_so_far}` |
| `enriching` | `{setups}` — begins option chain + backtest enrichment |
| `result` | Full scan payload |
| `[DONE]` | Literal string — signals stream end |

A `Semaphore(6)` limits concurrent Yahoo Finance connections during streaming. The non-streaming endpoint uses `Semaphore(4)`.

### Scan summary block

The summary returned alongside each scan includes:

- `total_symbols` — number of symbols in the universe
- `unique_setups` — symbols with at least one qualifying setup
- `total_setups` — total setups (a symbol can appear in multiple timeframes)
- `daily_setups` / `intraday_setups` — breakdown
- `bullish`, `bearish`, `range` — directional counts
- `strong_80plus` — setups with score ≥ 80
- `by_timeframe` — count per timeframe

---

## 11. Options Buying Scanner (Madras Trader Model)

A separate scanner (`/options-scanner`) designed for premium buying opportunities, distinct from the confluence scanner.

### Endpoint

```
GET /api/options-scanner/scan?universe=NIFTY_50&min_score=60
```

### Scoring dimensions

This scanner evaluates each symbol across:

1. **Multi-timeframe breakout** — checks 15m, 1h, 1d alignment (MTF Analyzer)
2. **Composite score** — from `ai_service.py` rule-based verdict
3. **IV assessment** — uses India VIX as a proxy when individual stock IV is unavailable
4. **DTE** (Days to Expiry) — prefers weekly contracts (3–7 DTE for intraday momentum, 7–21 for swing)
5. **Signal type** — breakout, pullback, continuation, reversal

### Output per symbol

Each result includes:

- Signal type and direction
- Suggested option type (CE/PE)
- Strike recommendation (ATM or near-ATM)
- Entry, stop-loss, and target levels
- Score (0–100 composite)
- IV-rank context

---

## 12. F&O AI Advisor

### Page: `/fo-ai-advisor`

### Endpoint

```
POST /api/fno/ai-analysis   (Claude AI backend)
```

The advisor combines the live confluence score with Claude AI (Anthropic SDK, `claude-sonnet-4-6`) to produce a narrative trade plan.

Input to Claude:

- Confluence model results (direction, score breakdown, reasons)
- Option chain data (nearest expiry, ATM strike, IV)
- India VIX
- Nearest expiry DTE
- Pattern detected

Claude's output:

- Trade recommendation (BUY CE / BUY PE / SELL strangle / AVOID)
- Rationale (2–3 sentences referencing specific technical signals)
- Entry zone, stop-loss, target 1, target 2 (spot levels)
- Option strikes and premiums
- Risk note (IV warning if VIX > 18, liquidity note for small-cap stocks)
- Alternative scenario (what would invalidate the setup)

---

## 13. Option Plan Advisor

A deterministic (non-AI) trade plan builder that runs on every live-scanner setup card. This is the `option_advisor.py` service.

### Plan building logic

**Directional setups (bullish/bearish):**

1. Option type: CE for bullish, PE for bearish
2. Strike: ATM (rounded to nearest interval)
3. Stop-loss: `spot − 1.5 × ATR` (bullish) or `spot + 1.5 × ATR` (bearish), minimum 0.3% of spot
4. Target 1: `entry ± 1.5 × risk`
5. Target 2: `entry ± 2.5 × risk`
6. R:R at T1 = 1.5 (always meets the 1.3 floor)
7. Premium estimation: extracted from live option chain at the ATM strike; falls back to `spot × 0.01` (1%) if chain unavailable
8. Premium stop: `entry_premium − 0.5 × risk_pts` (capped at ₹1 minimum)
9. Premium targets: `entry_premium ± delta × risk` where delta = 0.5 (ATM approximation)

**Range-bound setups (IV rank ≥ 40):**

1. Sells the OTM side with slight directional lean (CE if momentum_score ≥ 12, else PE)
2. Strike: 1 interval OTM from ATM
3. Premium stop: 2.5× premium collected
4. Premium target 1: 50% of premium collected
5. Premium target 2: 10% of premium collected (max decay capture)
6. R:R gate: rejects if below 1.3

**IV warnings:**

| IV rank | Warning shown |
|---------|---------------|
| > 70 | "Premium expensive — consider debit spread" |
| 50–70 and score < 75 | "Moderate IV rank — ensure conviction before buying" |
| ≥ 40 and range-bound | "Selling premium is the edge here" |

**Liquidity gate:**

If an option chain is available, the plan checks the recommended strike for:
- Minimum OI: 500 contracts
- Minimum volume: 100 contracts

If either threshold fails, a "Liquidity unverified" warning is added and `liquidity_ok = false`.

**Exit rule string (always included):**

```
"Exit when: spot < {SL} (stop) | spot > {T1} T1 | {T2} T2.
Intraday: exit by 3:10 PM or if stalled > 30 min (theta burn)."
```

---

## 14. Paper Trading Engine

### Page: `/paper-trade`

### Endpoints

All F&O paper trades are managed through the positions service (implicit in the paper trade router):

```
GET    /api/positions           — All open + closed positions
POST   /api/positions/add       — Open new paper position
PUT    /api/positions/{id}      — Update (partial exit, move stop)
DELETE /api/positions/{id}      — Close position
```

### Position schema

Each paper trade record stores:

| Field | Type | Description |
|-------|------|-------------|
| `id` | string (UUID) | Unique position ID |
| `symbol` | string | Underlying symbol |
| `instrument` | string | e.g. `NIFTY 25JUN 24000 CE` |
| `action` | string | `BUY` or `SELL` |
| `lots` | int | Number of lots |
| `lot_size` | int | Lot size from NSE |
| `entry_price` | float | Premium at entry |
| `entry_spot` | float | Underlying spot at entry |
| `entry_time` | ISO datetime | When entered |
| `sl_price` | float | Stop-loss premium |
| `sl_spot` | float | Stop-loss spot level |
| `t1_price` | float | Target 1 premium |
| `t2_price` | float | Target 2 premium |
| `exit_price` | float | Premium at exit (null if open) |
| `exit_time` | ISO datetime | When exited |
| `pnl` | float | Realised P&L (₹) |
| `status` | string | `open` / `closed` / `stopped_out` / `target_hit` |
| `notes` | string | Free-text trade notes |

### P&L calculation

```
P&L = (exit_price − entry_price) × lots × lot_size    (for BUY)
P&L = (entry_price − exit_price) × lots × lot_size    (for SELL)
```

### Storage

All paper trades are persisted to `storage/data/paper_trades.json`. The file is append-only for open positions; closed positions are updated in-place.

### Paper Trade Modal

The `PaperTradeModal.tsx` component is embedded in both the live scanner and the F&O AI advisor pages. When a user clicks "Paper Trade" on a setup card, it pre-fills the modal with:

- Symbol and instrument description
- Suggested action (BUY/SELL), option type, strike, expiry
- Entry, SL, and target prices from the `OptionPlan`
- Lot size from the F&O service

---

## 15. Greeks Calculator

### Service: `greeks_calculator.py`

Implements Black-Scholes closed-form Greeks for all F&O options.

### Inputs

| Parameter | Source |
|-----------|--------|
| S (spot) | NSE quote or Yahoo Finance |
| K (strike) | From option chain row |
| T (time to expiry) | Calendar days / 365 |
| r (risk-free rate) | 6.5% (RBI-aligned) |
| σ (volatility) | IV from NSE option chain; India VIX / 100 as fallback |

### Greeks computed

| Greek | Symbol | Formula |
|-------|--------|---------|
| Delta | Δ | ∂V/∂S via N(d1) for CE, N(d1)−1 for PE |
| Gamma | Γ | φ(d1) / (S·σ·√T) |
| Theta | Θ | − (S·φ(d1)·σ) / (2√T) − r·K·e^(−rT)·N(d2) (annualised, divided by 365 for daily) |
| Vega | V | S·φ(d1)·√T / 100 (per 1% IV change) |
| Rho | ρ | K·T·e^(−rT)·N(d2) / 100 |

where d1 = [ln(S/K) + (r + σ²/2)·T] / (σ·√T), d2 = d1 − σ·√T, and φ is the standard normal PDF.

### Output

Each option row in the chain view is enriched with Greeks. The option chain page shows Delta, Gamma, Theta, Vega alongside OI, IV, and LTP.

---

## 16. Greeks Portfolio Tracker

### Page: `/greeks`

### Endpoint

```
GET /api/fno/greek-summary
```

Aggregates Greeks across all positions in the F&O watchlist (or paper trade portfolio):

| Aggregate metric | Description |
|-----------------|-------------|
| Net Delta | Portfolio directional exposure (₹ per 1-pt move in underlying) |
| Net Gamma | Rate of change of delta (convexity) |
| Net Theta | Daily time decay (₹/day across all positions) |
| Net Vega | IV exposure (₹ per 1% IV change) |

Displays a summary card showing whether the portfolio is:

- **Delta positive** (net long) or **delta negative** (net short)
- **Theta positive** (net seller) or **theta negative** (net buyer)
- **Gamma positive** (benefits from large moves) or **gamma negative** (benefits from stability)

Also shows per-symbol Greek breakdown in a table for each F&O watchlist symbol.

---

## 17. Pattern Detection (Live Scanner)

The `pattern_detector.py` service is the candle trigger engine for the live scanner (Category 4 in the confluence model). It inspects the last 1–3 bars of any OHLCV DataFrame.

### Patterns detected

| Pattern | Bars checked | Direction | Strength |
|---------|-------------|-----------|----------|
| Bullish Engulfing | 2 bars | Bullish | Medium (2) |
| Bearish Engulfing | 2 bars | Bearish | Medium (2) |
| Hammer | 1 bar | Bullish | Medium (2) |
| Shooting Star | 1 bar | Bearish | Medium (2) |
| Bullish Marubozu | 1 bar | Bullish | Strong (3) |
| Bearish Marubozu | 1 bar | Bearish | Strong (3) |
| Inside Bar Breakout (bull) | 3 bars | Bullish | Weak (1) |
| Inside Bar Breakout (bear) | 3 bars | Bearish | Weak (1) |
| Doji / Spinning Top | 1 bar | Neutral | Weak (1) |

**Points mapping:**

- Strength 1 (Weak) → 8 pts
- Strength 2 (Medium) → 16 pts
- Strength 3 (Strong) → 25 pts

**Contra-pattern penalty:** If a pattern of strength ≥ 2 points opposite to the trend direction, 15 pts are deducted from the total confluence score.

The main `patterns.py` router (equity scanner) maintains a separate library of 39 full chart patterns (head-and-shoulders, double tops/bottoms, flags, wedges, triangles, cup-and-handle, etc.) computed over longer lookback windows. The live scanner uses the lighter single-bar/two-bar detector above for speed.

---

## 18. Multi-Timeframe Analysis

### Service: `mtf_analyzer.py`

Used by both the options-buying scanner and the F&O AI advisor to assess directional alignment across timeframes.

### Timeframe set

`15m`, `1h`, `1d` (three-timeframe model)

### Alignment logic

For each timeframe, the signal is classified as `bullish`, `bearish`, or `neutral` based on EMA20/50 relationship and RSI position.

| Score | Condition |
|-------|-----------|
| 3/3 aligned | All three timeframes agree → Strong conviction |
| 2/3 aligned | Two timeframes agree → Moderate conviction |
| 1/3 or 0/3 | Conflicting → Avoid or reduce size |

The MTF score feeds into the options-buying scanner's composite score as a major component.

---

## 19. Backtesting Engine

### Two backtest systems

#### A. Pattern backtest (equity scanner)

```
POST /api/backtests/run
{
  "pattern": "Bullish Engulfing",
  "universe": "NIFTY_50",
  "exit_days": 5,
  "risk_reward": 1.5
}
```

Runs a systematic backtest of any of the 39 chart patterns across the selected universe. For each signal:

- Entry: close of pattern bar
- Stop-loss: ATR-based (1.5× ATR below entry for bullish)
- Target: 1.5× risk (configurable R:R)
- Exit: whichever of stop, target, or hold-period (default 5 days) is hit first

Returns: win rate, average gain/loss, max drawdown, equity curve data, trade list.

#### B. In-scan mini-backtest (live scanner)

For each setup in the live scanner that has a detected candle pattern, a lightweight 6-month daily backtest is run:

- Scans the symbol's 1-year daily OHLCV for all occurrences of the same pattern
- Uses 5-bar forward-looking window for outcome assessment
- Returns `{hit_rate, sample_size}` on the setup card
- If `sample_size < 5`, returns `null` hit_rate with note "Low sample — unproven"

---

## 20. Position Sizing & Risk Management

### Page: `/position-sizing`

### Endpoints

```
POST /api/positions/calc
{
  "capital": 500000,
  "risk_pct": 1.5,
  "entry": 200,
  "stop_loss": 190,
  "lot_size": 75
}

POST /api/positions/kelly
{
  "win_rate": 0.55,
  "avg_win": 1.5,
  "avg_loss": 1.0
}
```

### Fixed-fraction sizing

```
Risk per trade = Capital × (risk_pct / 100)
Risk per lot   = (Entry − SL) × lot_size
Lots to trade  = floor(Risk per trade / Risk per lot)
Capital at risk = Lots × lot_size × (Entry − SL)
```

Respects lot size; never suggests fractional lots.

### Kelly criterion

```
Kelly fraction = W − (1−W)/R
```
where W = win rate, R = average win / average loss.

The platform applies a Half-Kelly by default for volatility reduction.

### AI allocation

The `ai_service.py` also provides an AI-driven position sizing suggestion that considers:

- Confluence score (higher score → allowed larger size)
- IV environment (high VIX → reduce size)
- Sector concentration (reduces allocation if same sector is over-represented in portfolio)

---

## 21. Technical Indicators Available

All indicators are computed via the Python `ta` library (v0.11). Available per-symbol via `GET /api/stocks/{symbol}/indicators`.

| Indicator | Parameters | Usage |
|-----------|-----------|-------|
| EMA | 9, 20, 50, 200 | Trend direction, crossover signals |
| SMA | 20, 50, 200 | Baseline trend |
| VWAP (session-reset) | Intraday only | Institutional reference price |
| RSI | 14 | Momentum, overbought/oversold |
| MACD | 12/26/9 | Momentum, histogram direction |
| Bollinger Bands | 20, 2σ | Volatility, mean-reversion zones |
| ATR | 14 | Volatility, stop-loss sizing |
| Stochastic | 14,3,3 | Momentum extremes |
| ADX | 14 | Trend strength (used in AI verdict) |
| OBV | — | Volume-price trend confirmation |
| Relative Volume | 20-bar rolling | Volume confirmation in live scanner |
| IV (from chain) | — | Options-specific volatility measure |

---

## 22. Market Dashboard (F&O Context)

### Page: `/dashboard` and `/fo-dashboard`

The main market dashboard surfaces F&O-relevant data:

| Widget | Data source |
|--------|-------------|
| Market status (pre-open / open / closed) | NSE market status API |
| NIFTY, BANKNIFTY, SENSEX spot quotes | NSE `/api/allIndices` |
| India VIX banner | NSE `/api/allIndices` |
| Sector heatmap (heat = % change) | NSE sector indices |
| FII/DII net flows (₹ crore) | NSE FII-DII data |
| GIFT NIFTY (pre-market sentiment) | NSE market status payload |

The dedicated F&O dashboard (`/fo-dashboard`) adds:

- Live index futures cards (spot, futures, basis for NIFTY/BANKNIFTY/FINNIFTY/MIDCPNIFTY)
- PCR_OI for NIFTY and BANKNIFTY
- India VIX with previous-close comparison
- Top OI spurt underlyings (top 10 by % OI change)
- F&O watchlist quote strip

---

## 23. F&O Education Page

### Page: `/fo-learn`

Static + dynamic educational content covering:

- Options basics (CE/PE, moneyness, expiry)
- Greeks explained with real NSE examples
- Options strategies (long call, long put, covered call, bull call spread, bear put spread, iron condor, straddle, strangle)
- PCR interpretation guide
- VIX interpretation guide
- OI analysis and buildup patterns
- Position sizing for options
- Risk management rules (max loss per trade, max loss per week)

Pattern examples from `pattern_examples.py` provide synthetic OHLCV data to render visual chart illustrations for each candle pattern directly in the browser.

---

## 24. API Reference — All F&O Endpoints

> **Accuracy note:** This section was regenerated from the actual router code after Phase 2.
> The pre-Phase 2 version contained 6 endpoints that didn't exist and omitted 13+ that did.

### `/api/fno/*` — Core F&O data + paper trading

| Method | Path | Description | Phase |
|--------|------|-------------|-------|
| GET | `/api/fno/option-chain` | Full option chain; auto-falls back to Black-Scholes synthetic | v2 |
| GET | `/api/fno/index-futures` | Live NIFTY/BN/FIN/MIDCP futures + basis | v2 |
| GET | `/api/fno/index-prices` | NIFTY 50, BANK, FIN, MIDCAP SELECT, IT, VIX from allIndices | v2 |
| GET | `/api/fno/vix` | India VIX current value + OHLC | v2 |
| GET | `/api/fno/pcr` | Put-Call Ratio (OI + Vol) for any symbol | v2 |
| GET | `/api/fno/history` | 60-day rolling PCR + VIX daily snapshots | Phase 2 |
| GET | `/api/fno/oi-spurts` | Top OI build-up stocks (NSE live-analysis) | v2 |
| GET | `/api/fno/oi-variations` | NSE's own long/short buildup/unwinding data | v2 |
| GET | `/api/fno/symbols` | All F&O eligible equity symbols (NSE list) | v2 |
| GET | `/api/fno/scan` | OI-based server-side scanner (High OI Buildup, etc.) | v2 |
| GET | `/api/fno/watchlist` | F&O watchlist symbols (default: NIFTY, BANKNIFTY) | Phase 2 |
| POST | `/api/fno/watchlist` | Add symbol to F&O watchlist | Phase 2 |
| DELETE | `/api/fno/watchlist/{symbol}` | Remove from F&O watchlist | Phase 2 |
| GET | `/api/fno/underlying-quotes` | Live spot LTP + change% for watchlist/given symbols | Phase 2 |
| GET | `/api/fno/greek-summary` | Net Δ/Γ/Θ/Vega across open paper-trade positions | Phase 2 |
| GET | `/api/fno/max-pain` | Max pain strike for symbol + expiry | Phase 3 |
| GET | `/api/fno/iv-rank` | True IV Rank (52w percentile) for a symbol | Phase 3 |
| POST | `/api/fno/iv-snapshot` | Manually trigger daily ATM IV snapshot | Phase 3 |
| GET | `/api/fno/strategies` | Saved named option strategy legs | v2 |
| POST | `/api/fno/strategies` | Save a strategy by name | v2 |
| DELETE | `/api/fno/strategies/{name}` | Delete a saved strategy | v2 |
| GET | `/api/fno/ai-suggest` | Claude AI F&O trade suggestion for a symbol | v2 |
| GET | `/api/fno/paper-trades/open` | All open paper-trade positions | v2 |
| GET | `/api/fno/paper-trades/closed` | All closed paper-trade positions | v2 |
| GET | `/api/fno/paper-trades/portfolio` | Portfolio summary (equity, P&L, win rate) | v2 |
| GET | `/api/fno/paper-trades/equity-curve` | Closed trade P&L series for chart | v2 |
| POST | `/api/fno/paper-trades` | Add a new paper trade | v2 |
| POST | `/api/fno/paper-trades/{id}/close` | Close a paper trade with exit price | v2 |
| POST | `/api/fno/paper-trades/refresh-prices` | Fetch live LTPs from NSE, update open P&L | Phase 2 |
| POST | `/api/fno/paper-trades/reset` | Reset portfolio to initial capital | v2 |

### `/api/live-scanner/*` — Intraday F&O confluence scanner

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/live-scanner/scan` | Synchronous confluence scan (all 4 TFs) |
| GET | `/api/live-scanner/scan/stream` | SSE streaming scan with per-symbol progress |
| GET | `/api/live-scanner/chart-data` | OHLCV candles for mini-chart in expanded row |
| GET | `/api/live-scanner/universe` | Available universe presets and symbol counts |
| GET | `/api/live-scanner/health` | Health check (polls before showing scan button) |

### `/api/options-scanner/*` — MTF options buying scanner

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/options-scanner/scan` | Full universe scan for options buying setups |
| GET | `/api/options-scanner/deep-dive` | Full MTF analysis + CE/PE plans for one symbol |
| GET | `/api/options-scanner/market-context` | VIX, PCR, index trend snapshot |
| GET | `/api/options-scanner/backtest` | Walk-forward backtest of the MT strategy |

### `/api/positions/*` — Position sizing

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/positions/calc` | Fixed-fraction position size (quantity, capital at risk) |
| POST | `/api/positions/kelly` | Kelly criterion sizing |

### `/api/backtests/*` — Pattern backtesting

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/backtests/run` | Pattern backtest across universe (win rate, drawdown, equity curve) |

---

## 25. Storage & Persistence

All storage is file-based (no database). Relevant F&O files:

| File path | Contents | Format |
|-----------|----------|--------|
| `storage/data/paper_trades.json` | All paper trade records | JSON array |
| `storage/data/fno_history.json` | 60-day PCR + VIX history | JSON dict |
| `storage/data/saved_strategies.json` | Named option strategy legs | JSON array |
| `storage/config/fno_watchlist.json` | F&O watchlist symbols | JSON dict |
| `storage/config/watchlist.json` | Equity watchlist | JSON dict |
| `storage/config/portfolio.json` | Equity holdings | JSON dict |
| `storage/universe/NIFTY_50.json` | NIFTY 50 constituents | JSON array |
| `storage/universe/NIFTY_BANK.json` | Bank Nifty constituents | JSON array |
| `storage/cache/*.json` | Yahoo Finance OHLCV cache | JSON keyed by symbol+interval |
| `storage/logs/backend.log` | Rotating log (5 MB × 3 backups) | Text |

---

## 26. Known Limitations & Gaps

> **Status as of Phase 2 (2026-06-09):** Items marked ✅ RESOLVED were fixed in Phase 2.

| Area | Status | Note |
|------|--------|------|
| **Live data** | Open | No WebSocket feed; all data is polled on demand. |
| **NSE rate limits** | Open | NSE public API rate-limits outside market hours. Session refresh (5 min TTL) mitigates; pages show context-specific retry guidance. |
| **Missing YF tickers** | Open | TATAMOTORS, ZOMATO excluded from live scanner (YF 404). MIDCPNIFTY, BANKEX have no YF ticker. See `REMAINING_WORK.md`. |
| **Greeks accuracy** | Open | Black-Scholes constant-vol assumption; no dividend yield; no smile modelling. |
| **IV rank per symbol** | Open | Portfolio Greeks use India VIX / 100 as proxy; no per-symbol historical IV series stored. |
| **Order routing** | Open (by design) | Paper trading only. No broker integration. |
| **Max pain standalone endpoint** | ✅ RESOLVED (Phase 3) | `GET /api/fno/max-pain` added; reuses `calculate_max_pain()` from `greeks_calculator.py`. |
| **Historical F&O data** | Open | NSE ban list, participant-wise OI, rollover data not fetched. |
| **Screener.in scraping** | Open | HTML structure may change; circuit-breaker prevents cascades but fundamentals may become stale. |
| **Multi-leg strategy payoff** | ✅ RESOLVED | `strategy.ts` implements `calculatePayoff()`, `calculateBreakevens()`, `calculateMaxProfitLoss()`, payoff diagram for all strategy types including iron condor and calendar. |
| **Strategy builder equity symbols** | ✅ RESOLVED | Symbol selector now loads all F&O equities from `GET /api/fno/symbols` (not just indices). |
| **Alerts** | Design only (Phase 3) | `ALERTS_DESIGN.md` written; awaiting sign-off on v1 scope. See §3 of that doc. |
| **PCR Sentiment page (P0-1)** | ✅ RESOLVED | Page now calls `GET /api/fno/pcr` and renders real PCR cards. |
| **Historical PCR/VIX chart (P1-1)** | ✅ RESOLVED | `GET /api/fno/history` exposed; 60-day dual-axis chart on PCR Sentiment page. |
| **F&O Watchlist CRUD (P1-2)** | ✅ RESOLVED | `GET/POST/DELETE /api/fno/watchlist` implemented; watchlist quote strip on fo-dashboard. |
| **Portfolio aggregate Greeks (P1-4)** | ✅ RESOLVED | `GET /api/fno/greek-summary` implemented; portfolio Greeks card on greeks page. |
| **Paper trade live P&L (P1-5)** | ✅ RESOLVED | `POST /api/fno/paper-trades/refresh-prices` exposed; Refresh Prices button on paper-trade page. |
| **Strategy builder equity symbols (P1-6)** | ✅ RESOLVED | (see above) |
| **Underlying quotes endpoint (P1-7)** | ✅ RESOLVED | `GET /api/fno/underlying-quotes` implemented. |
| **`/api/fno/oi-variations` dead endpoint (P1-3)** | ✅ RESOLVED | OI Analytics page now fetches it; shows NSE variation panel when data is available. |
| **9 F&O pages orphaned from nav (P0-3)** | ✅ RESOLVED | All 13 F&O pages now in sidebar nav with 5-group structure. |
| **Scanner unification (P2-2)** | ✅ RESOLVED (Phase 3) | OI types route to backend `/api/fno/scan`; chain types (PCR, Max Pain, IV Crush) now unlocked in fo-scanner using client-side `runFoScan()`. |
| **Missing YF tickers (TATAMOTORS, ZOMATO, MIDCPNIFTY, BANKEX)** | ✅ RESOLVED (Phase 3) | All four now work: TMCV.NS, ETERNAL.NS, NIFTY_MID_SELECT.NS, BSE-BANK.BO. |
| **IV rank per symbol** | ✅ RESOLVED (Phase 3) | Daily ATM IV snapshot in `iv_history.json`; `get_iv_rank()` computes 52-week percentile; portfolio Greeks use per-symbol IV when ≥30 days available, VIX proxy otherwise. |

---

*Document last updated: 2026-06-09 (Phase 3 completion)*  
*Platform version: post-refactor v2 + Phase 2 + Phase 3 remediation (branch: main)*
