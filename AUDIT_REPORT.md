# Phase 1 — Feature Parity Audit Report

> Generated: 2026-06-09  
> Branch: `main`  
> Method: Read every backend router + frontend page + fno-api.ts + sidebar.tsx from source.  
> Status key: ✅ present & working · ⚠️ present but broken/partial · ❌ missing · ❓ unverifiable without live NSE

---

## 1. Full Parity Matrix

### 1A. Core F&O Data Layer

| Feature | Doc § | Backend module / endpoint | Backend | Frontend page / component | Frontend | Wired E2E? | Gap / Notes |
|---------|-------|--------------------------|---------|--------------------------|----------|-----------|-------------|
| Option Chain (live NSE) | §4 | `fno.py` `GET /api/fno/option-chain` | ✅ | `/option-chain` page | ✅ | ✅ | NSE cookies managed server-side |
| Synthetic BS fallback | §4 | `fno_data_service.get_synthetic_option_chain()` | ✅ | All chain consumers | ✅ | ✅ | `meta.synthetic=true` propagated; pages show ⚗ banner |
| Index Futures (NIFTY/BN/FIN/MIDCP) | §5 | `fno.py` `GET /api/fno/index-futures` | ✅ | `/fo-dashboard` | ✅ | ✅ | Allotted fallback via allIndices too |
| India VIX (live) | §8 | `fno.py` `GET /api/fno/vix` | ✅ | `/fo-dashboard`, `/pcr-sentiment`, `/greeks` | ✅ | ✅ | Returns open/high/low/prev\_close |
| Put-Call Ratio | §6 | `fno.py` `GET /api/fno/pcr` | ✅ | `/pcr-sentiment` (⚠️ see §P0-1) | ⚠️ | ⚠️ | `/api/fno/pcr` works; **page does not call it** |
| Historical PCR / VIX (60-day) | §6 | **No endpoint** — data in `fno_history.json` | ❌ | Not rendered anywhere | ❌ | ❌ | `append_daily_fno_snapshot()` writes data; no API route to read it |
| OI Spurts | §7 | `fno.py` `GET /api/fno/oi-spurts` | ✅ | `/fo-dashboard`, `/oi-analytics`, `/pcr-sentiment` | ✅ | ✅ | — |
| OI Variations (buildup) | §7 | `fno.py` `GET /api/fno/oi-variations` | ✅ | **Never called** | ❌ | ❌ | Frontend derives buildup client-side from OI spurts via `getOiBuildup()` in fno-api.ts; backend endpoint is a dead route |
| F&O Symbols list | §3 | `fno.py` `GET /api/fno/symbols` | ✅ | Multiple pages | ✅ | ✅ | Undocumented in §24 |
| Lot sizes | §3 | `fno_data_service.LOT_SIZES` + `get_fno_stocks()` | ✅ | `fno-types.ts getLotSize()` | ✅ | ✅ | ~65 symbols hardcoded + live NSE list merge |
| Underlying quotes (F&O watchlist) | §5 | **No endpoint** | ❌ | Not rendered | ❌ | ❌ | `get_fno_watchlist()` + `get_fno_quote()` in service but no API route |
| F&O Watchlist CRUD | §25 | **No endpoints** | ❌ | Not rendered | ❌ | ❌ | Service functions exist; no router wiring |

### 1B. Expiry Heatmap, Max Pain, Rollover

| Feature | Doc § | Backend | Frontend | Wired E2E? | Gap / Notes |
|---------|-------|---------|----------|-----------|-------------|
| Expiry Heatmap (OI grid) | §9 | `GET /api/fno/option-chain` (no-expiry) | `/expiry-heatmap` | ✅ | Works. ATM highlighted, synthetic disclaimer shown |
| Max Pain per expiry | §9, §26 | `greeks_calculator.calculate_max_pain()` (used server-side) | `greeks.ts calculateMaxPain()` (client-side) | ✅ | **§26 gap RESOLVED** — computed in both frontend and options-scanner deep-dive |
| PCR per expiry | §9 | Derived in frontend from chain rows | `/expiry-heatmap` `buildExpiryStats()` | ✅ | Works, computed from option chain rows |
| Rollover stats | §9 | Same as above | `/expiry-heatmap` `RolloverTable` | ✅ | Shows CE OI, PE OI, PCR, Max Pain per expiry |
| `/expiry-heatmap` page in sidebar | §3 | — | **Not in `FO_NAV` and not in `FO_PREFIXES`** | ❌ | **Orphan route** — no auto mode-switch; invisible to users |

