# Phase 2 Changelog

All changes in this file map 1-to-1 to gap IDs from `AUDIT_REPORT.md`.
Format: `fix(GAP-ID): description` — matches commit message convention.

---

## Workstream A — Navigation & Reachability

### fix(P0-2, P2-3, P2-4): add /pcr-sentiment and /expiry-heatmap to FO_PREFIXES

**Gap:** `/pcr-sentiment` and `/expiry-heatmap` were not in `FO_PREFIXES`, so visiting
them directly did not auto-switch the sidebar to F&O mode. They were also missing from
`FO_NAV`, meaning users had no way to find them from any nav link.

**Files changed:**
- `frontend/lib/nav-config.ts` *(new)* — extracted `FO_PREFIXES` constant (now includes
  `/pcr-sentiment` and `/expiry-heatmap`) and `FO_NAV_ROUTES` / `FO_BACK_ROUTES`
  for testability.
- `frontend/components/layout/sidebar.tsx` — imports `FO_PREFIXES` / `FO_NAV_ROUTES` /
  `FO_BACK_ROUTES` from `nav-config.ts`; builds `FO_NAV` from the route array + icon map.

**Test added:** `frontend/tests/nav.test.ts` — asserts `/pcr-sentiment` and
`/expiry-heatmap` appear in both `FO_PREFIXES` and `FO_NAV_ROUTES`.

---

### fix(P0-3): expand F&O sidebar nav to all 13 pages

**Gap:** `FO_NAV` only contained 4 items (live-scanner, option-chain, paper-trade,
fo-learn). Nine pages — fo-dashboard, greeks, oi-analytics, fo-scanner, options-scanner,
fo-ai-advisor, strategy-builder, pcr-sentiment, expiry-heatmap — were orphans reachable
only via direct URL.

**What changed:** `FO_NAV` now contains all 13 F&O pages grouped into 5 sections:
- **Market**: F&O Overview (`/fo-dashboard`), PCR & Sentiment (`/pcr-sentiment`)
- **Scanners**: Live Scanner, F&O Scanner, Options Scanner, AI Advisor
- **Options**: Option Chain, Expiry Heatmap, Greeks, OI Analytics, Strategy Builder
- **Risk**: Paper Trade
- **Learn**: Learn F&O
Plus the existing Back to Equity / Settings utility links at the bottom.

**Files changed:**
- `frontend/lib/nav-config.ts` *(new)* — `FO_NAV_ROUTES` defines all 13 routes with
  group membership; sidebar adds icons via `FO_ICON_MAP`.
- `frontend/components/layout/sidebar.tsx` — `buildFoNav()` constructs `FO_NAV` from
  `FO_NAV_ROUTES` + `FO_BACK_ROUTES` + `FO_ICON_MAP`.

**Icons added to sidebar imports:**
`BarChart2`, `Activity`, `Search`, `Target`, `Cpu`, `CalendarDays`, `TrendingUp`,
`BarChart3`, `Layers` (all from `lucide-react@0.469.0`).

**Test added:** `frontend/tests/nav.test.ts` — 10 assertions across 3 describe blocks:
- `FO_NAV_ROUTES` contains all 13 required hrefs, has no duplicates, valid groups.
- `FO_PREFIXES` contains all 13 hrefs; every nav route is in `FO_PREFIXES`.
- Back routes are present and correctly NOT in `FO_PREFIXES`.

**Test infrastructure added:**
- `vitest@2.1.8` added to `frontend/devDependencies` (via pnpm).
- `frontend/vitest.config.ts` — `environment: "node"`, resolves `@` alias.
- `frontend/package.json` — added `"test"` and `"test:watch"` scripts.
- Root `Makefile` — `make test` runs both backend (pytest) and frontend (vitest).
- Root `Makefile` — `make test-backend` / `make test-frontend` for individual suites.

---

---

## Workstream B — PCR Sentiment page + Historical chart

### fix(P0-1): wire /pcr-sentiment to GET /api/fno/pcr

**Gap:** The page showed VIX + OI-flow with an info notice "PCR requires NSE option chain data — showing OI flow instead." The `/api/fno/pcr` endpoint was working but never called from this page.

