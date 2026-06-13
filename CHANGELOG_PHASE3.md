# Phase 3 Changelog

All changes map to workstream IDs from `REMAINING_WORK.md`.
Format: `fix(WS-N): description` — matches commit message convention.

---

## WS-1 — P2-2 Scanner Unification

### fix(WS-1): route OI scan types to backend, unlock chain scan types

**Gap:** Two parallel scanner implementations existed. `runFoScan()` in `fno-api.ts` had
client-side logic for High OI Buildup and Unusual Volume (same as the backend `/api/fno/scan`).
Chain-derived scan types (PCR Extremes, Max Pain Divergence, IV Crush Candidates) were locked
with a "requires option chain" tooltip and unreachable.

**What changed:**

`frontend/lib/fno-api.ts`:
- Removed "High OI Buildup" and "Unusual Volume" switch cases from `_scanSymbol()`.
- `runFoScan()` now throws if called with an OI-data type (guards against accidental misuse).
- Exported `CHAIN_SCAN_TYPES` and `BACKEND_SCAN_TYPES` constants for routing logic in the page.

`frontend/app/fo-scanner/page.tsx`:
- Added `CHAIN_SCAN_TYPES` (PCR Extremes, Max Pain Divergence, IV Crush Candidates) as unlocked,
  active scan types.
- Chain types call `runFoScan()` with `CHAIN_SCAN_UNIVERSE` (INDEX_SYMBOLS + 10 liquid equities).
- OI types still call `GET /api/fno/scan` (unchanged from Phase 2).
- UI now shows two labelled groups: "OI Data Scans · NSE" and "Option Chain Scans · Chain".
- Gamma Squeeze and Roll Activity remain locked (no implementation exists).
- `CHAIN_SCAN_UNIVERSE` is const-exported so tests can verify its contents.

**Tests added:** `frontend/tests/scanner-routing.test.ts` — 8 tests:
- BACKEND_SCAN_TYPES / CHAIN_SCAN_TYPES contain the correct types and are disjoint.
- `runFoScan()` throws (with `/backend/` in message) for all three OI types.

---

## WS-2 — Dedicated Max-Pain Endpoint

### fix(WS-2): add GET /api/fno/max-pain

**Gap:** Max pain was computed inline in the expiry heatmap (frontend) and options-scanner
deep-dive (backend). No standalone endpoint existed. §26 doc noted max pain "not computed as
a separate API field."

**What changed:**

`backend/routers/fno.py`:
- Added `GET /api/fno/max-pain?symbol=X&expiry=Y`.
- Reuses `calculate_max_pain()` from `services/greeks_calculator.py` — no math duplication.
- Falls back to synthetic chain when NSE unavailable.
- Returns `{symbol, expiry, max_pain, spot, distance_pct, synthetic}`.
- Explicitly casts `calculate_max_pain()` result to `float()` to avoid numpy.int64 Pydantic
  serialization error.

`PRODUCT_ANALYSIS_FNO.md §24`: New endpoint added to API reference.

**Tests added:** `tests/test_phase3.py::TestMaxPain` — 5 tests: 200 status, schema, positive
float, distance_pct ≥ 0, known-input sanity check (max_pain within ±20% of spot).

---

## WS-3 — Mobile Responsive Pass

### fix(WS-3): greeks tab nav scrollable on mobile + Playwright setup

**Gap:** P2-9 (mobile audit) confirmed `overflow-x-auto` on all min-width tables. The remaining
issue was the Greeks page tab bar which could overflow on narrow viewports.

**What changed:**

`frontend/app/greeks/page.tsx`:
- Tab nav now has `overflow-x-auto scrollbar-none shrink-0` on each tab to prevent overflow.
- Added `role="tablist"` and `aria-selected` for accessibility (also enables Playwright selector).

`frontend/playwright.config.ts` *(new)*:
- Playwright config with `mobile-380` project (380×812 viewport).
- `webServer` block auto-starts Next.js dev server on port 3001.

`frontend/tests/e2e/mobile-380.test.ts` *(new)*:
- 9 Playwright tests across 3 pages at 380px:
  - `/option-chain`: no overflow, heading visible, table/skeleton visible.
  - `/greeks`: no overflow, tablist accessible, symbol selector not clipped.
  - `/expiry-heatmap`: no overflow, header visible, `overflow-x-auto` container within viewport.

`frontend/package.json`:
- Added `"@playwright/test": "1.49.1"` to devDependencies.
- Added `test:e2e` and `test:e2e:ui` scripts.

`Makefile`:
- Added `make test-playwright` target.
- `make test` still runs backend + frontend unit tests only (not Playwright, since Playwright
  requires a running Next.js server).

`frontend/vitest.config.ts`:
- Added `exclude: ["tests/e2e/**"]` so Playwright tests don't accidentally run under Vitest.

**To run Playwright tests:**
```bash
# Start dev server first (or let Playwright start it automatically)
make test-playwright
# or: cd frontend && pnpm exec playwright test --project=mobile-380
```

---

## WS-4 — Yahoo Finance Ticker Fixes

### fix(WS-4): re-enable TATAMOTORS, ETERNAL, MIDCPNIFTY, BANKEX in live scanner

**Gap:** Four symbols were excluded from the live scanner due to broken/missing Yahoo Finance
tickers. Agent verification on 2026-06-09 found all four now have working tickers.