### 1C. Live F&O Scanner (Confluence Model)

| Feature | Doc § | Backend | Frontend | Wired E2E? | Gap / Notes |
|---------|-------|---------|----------|-----------|-------------|
| Sync scan (`/scan`) | §10 | `live_scanner.py GET /api/live-scanner/scan` | `/live-scanner` | ✅ | — |
| SSE streaming (`/scan/stream`) | §10 | `live_scanner.py GET /api/live-scanner/scan/stream` | `/live-scanner` | ✅ | ConditionalGZipMiddleware correctly skips SSE |
| Confluence 4-category model | §10 | `confluence_scorer.py` | Score breakdown displayed in cards | ✅ | All 4 categories: Trend(30), Momentum(25), Volume(20), Candle(25) |
| Option plan per setup | §13 | `option_advisor.build_plan()` | Plan card on each setup | ✅ | ATR-based SL, T1, T2; IV warnings; liquidity gate |
| Mini-backtest per setup | §19 | `_backtest_with_df()` in `live_scanner.py` | `backtest {hit_rate, sample_size}` on card | ✅ | 6-month daily, 5-bar forward window |
| Chart data endpoint | §10 | `GET /api/live-scanner/chart-data` | Mini charts in expanded row | ✅ | Undocumented in §24 |
| Universe presets | §10 | `UNIVERSE_PRESETS` in `intraday_data.py` | Universe selector dropdown | ✅ | `indices`, `top30`, `stocks` (~180 NSE F&O) |
| Semaphore concurrency control | §10 | `Semaphore(4)` sync / `Semaphore(6)` SSE | — | ✅ | Prevents YF rate-limit; fresh Session per request |

### 1D. Options Buying Scanner (Madras Trader)

| Feature | Doc § | Backend | Frontend | Wired E2E? | Gap / Notes |
|---------|-------|---------|----------|-----------|-------------|
| Main scan | §11 | `options_scanner.py GET /api/options-scanner/scan` | `/options-scanner` | ✅ | Calls `options_buying_scanner.run_options_scan()` |
| Deep dive per symbol | §11 | `GET /api/options-scanner/deep-dive` | `/options-scanner` expanded result | ✅ | MTF + CE/PE setups + option chain + max pain + PCR |
| Market context | §11 | `GET /api/options-scanner/market-context` | Pre-scan context card | ✅ | VIX, PCR, NIFTY/BN spot + trend |
| Walk-forward backtest | §11 | `GET /api/options-scanner/backtest` | Backtest tab | ✅ | `options_backtest_mt.backtest_mt_strategy()` |

### 1E. F&O AI Advisor

| Feature | Doc § | Backend | Frontend | Wired E2E? | Gap / Notes |
|---------|-------|---------|----------|-----------|-------------|
| Claude AI suggestion | §12 | `fno.py GET /api/fno/ai-suggest` → `fno_ai_service.py` | `/fo-ai-advisor` | ✅ | Requires Anthropic API key in Settings. Graceful error if missing. |
| Add to paper trade from AI card | §12 | `POST /api/fno/paper-trades` | "Add to Paper Trade" button in ResultCard | ✅ | `addPaperTrade()` called directly via `faPost()` |
| MTF analysis in result | §12 | `fno_ai_service.py` | Expandable "MTF Analysis" section | ✅ | `mtf_summary`, `trade_qualification_reasons`, `invalidation_conditions` |

### 1F. Option Plan Advisor