**What changed:**
- `frontend/app/pcr-sentiment/page.tsx` — full rewrite. Added two `useQuery` calls for `getPcr("NIFTY")` and `getPcr("BANKNIFTY")`. Renders `PcrCard` components showing: PCR OI (large), PCR Vol, sentiment badge (Strongly Bullish → Strongly Bearish), CE/PE OI bar, and CE/PE volume. Removed the "PCR unavailable" info notice. PCR error state now shows context-specific retry guidance (NSE rate-limit hours).
- `frontend/lib/fno-utils.ts` *(new)* — `getPcrSentiment(pcr: number)` maps PCR value to `{label, variant}` using spec §6 thresholds (>1.3 Strongly Bullish, 1.0–1.3 Mildly Bullish, 0.7–1.0 Neutral, 0.5–0.7 Mildly Bearish, <0.5 Strongly Bearish).

**Test added:** `frontend/tests/fno-utils.test.ts` — 7 tests covering all 5 PCR threshold tiers, boundary at 1.3, and distinctness of all labels.

---

### fix(P1-1): add GET /api/fno/history + 60-day PCR + VIX sparkline

**Gap:** `append_daily_fno_snapshot()` was writing 60-day PCR + VIX history to `fno_history.json` but no API endpoint exposed it. No historical chart existed on any page.

**What changed:**
- `backend/routers/fno.py` — added `GET /api/fno/history` wrapping `fno_data_service.get_fno_history()`.
- `frontend/lib/fno-types.ts` — added `FnoHistoryPcrEntry`, `FnoHistoryVixEntry`, `FnoHistory` interfaces.
- `frontend/lib/fno-api.ts` — added `getFnoHistory()` (falls back to `{pcr:[],vix:[]}` on error).
- `frontend/lib/fno-utils.ts` — added `mergeHistory(pcr, vix)` that joins arrays by date, fills missing values with null, and sorts chronologically.
- `frontend/app/pcr-sentiment/page.tsx` — added `HistoryChart` component rendering a dual-Y-axis Recharts `LineChart` (NIFTY PCR + BankNifty PCR on left axis, India VIX on right axis). Shows "No history yet" empty state when `pcr.length === 0`.

**Tests added:**
- `frontend/tests/fno-utils.test.ts` — 7 tests for `mergeHistory()`: date alignment, null-fills for missing entries, chronological ordering, empty-array safety, duplicate detection.
- `tests/test_fno.py::TestFNOHistory` — 6 backend tests: 200 status, `{pcr,vix}` schema, ≤60 entries, per-entry field presence, ISO-8601 date format.

---

## Workstream C — Paper Trade live P&L + exit-price dialog

### fix(P1-5): live LTP refresh for open paper positions

**Gap:** `current_price` in open trades fell back to `entry_price` at entry time. P&L showed ₹0 unless the price was manually updated. `update_all_prices()` existed in `paper_trade_service.py` but was never exposed as an API endpoint.

**What changed:**
- `backend/routers/fno.py` — added `POST /api/fno/paper-trades/refresh-prices` wrapping `paper_trade_service.update_all_prices()`. Returns list of `{trade_id, symbol, current_price, pnl_rs, sl_hit, tp_hit}` for successfully updated trades.
- `frontend/lib/fno-types.ts` — added `PriceRefreshResult` interface.
- `frontend/lib/fno-api.ts` — added `refreshPaperTradePrices()` (graceful empty-list fallback on error).
- `frontend/app/paper-trade/page.tsx` — added "Refresh Prices" button (with spinner) that calls `refreshPaperTradePrices()` then invalidates `paper-trades` query. LTP column shows blue text + "entry price" sub-label when live price not yet fetched (so users know the status).

**Test added:** `tests/test_fno.py::TestPaperTrades::test_refresh_prices_returns_list` — asserts 200 + list response.

---

### fix(P2-8): exit-price input dialog for paper trade close

**Gap:** Clicking Close silently used `trade.current_price || trade.entry_price` as exit price. Since current_price = entry_price before refresh, P&L was always ₹0. No user input was requested.

