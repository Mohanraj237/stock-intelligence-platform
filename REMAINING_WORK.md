# Remaining Work — Post Phase 3

Items still open after Phase 3 completion. All Phase 2 and Phase 3 workstreams are closed
(or delivered as design docs pending sign-off).

---

## Alerts Engine — Awaiting Sign-Off

**Status:** Design document written (`ALERTS_DESIGN.md`).  
**Requires:** Sign-off on rule types, SSE delivery model, and v2 Telegram scope.  
**Effort estimate:** ~20 hours for v1 (in-app SSE only).

**Key decisions needed:**
1. Are the 5 v1 rule types correct? (scanner_score, paper_trade_sl/tp, vix_threshold, pcr_threshold)
2. 60-second poll interval acceptable, or should it be configurable per rule?
3. Include Telegram v2 in next phase scope?

---

## Playwright E2E Tests — Need Next.js Server Running

**Status:** Tests written (`frontend/tests/e2e/mobile-380.test.ts`).  
**How to run:**
```bash
# Option A: auto-starts dev server
cd frontend && pnpm exec playwright test --project=mobile-380

# Option B: run dev server first, then tests
cd frontend && pnpm dev &
make test-playwright
```
**Note:** Playwright tests are NOT included in `make test` (which runs unit tests only).
Run separately when doing a mobile regression check.

---

## Historical F&O Data — Deferred

NSE ban list, participant-wise OI (FII/DII/Retail OI breakdown), and contract rollover data
are not fetched. These require either:
- NSE's Bhav Copy downloads (CSV, daily batch)
- A paid data vendor for historical F&O OI series

Out of scope for this research-tool architecture.

---

## P2-9 — Full Mobile Responsive Deep Pass

The audit confirmed `overflow-x-auto` wrappers on all data tables. The Greeks tab nav was
made scrollable in Phase 3. A deeper mobile pass (collapsible columns, responsive stacked
cards) would improve usability but is not blocking any feature.

Playwright tests at 380px cover the structural correctness (no overflow, controls visible).
UX refinements (e.g. hiding non-essential columns on mobile) are incremental work.

---

## Screener.in Scraper Stability

The fundamentals scraper uses HTML parsing that may break if Screener.in changes its HTML
structure. A circuit-breaker prevents cascading failures. No permanent fix without either:
- An official Screener.in API (not currently available)
- Migration to an alternative fundamentals source

---

*Phase 3 completed: 2026-06-09*  
*Total tests: 145 backend (pytest) + 32 frontend Vitest + 9 Playwright e2e*  
*All workstreams from REMAINING_WORK.md closed or delivered as design docs.*