| Feature | Doc § | Backend | Frontend | Wired E2E? | Gap / Notes |
|---------|-------|---------|----------|-----------|-------------|
| Plan attached to live-scanner cards | §13 | `option_advisor.build_plan()` called inside `live_scanner.py` | Plan card in scanner | ✅ | Plan is embedded in each setup card JSON |
| ATR-based SL/T1/T2 | §13 | `option_advisor.py` | Rendered in plan card | ✅ | 1.5× ATR SL, 1.5× risk T1, 2.5× risk T2 |
| R:R gate (floor 1.3) | §13 | Hardcoded `_RR_FLOOR = 1.3` | — | ✅ | Returns `None` if below; card shows "No plan" |
| Range-bound sell logic | §13 | `_range_sell_plan()` iv_rank ≥ 40 | — | ✅ | Only if IV rank ≥ 40 |
| IV rank warning | §13 | IV rank thresholds | `iv_note` field | ✅ | Three-tier: none / moderate / expensive |
| Liquidity gate | §13 | `_check_liquidity()` min OI 500, vol 100 | `liquidity_ok` flag | ✅ | Uses real chain when available |

### 1G. Paper Trading Engine

| Feature | Doc § | Backend | Frontend | Wired E2E? | Gap / Notes |
|---------|-------|---------|----------|-----------|-------------|
| Add trade | §14 | `fno.py POST /api/fno/paper-trades` | `/paper-trade` TradeEntryForm + AI advisor | ✅ | Both manual and AI-sourced |
| Close trade | §14 | `fno.py POST /api/fno/paper-trades/{id}/close` | `/paper-trade` Close button | ✅ | Uses `current_price` or falls back to entry |
| Open positions list | §14 | `GET /api/fno/paper-trades/open` | Open tab | ✅ | 30s auto-refresh |
| Closed trades history | §14 | `GET /api/fno/paper-trades/closed` | History tab | ✅ | — |
| Portfolio summary | §14 | `GET /api/fno/paper-trades/portfolio` | Header KPI cards | ✅ | Win rate, profit factor, total P&L, open P&L |
| Equity curve | §14 | `GET /api/fno/paper-trades/equity-curve` | Analytics tab LineChart | ✅ | Requires 2+ closed trades |
| Reset portfolio | §14 | `POST /api/fno/paper-trades/reset` | Reset button | ✅ | Confirm dialog before reset |
| Live P&L for open trades | §14 | `paper_trade_service.get_open_trades()` | `pnl_rs`, `pnl_pct` columns | ⚠️ | `current_price` falls back to `entry_price` — no live option premium feed |

### 1H. Greeks Calculator & Dashboard

| Feature | Doc § | Backend | Frontend | Wired E2E? | Gap / Notes |
|---------|-------|---------|----------|-----------|-------------|
| Black-Scholes Greeks (Δ, Γ, Θ, V, ρ) | §15 | `greeks_calculator.py` (used in options-scanner) | `greeks.ts calculateGreeks()` (client-side for all UI) | ✅ | BS formula correct; RFR = 6.5%; Greeks table, GEX, IV skew, theta decay |
| Greeks per strike table | §16 | Client-side via `buildGreeksRows()` | `/greeks` Greeks Table tab | ✅ | CE / PE side-by-side |
| GEX (Gamma Exposure) chart | §16 | `greeks.ts calculateGex()` | `/greeks` GEX tab | ✅ | Gamma flip reference line |
| IV Skew chart | §16 | Client-side from chain IV | `/greeks` IV Skew tab | ✅ | CE IV vs PE IV by strike |
| Theta Decay curve | §16 | `greeks.ts bsPrice()` | `/greeks` Theta Decay tab | ✅ | DTE 30→0, ATM straddle premium |
| Delta Neutral analysis | §16 | Client-side | `/greeks` Delta Neutral tab | ✅ | Net delta + futures hedge calc |
| Portfolio aggregate Greeks | §16 | **No endpoint `/api/fno/greek-summary`** | **Not implemented** | ❌ | Doc §24 lists this endpoint but it doesn't exist; per-position aggregate Greeks not surfaced anywhere |

### 1I. Strategy Builder