**What changed:**
- `frontend/app/paper-trade/page.tsx` — replaced direct `closeMutation.mutate()` in `handleClose` with `handleRequestClose()` which opens `ExitDialog`. Dialog is pre-filled with `trade.current_price` (live LTP if refreshed, entry price otherwise), allows editing, validates > 0, and calls `handleConfirmClose(tradeId, exitPrice)` which calls `closePaperTrade(id, price)`. Cancel button dismisses without closing.

**Tests added:** `tests/test_fno.py::TestPaperTradePnL` — 5 tests:
- `test_buy_profit_pnl` — BUY: `(exit − entry) × lots × lot_size = +7500`
- `test_buy_loss_pnl` — BUY: `(exit − entry) × lots × lot_size = −4000`
- `test_sell_profit_pnl` — SELL: `(entry − exit) × lots × lot_size = +1800`
- `test_sell_loss_pnl` — SELL: `(entry − exit) × lots × lot_size = −2250`
- `test_close_uses_provided_exit_price` — exact exit price appears verbatim in closed trade record

---

---

## Workstream D — Missing backend endpoints

### fix(P1-2): GET/POST/DELETE /api/fno/watchlist + watchlist quote strip

**Files changed:**
- `services/fno_data_service.py` — added `get_underlying_quotes(symbols)` function
- `backend/routers/fno.py` — added `GET /api/fno/watchlist`, `POST /api/fno/watchlist`, `DELETE /api/fno/watchlist/{symbol}`
- `frontend/lib/fno-api.ts` — added `getFnoWatchlist()`, `addToFnoWatchlist()`, `removeFromFnoWatchlist()`
- `frontend/app/fo-dashboard/page.tsx` — added `WatchlistStrip` component (quote strip with add/remove UI)

**Tests added:** `tests/test_fno.py::TestFNOWatchlist` — 5 tests: GET returns list, POST adds symbol, 400 on missing symbol, DELETE removes symbol, add is idempotent.

---

### fix(P1-7): GET /api/fno/underlying-quotes

**Files changed:**
- `services/fno_data_service.py` — added `get_underlying_quotes(symbols)`: indices from allIndices, equities from `get_fno_stocks()` LTP list; preserves request order.
- `backend/routers/fno.py` — added `GET /api/fno/underlying-quotes?symbols=NIFTY,BANKNIFTY` endpoint.
- `frontend/lib/fno-types.ts` — added `UnderlyingQuote` interface.
- `frontend/lib/fno-api.ts` — added `getUnderlyingQuotes(symbols?)`.

**Tests added:** `tests/test_fno.py::TestUnderlyingQuotes` — 3 tests: returns list, accepts symbols param, required fields present.

---

### fix(P1-4): GET /api/fno/greek-summary — portfolio net Greeks

**Files changed:**
- `services/fno_data_service.py` — added `calculate_portfolio_greeks(open_trades)`: uses `calculate_greeks()` from `greeks_calculator.py` with India VIX / 100 as IV proxy; FUT delta = ±1; aggregates net Δ/Γ/Θ/Vega scaled by lots × lot_size × BUY/SELL sign.
- `backend/routers/fno.py` — added `GET /api/fno/greek-summary`.
- `frontend/lib/fno-api.ts` — added `getGreekSummary()` + `GreekSummary` type.
- `frontend/app/greeks/page.tsx` — added `Portfolio Greeks` card at bottom: net Greeks KPI grid + per-position breakdown table + disclaimer note.

**Tests added:** `tests/test_fno.py::TestGreekSummary` — 3 tests: 200 status, schema, empty portfolio gives zero Greeks.

---

### fix(P1-3): wire OI Analytics to /api/fno/oi-variations (P1-3 decision)

**Decision made:** Keep the backend endpoint AND wire the frontend. When NSE data is available, show a "NSE Variation Data" panel at the bottom of OI Analytics as a supplementary view. When NSE returns empty (rate-limited), the panel is hidden. Client-side classification from oi-spurts remains as the primary, always-reliable source.

**Files changed:**
- `frontend/lib/fno-api.ts` — added `getOiVariations()` + `OIVariationRow` interface.
- `frontend/app/oi-analytics/page.tsx` — added `variationsQuery` + conditional `NSE Variation Data` panel.

---

## Workstream E — Strategy builder equity symbols (P1-6)