| Symbol | Old ticker | New/correct ticker | Notes |
|--------|-----------|-------------------|-------|
| TATAMOTORS | TATAMOTORS.NS (404) | TMCV.NS | Tata Motors YF symbol changed |
| ZOMATO → ETERNAL | ZOMATO.NS (404) | ETERNAL.NS | Company renamed Eternal Ltd Feb 2025 |
| MIDCPNIFTY | (missing) | NIFTY_MID_SELECT.NS | Now available on YF |
| BANKEX | (missing) | BSE-BANK.BO | BSE index, available via .BO suffix |

**Files changed:**

`services/intraday_data.py`:
- Extended `_INDEX_MAP` to include `MIDCPNIFTY → NIFTY_MID_SELECT.NS` and `BANKEX → BSE-BANK.BO`.
- Added `_EQUITY_TICKER_OVERRIDE` dict for non-standard equity tickers.
- Updated `_ticker()` to check both `_INDEX_MAP` and `_EQUITY_TICKER_OVERRIDE` before defaulting to `{SYM}.NS`.
- `_ALL_INDICES` now includes MIDCPNIFTY and BANKEX.
- `_ALL_FNO_EQUITY` now includes TATAMOTORS (re-enabled) and ETERNAL (new, replaces ZOMATO).

`services/fno_data_service.py`:
- `LOT_SIZES`: added TATAMOTORS (1425) and ETERNAL (4500); removed ZOMATO comment.

`services/option_advisor.py`:
- `LOT_SIZES`: replaced ZOMATO: 2062 with ETERNAL: 4500.

**Tests added:** `tests/test_phase3.py::TestYFTickerFixes` — 11 tests:
- Each ticker resolves to the correct YF symbol.
- Standard equities still use `{SYM}.NS`.
- TATAMOTORS, ETERNAL in `_ALL_FNO_EQUITY`; MIDCPNIFTY, BANKEX in `_ALL_INDICES`.
- ETERNAL has a lot_size entry.

---

## WS-5 — Historical IV per Symbol → True IV Rank

### fix(WS-5): daily ATM IV snapshot + true IV Rank with VIX fallback

**Gap:** §26 noted "no historical IV series stored per symbol; IV rank uses India VIX as a
proxy." Portfolio Greeks summary used VIX/100 as IV for all positions.

**What changed:**

`services/fno_data_service.py`:
- Added `_IV_HISTORY_PATH = storage/data/iv_history.json`.
- Added `get_iv_history()` — reads `{symbol: [{date, atm_iv, synthetic}, ...]}`.
- Added `append_daily_iv_snapshot()` — fetches ATM IV (avg of CE IV + PE IV at ATM strike,
  nearest expiry) for all watchlist + INDEX_SYMBOLS. Idempotent: does not double-write same day.
  Retains up to 260 entries per symbol (~1 year). Falls back to synthetic chain if NSE unavailable.
- Added `get_iv_rank(symbol)` — computes true IV Rank (percentile in 52-week high/low range).
  Returns `sufficient_history=False` and `iv_rank=None` when < 30 days of history.
- Updated `calculate_portfolio_greeks()` — for each position, tries `get_iv_rank(symbol)` first;
  uses `current_iv / 100` if `sufficient_history=True`, else falls back to VIX/100. Per-position
  `iv_source` field shows "IV history" or "VIX proxy". Portfolio summary includes `iv_source` label.

`backend/routers/fno.py`:
- Added `GET /api/fno/iv-rank?symbol=X` — returns IV rank for one symbol.
- Added `POST /api/fno/iv-snapshot` — manual trigger for daily snapshot (for testing and admin).

**Tests added:** `tests/test_phase3.py::TestIVRank` — 8 tests:
- IV rank = 100 when current is 52w high.
- IV rank = 0 when current is 52w low.
- IV rank = 50 at midpoint.
- `iv_rank = None` when insufficient history (< 30 days).
- Empty symbol returns `sufficient_history=False`.
- `/api/fno/iv-snapshot` endpoint returns 200 + list.
- `/api/fno/iv-rank` endpoint returns 200 + schema.
- `append_daily_iv_snapshot()` is idempotent (no double-write on same day).

---

## WS-6 — Alerts Engine Design

**Deliverable:** `ALERTS_DESIGN.md` — architecture doc covering:
- 5 rule types (scanner_score, paper_trade_sl/tp, vix_threshold, pcr_threshold).
- In-app SSE delivery (reuses existing SSE infra from live scanner).
- JSON storage schema for rules and events.
- Full API surface (7 endpoints).
- Effort estimate (~20h for v1).
- v2 Telegram option flagged for sign-off.

**Status:** Design only — awaiting sign-off before implementation.

---

## Test Suite Summary (Phase 3 additions)

| Suite | New tests | Total (all phases) |
|-------|----------|-------------------|
| Backend (pytest) | +31 | 145 |
| Frontend Vitest | +8 | 32 |
| Frontend Playwright (e2e) | +9 | 9 (separate runner) |

**Run all unit tests (deterministic, no server needed):**
```bash
make test
# or:
python -m pytest tests/ -v --tb=short
cd frontend && pnpm exec vitest run --reporter verbose
```

**Run Playwright e2e tests (requires Next.js server on :3001):**
```bash
make test-playwright
# or: cd frontend && pnpm exec playwright test --project=mobile-380
```