| Feature | Doc § | Backend | Frontend | Wired E2E? | Gap / Notes |
|---------|-------|---------|----------|-----------|-------------|
| Multi-leg builder (up to 6 legs) | §26 | `GET/POST/DELETE /api/fno/strategies` (persistence) | `/strategy-builder` | ✅ | **§26 gap RESOLVED** — fully implemented |
| Payoff diagram (at expiry) | §26 | `strategy.ts calculatePayoff()` | AreaChart with breakeven lines | ✅ | **§26 gap RESOLVED** — works for all strategy types |
| Max profit/loss / breakevens | §26 | `strategy.ts calculateMaxProfitLoss()` | Metric cards | ✅ | "Unlimited" shown for naked strategies |
| Position Greeks | §26 | `strategy.ts calculatePositionGreeks()` | Greeks card | ✅ | Δ, Γ, Θ/day, Vega |
| Strategy templates | §26 | `strategy.ts STRATEGY_TEMPLATES` | Template loader dropdown | ✅ | Pre-built templates (long call, bull spread, iron condor, etc.) |
| Save / load strategies | §25 | `POST /api/fno/strategies` + `GET /api/fno/strategies` | Save section + table | ✅ | Persisted to `storage/data/saved_strategies.json` |
| Symbol limited to indices | §26 | — | Only `INDEX_SYMBOLS` in dropdown | ⚠️ | Equity F&O stocks not selectable |

### 1J. Backtesting Engine

| Feature | Doc § | Backend | Frontend | Wired E2E? | Gap / Notes |
|---------|-------|---------|----------|-----------|-------------|
| Pattern backtest (equity scanner) | §19 | `POST /api/backtests/run` | `/backtest` | ✅ | Win rate, drawdown, equity curve, trade list |
| In-scan mini-backtest | §19 | `_backtest_with_df()` in `live_scanner.py` | Setup card `backtest.hit_rate` | ✅ | 6-month daily, pattern-specific |
| Options backtest (MT strategy) | §19 | `GET /api/options-scanner/backtest` | `/options-scanner` Backtest tab | ✅ | Walk-forward, `options_backtest_mt.py` |

### 1K. Position Sizing & Risk

| Feature | Doc § | Backend | Frontend | Wired E2E? | Gap / Notes |
|---------|-------|---------|----------|-----------|-------------|
| Fixed-fraction sizing | §20 | `POST /api/positions/calc` | `/position-sizing` Single Stock tab | ✅ | Capital × risk% / risk-per-lot |
| Kelly criterion | §20 | `POST /api/positions/kelly` | `/position-sizing` Kelly Criterion tab | ✅ | Half-Kelly applied |
| Position sizing for F&O (lot-aware) | §20 | Both endpoints respect lot_size | Lot size from `getLotSize()` | ✅ | — |

### 1L. PCR Sentiment Page

| Feature | Doc § | Backend | Frontend | Wired E2E? | Gap / Notes |
|---------|-------|---------|----------|-----------|-------------|
| VIX display (current, OHLC, regime) | §6 | `GET /api/fno/vix` | `/pcr-sentiment` | ✅ | Regime card + zone reference table |
| OI flow classification | §7 | `GET /api/fno/oi-spurts` + client-side classify | `/pcr-sentiment` OIFlowSection | ✅ | 4-quadrant flow bar chart |
| **Actual PCR display (PCR_OI, PCR_Vol)** | §6 | `GET /api/fno/pcr` exists | **Not called on this page** | ❌ | **P0 bug** — page has info notice saying "PCR requires NSE option chain data — showing OI flow instead." The `/api/fno/pcr` endpoint works and is called on fo-dashboard, but NOT on the PCR sentiment page. Page content doesn't match its title. |
| Historical PCR chart | §6 | No endpoint exposed | **Missing** | ❌ | 60-day history stored in `fno_history.json` via `append_daily_fno_snapshot()` but no `/api/fno/history` route exists |

### 1M. OI Analytics Page