**Files changed:**
- `frontend/app/strategy-builder/page.tsx` — added `getFnoSymbols` import + `symbolsQuery` + `allSymbols` memo (INDEX_SYMBOLS + equity F&O stocks sorted). Symbol selector now uses `<optgroup>` with separate Indices / Equity F&O groups.

---

## Workstream F — UX polish

### fix(P2-5): contextual "Learn F&O" links from advanced pages

**Files changed:**
- `frontend/app/pcr-sentiment/page.tsx` — "Learn about PCR →" header link to `/fo-learn#pcr`
- `frontend/app/oi-analytics/page.tsx` — "Learn about OI →" inline link in subtitle
- `frontend/app/greeks/page.tsx` — "Learn about Greeks →" inline link in subtitle

### fix(P2-10): HelpTip tooltip component for jargon

**Files created:**
- `frontend/components/ui/tooltip.tsx` — `HelpTip` component using `@radix-ui/react-tooltip` (already in dependencies). Dotted underline, hover tooltip, accessible via tab+focus.

**HelpTips added to:**
- PCR Sentiment page: "Put-Call Ratio" label
- OI Analytics page: "Open interest" in subtitle (explains Long Buildup / OI definition)
- Live Scanner page: `ScorePill` — explains Confluence Score breakdown (Trend 30 + Momentum 25 + Volume 20 + Candle 25)
- Greeks page: "Black-Scholes Greeks" in subtitle (explains all 5 Greeks)

### fix(P2-6): context-specific NSE error messages

**Files changed:**
- `frontend/app/pcr-sentiment/page.tsx` — PCR error now says "NSE option chain may be rate-limited outside market hours. Try again between 9:15 AM and 3:30 PM IST."

### fix(P2-9): mobile responsive audit

**No code change required** — option-chain, greeks, and expiry-heatmap already had `overflow-x-auto` wrappers around all `min-w-[...]` tables/grids. The audit confirmed this pattern is consistent.

### misc: PageHeader subtitle widened to ReactNode

**Files changed:**
- `frontend/components/common/page-header.tsx` — `subtitle?: string` → `subtitle?: React.ReactNode` to allow inline HelpTips and links.

---

## Workstream G — Documentation

### fix(P2-1): regenerate §24 API reference from actual routers

**Files changed:**
- `PRODUCT_ANALYSIS_FNO.md §24` — regenerated from live router code. Now lists all 27+ real fno endpoints (including Phase 2 additions), 5 live-scanner endpoints, 4 options-scanner endpoints, 2 position-sizing endpoints, 1 backtest endpoint. Each entry tagged v2 or Phase 2.

### fix(§26): reconcile Known Limitations table

**Files changed:**
- `PRODUCT_ANALYSIS_FNO.md §26` — all 12 resolved gaps marked ✅ RESOLVED; 8 remaining open items retained with current status.

### DECISION REQUIRED items documented

**Files created:**
- `REMAINING_WORK.md` — documents P2-2 (scanner unification) with full recommendation; alerts engine deferral; missing YF tickers as data dependency; historical IV gap; max-pain standalone endpoint note.

---

## Test Suite Summary

| Suite | Tests | Command |
|-------|-------|---------|
| Frontend (Vitest) | 24 | `cd frontend && pnpm exec vitest run` |
| Backend (pytest) | 47 | `python -m pytest tests/test_fno.py` |
| **Total** | **71** | `make test` |

Per-gap test coverage:

| Gap ID | Test location | Tests |
|--------|---------------|-------|
| P0-2, P0-3, P2-3, P2-4 | `frontend/tests/nav.test.ts` | 10 |
| P0-1, P1-1 | `frontend/tests/fno-utils.test.ts` | 14 |
| P1-1 | `tests/test_fno.py::TestFNOHistory` | 6 |
| P1-2 | `tests/test_fno.py::TestFNOWatchlist` | 5 |
| P1-3 | (structural — tested via oi-variations endpoint) | — |
| P1-4 | `tests/test_fno.py::TestGreekSummary` | 3 |
| P1-5, P2-8 | `tests/test_fno.py::TestPaperTradePnL` | 5 |
| P1-5 | `tests/test_fno.py::TestPaperTrades::test_refresh_prices_returns_list` | 1 |
| P1-7 | `tests/test_fno.py::TestUnderlyingQuotes` | 3 |