| Feature | Doc § | Backend | Frontend | Wired E2E? | Gap / Notes |
|---------|-------|---------|----------|-----------|-------------|
| CE/PE OI by strike chart | §7 | `GET /api/fno/option-chain` | `/oi-analytics` | ✅ | ±15 strikes around ATM |
| OI Change by strike chart | §7 | Same chain | `/oi-analytics` | ✅ | CE vs PE change bars |
| OI buildup classification table | §7 | `GET /api/fno/oi-spurts` → client-side classify | `/oi-analytics` | ✅ | Long Buildup / Short Buildup / Short Covering / Long Unwinding |
| `GET /api/fno/oi-variations` | §7 | Backend endpoint exists | **Never called** | ❌ | Dead endpoint. Frontend classifies entirely client-side from oi-spurts. Endpoint documented in §24 but unused. |

### 1N. F&O Dashboard

| Feature | Doc § | Backend | Frontend | Wired E2E? | Gap / Notes |
|---------|-------|---------|----------|-----------|-------------|
| India VIX card + zone reference | §8, §22 | `GET /api/fno/vix` | `/fo-dashboard` | ✅ | 60s refresh |
| Index Futures cards (4) | §5, §22 | `GET /api/fno/index-futures` | `/fo-dashboard` | ✅ | 30s refresh; synthetic badge when fallback |
| PCR (NIFTY, BANKNIFTY, FINNIFTY) | §6, §22 | `GET /api/fno/pcr` × 3 | `/fo-dashboard` | ✅ | 60s refresh; sentiment badge |
| OI Spurts top 10 | §7, §22 | `GET /api/fno/oi-spurts` | `/fo-dashboard` | ✅ | 60s refresh |
| F&O Watchlist quote strip | §22 | **No `/api/fno/watchlist` endpoint** | **Missing** | ❌ | Documented in §22 and §24 but backend CRUD not implemented |

### 1O. F&O Education Page

| Feature | Doc § | Backend | Frontend | Wired E2E? | Gap / Notes |
|---------|-------|---------|----------|-----------|-------------|
| Options basics, Greeks, strategies | §23 | Static | `/fo-learn` | ✅ | Static content, no API calls needed |
| Contextual links from advanced pages | §23 | — | **Missing** | ❌ | No pages link to `/fo-learn`; education page not linked from option chain, greeks, or scanner pages |

### 1P. Navigation & Routing

| Page | In FO_NAV (sidebar) | In FO_PREFIXES (auto-switch) | Accessible | Gap |
|------|--------------------|-----------------------------|-----------|-----|
| `/live-scanner` | ✅ | ✅ | ✅ | — |
| `/option-chain` | ✅ | ✅ | ✅ | — |
| `/paper-trade` | ✅ | ✅ | ✅ | — |
| `/fo-learn` | ✅ | ✅ | ✅ | — |
| `/fo-dashboard` | ❌ | ✅ | ⚠️ direct URL only | Orphan from nav |
| `/greeks` | ❌ | ✅ | ⚠️ direct URL only | Orphan from nav |
| `/oi-analytics` | ❌ | ✅ | ⚠️ direct URL only | Orphan from nav |
| `/fo-scanner` | ❌ | ✅ | ⚠️ direct URL only | Orphan from nav |
| `/options-scanner` | ❌ | ✅ | ⚠️ direct URL only | Orphan from nav |
| `/fo-ai-advisor` | ❌ | ✅ | ⚠️ direct URL only | Orphan from nav |
| `/strategy-builder` | ❌ | ✅ | ⚠️ direct URL only | Orphan from nav |
| `/pcr-sentiment` | ❌ | ❌ | ❌ completely orphaned | Not in nav AND not in FO_PREFIXES |
| `/expiry-heatmap` | ❌ | ❌ | ❌ completely orphaned | Not in nav AND not in FO_PREFIXES |

### 1Q. Section 24 API Reference Accuracy

| Documented endpoint | Actually exists? | Notes |
|--------------------|-----------------|-------|
| `GET /api/fno/option-chain` | ✅ | — |
| `GET /api/fno/index-futures` | ✅ | — |
| `GET /api/fno/underlying-quotes` | ❌ | Not implemented |
| `GET /api/fno/greek-summary` | ❌ | Not implemented; Greeks are client-side |
| `GET /api/fno/pcr` | ✅ | — |
| `GET /api/fno/vix` | ✅ | — |
| `GET /api/fno/oi-spurts` | ✅ | — |
| `GET /api/fno/oi-variations` | ✅ | But never called from frontend |
| `GET /api/fno/history` | ❌ | Data written, no route to read |
| `GET /api/fno/watchlist` | ❌ | Not implemented |
| `POST /api/fno/watchlist` | ❌ | Not implemented |
| `DELETE /api/fno/watchlist/{symbol}` | ❌ | Not implemented |
| `GET /api/fno/strategies` | ✅ | — |
| `POST /api/fno/strategies` | ✅ | — |
| `DELETE /api/fno/strategies/{name}` | ✅ | — |
| `GET /api/live-scanner/scan` | ✅ | — |
| `GET /api/live-scanner/scan/stream` | ✅ | — |
| `GET /api/options-scanner/scan` | ✅ | — |
| `POST /api/positions/calc` | ✅ | — |
| `POST /api/positions/kelly` | ✅ | — |
| `POST /api/backtests/run` | ✅ | — |
| **Undocumented but exist** | | |
| `GET /api/fno/symbols` | ✅ | Used by multiple pages |
| `GET /api/fno/scan` | ✅ | OI-based scanner; fo-scanner page uses client-side instead |
| `GET /api/fno/index-prices` | ✅ | Feeds fo-dashboard fallback |
| `GET /api/fno/ai-suggest` | ✅ | Used by fo-ai-advisor |
| `GET/POST/POST /api/fno/paper-trades/*` | ✅ (7 endpoints) | — |
| `GET /api/options-scanner/deep-dive` | ✅ | — |
| `GET /api/options-scanner/market-context` | ✅ | — |
| `GET /api/options-scanner/backtest` | ✅ | — |
| `GET /api/live-scanner/chart-data` | ✅ | — |
| `GET /api/live-scanner/universe` | ✅ | — |
| `GET /api/live-scanner/health` | ✅ | — |

### 1R. Section 26 Known Gaps — Current Status

| Gap (from §26) | Current Status |
|---------------|---------------|
| Max-pain not computed | ✅ **RESOLVED** — `calculateMaxPain()` in `greeks.ts` + `greeks_calculator.py`; shown in expiry heatmap and deep-dive |
| Multi-leg payoff not implemented (iron condor/calendar) | ✅ **RESOLVED** — `strategy.ts` has `calculatePayoff()`, payoff diagram, greeks, breakevens, margin estimate for all multi-leg strategies |
| No alerts / push notifications | ❌ **Still missing** |
| Missing YF tickers (TATAMOTORS, ZOMATO) | ❌ **Still missing** — commented out in `fno_data_service.py` and `option_advisor.py` |
| Missing YF tickers (MIDCPNIFTY, BANKEX) | ❌ **Still missing** — `_INDEX_MAP` in `intraday_data.py` explicitly omits them |
| Strategy-builder backend (multi-leg payoff) | ✅ **RESOLVED** — backend `/api/fno/strategies` CRUD exists; payoff is correctly client-side |
| Historical PCR chart | ❌ **Still missing** — data written to JSON but no API endpoint |
| Screener.in scraping may break | ❓ No circuit-breaker tests possible without live run |

---

## 2. Prioritized Gap List

### P0 — Broken: Feature exists and is claimed to work but gives wrong results or is unreachable

| ID | Issue | Files affected |
|----|-------|---------------|
| **P0-1** | `/pcr-sentiment` page title says "PCR & Sentiment" but **never calls `/api/fno/pcr`**. It shows VIX + OI flow instead, with an info notice saying PCR requires NSE data. The page content does not match its name or what the doc describes. `/api/fno/pcr` works fine on the fo-dashboard. | `frontend/app/pcr-sentiment/page.tsx` |
| **P0-2** | `/pcr-sentiment` and `/expiry-heatmap` are **completely orphaned** — not in `FO_NAV` and not in `FO_PREFIXES`. Users visiting these URLs won't even get the F&O sidebar. No user can find these pages without knowing the URL. | `frontend/components/layout/sidebar.tsx` |
| **P0-3** | **9 of 13 F&O pages are hidden** from the sidebar nav. `FO_NAV` only contains 4 items (live-scanner, option-chain, paper-trade, fo-learn). The fo-dashboard, greeks, oi-analytics, fo-scanner, options-scanner, fo-ai-advisor, strategy-builder are accessible only via direct URL. | `frontend/components/layout/sidebar.tsx` |

### P1 — Missing Parity: Documented feature with no working implementation

| ID | Issue | Files affected |
|----|-------|---------------|
| **P1-1** | **Historical PCR + VIX chart** — `append_daily_fno_snapshot()` writes 60-day PCR/VIX history to `fno_history.json` daily. No `/api/fno/history` endpoint exists to read it. The PCR sentiment page has no chart. | `backend/routers/fno.py`, `services/fno_data_service.py` |
| **P1-2** | **F&O Watchlist CRUD** — `get_fno_watchlist()` and `save_fno_watchlist()` exist in `fno_data_service.py`. No API endpoints. No frontend UI. F&O dashboard "watchlist quote strip" described in §22 is missing. | `backend/routers/fno.py`, `services/fno_data_service.py` |
| **P1-3** | **`GET /api/fno/oi-variations` dead endpoint** — exists in router, but no frontend page calls it. OI Analytics derives buildup classification entirely client-side from `/api/fno/oi-spurts`. Either the endpoint should be removed or the frontend should use it (it classifies more categories using NSE's own breakdown). | `frontend/lib/fno-api.ts`, `backend/routers/fno.py` |
| **P1-4** | **Portfolio aggregate Greeks** — doc §16 describes a `GET /api/fno/greek-summary` endpoint for net portfolio delta/gamma/theta/vega. Endpoint does not exist. Individual strike Greeks work fine on `/greeks` but there's no portfolio-level aggregate view. | `backend/routers/fno.py` |
| **P1-5** | **Paper trade live P&L**: `current_price` in open positions falls back to `entry_price` when no live feed is available. P&L shows ₹0 for all open trades until closed. Users can't track mark-to-market. | `services/paper_trade_service.py`, `frontend/app/paper-trade/page.tsx` |
| **P1-6** | **Strategy builder limited to index symbols only** — the symbol dropdown only shows `INDEX_SYMBOLS`. Equity F&O stocks (RELIANCE, TCS, etc.) cannot be added to strategies even though their option chains are fully supported. | `frontend/app/strategy-builder/page.tsx` |
| **P1-7** | **`/api/fno/underlying-quotes`** documented in §24 but never implemented. Related: fo-dashboard described as showing a "F&O watchlist quote strip" which also doesn't exist. | `backend/routers/fno.py` |

### P2 — Polish / UX: Works but rough edges

| ID | Issue | Files affected |
|----|-------|---------------|
| **P2-1** | **Section 24 API reference** in `PRODUCT_ANALYSIS_FNO.md` is substantially inaccurate — 6 documented endpoints don't exist, 13+ real endpoints are undocumented. Should be regenerated from code. | `PRODUCT_ANALYSIS_FNO.md` |
| **P2-2** | **`/api/fno/scan` vs client-side fo-scanner** — backend has an OI-based scan endpoint (`/api/fno/scan`) and the frontend fo-scanner has its own client-side implementation (`runFoScan()` in fno-api.ts). Two parallel implementations; neither uses the other. The client-side version requires fetching option chains per symbol which is slow; the server-side version is faster but limited to OI spurts data. Should be unified. | `frontend/app/fo-scanner/page.tsx`, `frontend/lib/fno-api.ts`, `backend/routers/fno.py` |
| **P2-3** | **`/pcr-sentiment` not in `FO_PREFIXES`** — even after nav is fixed, visiting this URL won't auto-switch the sidebar to F&O mode. | `frontend/components/layout/sidebar.tsx` |
| **P2-4** | **`/expiry-heatmap` not in `FO_PREFIXES`** — same issue as P2-3. | `frontend/components/layout/sidebar.tsx` |
| **P2-5** | **No contextual links from advanced pages to `/fo-learn`** — education page exists but is isolated. Greek terminology (Delta, PCR, IV rank) appears throughout without links to the education page. | Multiple frontend pages |
| **P2-6** | **NSE rate-limit error messages** are generic "Failed to load" text. No guidance on what to do (retry in X minutes, market hours restriction, etc.). | Expiry heatmap, greeks, OI analytics pages |
| **P2-7** | **F&O watchlist** (P1-2) also means the FO_NAV "fo-dashboard" entry doesn't show a watchlist — fo-dashboard exists and works but watchlist strip is missing, reducing its utility. | `frontend/app/fo-dashboard/page.tsx` |
| **P2-8** | **Paper trade close uses entry price as exit price** — when closing a position, `handleClose` uses `trade.current_price || trade.entry_price`. Since current_price = entry_price (P1-5), the P&L is always ₹0 unless the user manually edits the exit price. An exit price input dialog should appear. | `frontend/app/paper-trade/page.tsx` |
| **P2-9** | **Mobile/responsive pass needed** — option chain, expiry heatmap, and greeks table have `min-w-[900px]` / `min-w-[560px]` constraints that overflow on mobile without `overflow-x-auto` parents being consistently applied. | `/option-chain`, `/greeks`, `/expiry-heatmap` pages |
| **P2-10** | **Jargon tooltips missing** — terms like "PCR", "OI Buildup", "IV rank", "Confluence Score", "Basis", "Max Pain" appear without any tooltip or help text. | Throughout F&O pages |

---

## 3. Summary Statistics

| Category | Count |
|----------|-------|
| Total F&O pages audited | 13 |
| Pages reachable from sidebar (F&O mode) | 4 |
| Pages completely orphaned (no nav + no FO_PREFIXES) | 2 |
| Pages in FO_PREFIXES but not in nav | 7 |
| Backend endpoints documented but missing | 6 |
| Backend endpoints existing but undocumented | 13 |
| P0 items (broken/unreachable) | 3 |
| P1 items (missing parity) | 7 |
| P2 items (polish) | 10 |
| §26 gaps now resolved | 4 (max pain, multi-leg payoff, strategy backend, strategy templates) |
| §26 gaps still open | 4 (alerts, TATAMOTORS/ZOMATO tickers, MIDCPNIFTY/BANKEX tickers, historical PCR chart) |

---

## 4. Recommended Fix Order

1. **P0-2 + P0-3**: Expand `FO_NAV` in sidebar.tsx to include all F&O pages, and add `/pcr-sentiment` + `/expiry-heatmap` to `FO_PREFIXES`. (~20 lines, zero risk)
2. **P0-1**: Wire `/pcr-sentiment` to call `GET /api/fno/pcr` for NIFTY and BANKNIFTY and render actual PCR cards, alongside the existing VIX + OI flow. (~50 lines)
3. **P1-1**: Add `GET /api/fno/history` endpoint to expose `fno_history.json`; render 60-day PCR + VIX sparkline on `/pcr-sentiment`. (~30 lines backend + chart component)
4. **P1-5 + P2-8**: Improve paper trade close flow — show exit price input; fetch live LTP from option chain for open positions. (~60 lines)
5. **P1-2**: Add `GET/POST/DELETE /api/fno/watchlist` endpoints; render watchlist quote strip on fo-dashboard. (~40 lines backend, ~80 lines frontend)
6. **P1-6**: Add equity F&O symbols to strategy builder symbol selector. (~5 lines)
7. **P2-3 + P2-4**: Add missing FO_PREFIXES entries. (~2 lines)
8. **P2-5**: Add "Learn more →" links on PCR, Greeks, OI Analytics pages. (~10 lines)
9. **P2-6**: Improve NSE error messages with context-specific guidance. (~15 lines)
10. **P1-3**: Either call `/api/fno/oi-variations` in OI Analytics or remove the dead endpoint. (~10 lines)
