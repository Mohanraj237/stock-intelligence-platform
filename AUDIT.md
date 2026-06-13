# Phase 0 Audit — Stock Intelligence Platform
**Audited:** 2026-06-06  
**Auditor:** Claude (principal-level quant engineering review)  
**Repo root:** `c:\Users\mohan\Stock App\stock-intelligence-platform\`

---

## 1. Tech Stack — Versions

| Layer | Technology | Version |
|---|---|---|
| Frontend framework | Next.js (App Router) | 15.1.3 |
| UI library | React | 19.0.0 |
| Data fetching | @tanstack/react-query | 5.62.7 |
| Charting | lightweight-charts (TradingView) | 4.2.2 |
| Analytics charts | recharts | 2.15.0 |
| Component primitives | Radix UI (assorted) | 1.x–2.x |
| Styling | Tailwind CSS | 4.0.0 |
| Language (FE) | TypeScript | 5.7.2 |
| Backend framework | FastAPI (Python) | (latest pinned) |
| Python runtime | CPython | 3.12 |
| ASGI server | Uvicorn | (pinned) |
| HTTP client | requests (sync) | — |
| AI model | Anthropic Claude Sonnet 4.6 | claude-sonnet-4-6 |
| Storage | JSON flat files | none |
| Cache | JSON files + TTL logic | none |
| Database | **None** | — |
| Message queue | **None** | — |
| WebSocket server | **None** | — |

---

## 2. Frontend Audit

### 2a. Component Tree (summary)

```
app/
├── layout.tsx              Root: QueryClientProvider + RegionProvider
├── providers.tsx           React Query config (stale=30s, gc=5m, no window-focus refetch)
├── page.tsx                Redirect → /dashboard
│
├── dashboard/              Market overview (indices, sectors, FII/DII, top movers)
├── analyzer/               Deep dive: chart, technicals, fundamentals, AI verdict
├── scanner/                12 scan types, SSE streaming progress
├── patterns/               Pattern detection + backtest lab
├── compare/                Multi-stock overlay
├── backtest/               Historical strategy, equity curve
├── position-sizing/        Kelly / fixed-fraction calculator
├── rules/                  Automated screening rule engine
├── portfolio/              Holdings tracker
├── watchlist/              Symbol watchlist
├── reports/                PDF report generator
├── settings/               App config incl. Anthropic key input
├── learn/                  Educational content
├── universe/               NSE index explorer
├── news/                   RSS-aggregated news
├── earnings/               Earnings calendar
│
├── fo-dashboard/           F&O overview: VIX, index futures, PCR, OI spurts
├── option-chain/           Full chain with Greeks
├── oi-analytics/           OI buildup classification
├── pcr-sentiment/          PCR sentiment dashboard
├── expiry-heatmap/         OI heatmap by strike × expiry
├── strategy-builder/       Multi-leg builder + backtest
├── fo-scanner/             F&O scan: OI buildup, PCR extremes, max pain
├── options-scanner/        MTF buyer scanner (deep-dive, composite score)
├── greeks/                 GEX visualization
├── fo-ai-advisor/          Claude-powered F&O trade suggestions
└── paper-trade/            Virtual trading, P&L, equity curve
```

**Total routes:** 29 pages + 2 API proxy routes.

### 2b. State Management

| Mechanism | Usage | Verdict |
|---|---|---|
| React Query v5 | Primary data layer — 138 useQuery calls across all pages | Keep; upgrade patterns |
| React Context (RegionContext) | India / US toggle, currency formatter, localStorage persist | Keep |
| Local useState | Form inputs, UI toggles, per-page ephemeral state | Keep |
| Zustand | Not present | — |
| Redux | Not present | — |
| Tick store / event bus | **Not present** | Must build |

**React Query global config** (`providers.tsx`):
```ts
staleTime: 30_000          // data fresh for 30s
gcTime: 5 * 60_000         // unused queries evicted at 5m
refetchOnWindowFocus: false
retry: 1
```
The 30-second stale time means all pages silently serve cache for 30 s after every poll cycle. For live prices this is functionally a 30–90 s delay (stale + interval).

### 2c. All Data Fetch Locations

All fetches go through one of two typed wrappers:

| File | Wrapper | Destination |
|---|---|---|
| `lib/api.ts` | `api.*()` methods | `http://127.0.0.1:8000` (FastAPI directly) |
| `lib/fno-api.ts` | `apiGet/apiPost` | Next.js proxy `/api/fno/*` → FastAPI |
| `lib/fno-api.ts` | `faGet/faPost` | **FastAPI directly** (bypasses proxy — see Risk #3) |
| `app/options-scanner/page.tsx` | `fetch("/api/options-scanner/...")` | Next.js proxy → FastAPI |

All fetch calls set `"cache": "no-store"` — correct for data accuracy, but means no HTTP-layer edge caching available.

### 2d. Polling & Refresh Inventory (COMPLETE)

Every `refetchInterval` currently in the codebase:

| Page | Query | Interval | Lines |
|---|---|---|---|
| `/dashboard` | indices | 60 s | `dashboard/page.tsx:14` |
| `/dashboard` | sectors | 120 s | `dashboard/page.tsx:15` |
| `/dashboard` | FII/DII | 300 s | `dashboard/page.tsx:16` |
| `/dashboard` | universe quotes | 60 s | `dashboard/page.tsx:304` |
| `/fo-dashboard` | VIX | 60 s | `fo-dashboard/page.tsx:244` |
| `/fo-dashboard` | index futures | 30 s | `fo-dashboard/page.tsx:251` |
| `/fo-dashboard` | PCR | 60 s | `fo-dashboard/page.tsx:258` |
| `/fo-dashboard` | OI spurts | 60 s | `fo-dashboard/page.tsx:265` |
| `/fo-dashboard` | OI buildup | 60 s | `fo-dashboard/page.tsx:272` |
| `/fo-dashboard` | OI heatmap | 60 s | `fo-dashboard/page.tsx:279` |
| `/option-chain` | chain | 30 s | `option-chain/page.tsx:323` |
| `/greeks` | chain | 60 s | `greeks/page.tsx:648` |
| `/expiry-heatmap` | chain | 60 s | `expiry-heatmap/page.tsx:343` |
| `/oi-analytics` | OI spurts | 60 s | `oi-analytics/page.tsx:232` |
| `/oi-analytics` | OI buildup | 60 s | `oi-analytics/page.tsx:239` |
| `/pcr-sentiment` | PCR | 60 s | `pcr-sentiment/page.tsx:383` |
| `/pcr-sentiment` | heatmap | 60 s | `pcr-sentiment/page.tsx:390` |
| `/paper-trade` | open trades | 30 s | `paper-trade/page.tsx:322` |
| `/paper-trade` | closed trades | 30 s | `paper-trade/page.tsx:328` |
| `/strategy-builder` | chart | 60 s | `strategy-builder/page.tsx:126` |

**setInterval (raw, not React Query):**

| File | What | Interval | Lines |
|---|---|---|---|
| `options-scanner/page.tsx` | `handleScan()` auto-trigger | 15 min (market hours only) | 759–772 |

**setTimeout (toast dismissal only — acceptable):** 6 instances, all 2–5 s, UI-only.

**Conclusion:** The entire real-time layer is HTTP polling. No WebSocket. No push. For India F&O this means option chain prices lag 30–60 s. For the US equity requirement ("stream what's on-screen") this architecture does not work at all.

### 2e. Re-render Risk on High-Frequency Updates

Because every page independently holds its own useQuery and renders all rows on each fetch, introducing a 500-symbol tick feed **today would re-render every row every tick**. There is no:
- Virtualized row list (react-window / tanstack-virtual)
- Selective subscription (only re-render the row whose price changed)
- Atom-level state (Jotai / Zustand slices keyed by symbol)

Any page with a table of symbols (dashboard, scanner, universe) will choke past ~50 simultaneous ticks.

---

## 3. Backend Audit

### 3a. Service Map

```
backend/
├── main.py             FastAPI app, CORS, GZip, logging, startup sync
├── config.py           Pydantic settings (SIP_ prefix env vars)
├── deps.py             run_sync() helper — wraps sync services in ThreadPoolExecutor
│
├── routers/
│   ├── market.py       /api/market — indices, sectors, FII/DII, universe quotes
│   ├── stocks.py       /api/stocks — OHLCV, indicators, fundamentals, AI verdict
│   ├── fno.py          /api/fno — option chain, VIX, PCR, OI, paper trades, strategies
│   ├── options_scanner.py  /api/options-scanner — MTF scanner, deep-dive, backtest
│   ├── patterns.py     /api/patterns — detection, backtest, SSE scan stream
│   ├── scans.py        /api/scans — 12 scan types, SSE stream
│   ├── backtests.py    /api/backtests — strategy backtest, SSE stream
│   ├── news.py         /api/news — market + stock RSS feeds, NSE announcements
│   ├── earnings.py     /api/earnings — upcoming calendar, recent results
│   ├── portfolio.py    /api/portfolio — CRUD on holdings
│   ├── watchlist.py    /api/watchlist — CRUD on symbols
│   ├── rules.py        /api/rules — rule engine CRUD + apply
│   ├── positions.py    /api/positions — Kelly criterion, AI allocation
│   ├── reports.py      /api/reports — PDF generation + list
│   ├── universe.py     /api/universe — index constituents, sync
│   └── settings.py     /api/settings — config CRUD incl. API keys
│
└── services/
    ├── nse_service.py          NSE scraper (session-based, cookie spoofing)
    ├── market_data_service.py  Yahoo Finance OHLCV + quotes (unofficial)
    ├── screener_service.py     Screener.in fundamentals (CSRF + session)
    ├── fno_data_service.py     NSE option chain, VIX, PCR, OI
    ├── fno_ai_service.py       Claude Sonnet 4.6 — F&O recommendations
    ├── news_service.py         RSS feed aggregation (parallel ThreadPool)
    ├── universe_sync.py        NSE Archives CSV download at startup
    ├── us_market_service.py    Yahoo Finance crumb auth, US OHLCV
    ├── us_universe_sync.py     Wikipedia S&P 500 / NASDAQ-100 scrape
    └── various analyzers       Pattern detection, backtest, indicators
```

### 3b. Data Flow (source → storage → client)

```
  NSE India (session/cookie scrape)
  Yahoo Finance (unofficial crumb API)
  Screener.in (CSRF session)
  News RSS feeds
  NSE Archives (CSV)
  Wikipedia (HTML scrape — US index lists)
         │
         ▼  (sync HTTP via requests library)
  services/*.py  →  cache_manager.py  →  storage/cache/*.json
                                             (TTL: 15 min – 24 h)
         │
         ▼  (run_sync() → ThreadPoolExecutor 16 workers)
  FastAPI routers  (async handlers wrapping sync services)
         │
         ▼  (HTTP REST / SSE)
  Next.js frontend  (React Query polling every 30–120 s)
```

**There is no push path.** Data flows exclusively on client request.

### 3c. External APIs — Rate Limits, Auth, ToS

| Source | Auth Model | Rate Limit (documented) | WebSocket? | ToS Note |
|---|---|---|---|---|
| NSE India (`nseindia.com`) | Session cookie + Referer spoof | Aggressive IP-blocking; no published limit | No | **Scraping against NSE ToS. Personal-use only. Not redistribution-safe.** |
| NSE Archives (`archives.nseindia.com`) | None | Low; cached 24 h | No | Same ToS. CSV reference data. |
| Yahoo Finance (unofficial) | Crumb + cookie for v7 | Undocumented; soft ~2000 req/day per IP | No | **Unofficial API. No ToS acceptance. Can break without notice.** |
| Screener.in | CSRF token + session | Unknown | No | Requires manual session token entry in Settings. Brittle. |
| Anthropic Claude API | API key (settings.json) | Pay-as-you-go; no burst limit stated | No | Legitimate. Key stored plaintext. |
| RSS feeds (MC/ET/BS/Mint) | None | Low volume; ~10 feeds | No | Standard RSS — generally permissible. |
| Wikipedia | None (HTML scrape) | Low; cached at sync | No | CC-BY-SA content. Scraping permissible at low volume. |

**No source in the current system provides:**
- True real-time tick streaming for India (NSE is snapshot/scrape)
- WebSocket feed for any market
- A legitimate licensed Indian market data connection

### 3d. Databases, Caches, Message Queues

| Component | Implementation | Status |
|---|---|---|
| Relational DB | None | Absent |
| Time-series DB | None | Absent |
| In-memory cache | None (Redis) | Absent |
| Message queue | None (Redis/Kafka) | Absent |
| File cache | `storage/cache/*.json` (TTL-based) | Present — adequate for snapshots only |
| User data store | `storage/config/*.json` (watchlist, portfolio, rules, settings) | Present — single-user flat file |
| Logs | `storage/logs/backend.log` (rotating 5 MB × 3) | Present |

### 3e. Single Points of Failure & Blocking I/O

1. **All NSE calls are synchronous** (`requests.get()`). Under `run_sync()` they consume one of 16 ThreadPoolExecutor workers per call. Under load, all 16 workers can be held by simultaneous NSE requests (which each take 8–15 s) → total backend stall.

2. **NSE session refresh** (`nse_service.py:51–67`) — one global `requests.Session`. If it expires or is blocked, **every** NSE-sourced endpoint fails simultaneously (indices, option chain, PCR, VIX, OI — everything).

3. **No circuit breaker** on any upstream. A flaky NSE response triggers a slow 15 s timeout on each request, propagating latency directly to the user.

4. **No heartbeat or staleness detection** — if NSE stops responding during market hours the UI keeps showing the last-cached value with no visible "stale" indicator.

5. **No failover** — there is no secondary data source for India equity prices.

6. **Yahoo Finance crumb auth** is a reverse-engineered undocumented mechanism. When Yahoo rotates their auth scheme (has happened twice in 2023–2024) all US market data silently breaks.

7. **`faGet()` bypasses the Next.js proxy** (`lib/fno-api.ts`) — calls go directly from browser to `127.0.0.1:8000`. This exposes the FastAPI server address to the browser and means NSE cookie management (which should be server-side-only) is partially bypassed.

---

## 4. Keep / Refactor / Rip-out Table

| Component | Decision | Reason |
|---|---|---|
| **Next.js 15 App Router** | **Keep** | Correct framework choice; App Router + React 19 is the right foundation. |
| **React Query v5** | **Keep** | Keep for all non-tick data (fundamentals, news, earnings, scans). Remove `refetchInterval` on price queries — replace with WebSocket subscription. |
| **RegionContext (IN/US)** | **Keep** | Lightweight and correct pattern for region toggle. |
| **lightweight-charts (TradingView)** | **Keep** | Best free candlestick library; handles streaming tick updates via `series.update()`. |
| **recharts** | **Keep** | Fine for analytics charts (PCR, OI, P&L curves). Not for live tick data. |
| **Radix UI + Tailwind 4** | **Keep** | Solid accessible component foundation. |
| **FastAPI + Python** | **Keep (refactor internals)** | Good async framework. The router/service split is clean. Internals need async-native HTTP client (httpx) and circuit breakers. |
| **`lib/api.ts` + `lib/fno-api.ts` typed wrappers** | **Refactor** | Correct pattern; eliminate `faGet/faPost` direct-to-FastAPI calls (security + proxy bypass). Add typed error handling. |
| **SSE streaming for scans/backtests** | **Keep** | Correct tool for long-running one-shot operations (scans, backtests). Keep SSE here; add WebSocket separately for tick data. |
| **Claude Sonnet 4.6 AI integration** | **Keep (harden)** | Good model choice. Needs: server-side key never in settings.json plaintext; prompt caching; structured output with Pydantic validation. |
| **File-based user data (watchlist, portfolio, rules)** | **Keep for now** | Single-user; acceptable. Mark for SQLite migration when multi-user or persistence guarantees matter. |
| **File-based cache (`storage/cache/*.json`)** | **Refactor → Redis** | Replace with Redis for in-memory tick store and shared cache. File cache is fine as cold fallback only. |
| **`requests` (sync HTTP)** | **Refactor → `httpx`** | Replace synchronous `requests` with async `httpx` throughout services. Eliminates ThreadPoolExecutor blocking and allows true async fan-out. |
| **ThreadPoolExecutor wrapping sync services** | **Rip out (after httpx migration)** | Necessary workaround today; becomes dead weight after async migration. |
| **NSE scraping as live-tick backbone** | **Rip out for live prices** | Against ToS, no WebSocket, IP-blocked aggressively. Keep only for reference/static data (instrument master, expiry calendars) with 24 h cache. |
| **Yahoo Finance unofficial crumb API** | **Refactor to fallback-only** | Undocumented, breaks without notice. Acceptable as secondary/fallback for historical OHLCV. Primary must be a stable free source (Finnhub for US, broker API for India). |
| **Screener.in CSRF session** | **Refactor** | Brittle (requires manual token entry). Wrap in a service with auto-session refresh + error isolation so a Screener failure doesn't cascade. |
| **Wikipedia HTML scrape for US index lists** | **Replace** | Replace with Finnhub `GET /stock/index` endpoint (free, stable, JSON). |
| **`refetchInterval` on price queries** | **Rip out** | Replace with WebSocket subscription model. Polling introduces 30–120 s price lag — unacceptable for a trader tool. |
| **`setInterval` auto-scan in options-scanner** | **Rip out** | Replace with event-driven re-scan triggered by price-movement threshold, not a wall-clock timer. |
| **No virtualization on symbol tables** | **Rip out (add virtualization)** | Any table with >50 rows that updates on tick needs react-virtual. Current architecture will choke. |
| **CORS `allow_all` regex** | **Refactor** | Tighten to explicit origins (localhost:3000/3001) for dev; env-configurable for prod. |
| **Anthropic key in `settings.json` plaintext** | **Rip out** | Move to server-side env var only. Never expose or store in a user-editable config file that could be leaked. |
| **No WebSocket server** | **Build** | Core missing piece for the entire real-time requirement. |
| **No Redis / tick store** | **Build** | Required for fan-out, last-known-value cache, and staleness tracking. |
| **No circuit breaker / reconnect logic** | **Build** | Required for resilience contract. |
| **No staleness indicator in UI** | **Build** | Required: every price panel must show source + "live / delayed Ns / stale" badge. |
| **No market-hours / timezone logic** | **Build** | IST vs ET, pre-open, post-close, F&O expiry-day behavior, NSE/BSE holidays. |
| **No decimal-safe price math** | **Build** | Python `Decimal` or `decimal.js` on FE for price/Greeks arithmetic. Current float math risks rounding errors in P&L and Greeks. |
| **No observability** | **Build** | Latency dashboards, feed-disconnect alerts, dropped-message counters. |
| **No unit tests for indicators/patterns** | **Build** | Required by spec and by correctness. |

---

## 5. Prioritized Risk List

### CRITICAL (data-correctness or legal breach — must resolve before any live trading use)

| # | Risk | Impact | Evidence |
|---|---|---|---|
| **R-1** | NSE scraping used as live-price backbone | Legal (ToS breach) + Reliability (IP block → total India data outage) | `nse_service.py:51–67`, all F&O endpoints |
| **R-2** | No WebSocket / real-time push path exists | User sees 30–120 s stale prices labeled as current | All `refetchInterval` entries |
| **R-3** | `faGet/faPost` bypass Next.js proxy → browser calls FastAPI directly | Security: exposes internal server; NSE cookie handling bypassed | `lib/fno-api.ts:faGet`, `lib/fno-api.ts:faPost` |
| **R-4** | Anthropic API key stored plaintext in `settings.json` | If file is leaked or app becomes public-facing, key is exposed | `settings.py`, `fno_ai_service.py:21` |
| **R-5** | Float arithmetic on prices and Greeks | Silent rounding errors in P&L, Greeks, and option pricing | No `Decimal` usage found in any pricing path |

### HIGH (reliability / accuracy — must resolve before Phase 5 shipment)

| # | Risk | Impact | Evidence |
|---|---|---|---|
| **R-6** | Single NSE Session — no failover | One blocked IP or session expiry silently stalls all India data | `nse_service.py` global session |
| **R-7** | No circuit breaker on any upstream | Slow NSE / Yahoo timeouts (8–20 s) hold ThreadPool workers; 16 simultaneous → total backend stall | `deps.py:run_sync`, services timeouts |
| **R-8** | Yahoo Finance unofficial API | Can break silently with zero warning; US market data goes dark | `market_data_service.py`, `us_market_service.py` |
| **R-9** | No staleness / heartbeat detection | Stale prices displayed as current during partial outages | No stale flag logic anywhere in codebase |
| **R-10** | All services synchronous (`requests`) | Async FastAPI negated by sync HTTP; true concurrency limited to 16 threads | All `services/*.py` |
| **R-11** | No virtualization on price tables | 500+ symbols ticking → entire page re-renders every tick; browser freeze | No `react-virtual` in deps |
| **R-12** | Backtest / pattern detection has no look-ahead-bias guard | Confidence numbers may be inflated; signals look better than they are in live use | `patterns.py`, `backtests.py` — no forward-bar exclusion verified |
| **R-13** | Screener.in CSRF requires manual token entry | Fundamentals silently fail if token expires; no auto-refresh | `screener_service.py:85–92`, `settings/page.tsx` |

### MEDIUM (quality / maintainability — address in parallel with feature work)

| # | Risk | Impact | Evidence |
|---|---|---|---|
| **R-14** | CORS `allow_all` regex | Acceptable locally; CSRF risk if ever deployed | `main.py:92–101` |
| **R-15** | Wikipedia HTML scrape for US index lists | Fragile; breaks on Wikipedia layout change | `us_universe_sync.py:159–160` |
| **R-16** | No market-hours / timezone logic | Pre-open data shown as regular session; F&O expiry-day edge cases not handled | No `pytz`/`zoneinfo` usage found |
| **R-17** | No unit tests for any indicator or pattern | Regressions undetectable; can't prove precision contract | No `tests/` directory |
| **R-18** | No observability infrastructure | Feed disconnects not alerted; latency regressions invisible | No metrics, no tracing |
| **R-19** | File-based cache: no atomic writes | Concurrent writes to same JSON cache file can corrupt it | `cache_manager.py` |
| **R-20** | 15-min `setInterval` in options-scanner | Arbitrary wall-clock trigger; fires during non-market hours if guard logic is wrong | `options-scanner/page.tsx:759–772` |

---

## 6. Honest Data-Source Reality Statement

Per Phase 2 requirements, stating this plainly:

**India:**
- True free real-time tick streaming for NSE/BSE does **not** exist outside licensed exchange feeds.
- The current NSE scraping is snapshot-based (not streaming), against ToS, and fragile.
- **Recommended path:** Free broker WebSocket API (Dhan, Fyers, Angel One SmartAPI, Upstox, or ICICI Breeze). These are legal, near-real-time (~200–500 ms LTP), free for account holders. Option chain OI refreshes at ~3 s cadence per broker throttle — this is the physical limit of freely available OI data, not a software problem.
- **NSE scraping should be retained only for:** instrument master lists, expiry calendars, index constituent lists — all cached 24 h.
- **The UI must label every India price panel as:** data source name + "~200–500 ms delayed (broker feed)" or "snapshot, delayed up to 60 s" (for any remaining scrape path).

**US:**
- True free real-time is available: Finnhub WebSocket (`wss://ws.finnhub.io`) — 50-symbol cap per connection, no credit card required.
- Symbol rotation on navigation (unsubscribe off-screen symbols, subscribe on-screen symbols) is required to stay within the cap.
- Secondary/failover: Alpaca free IEX feed or Twelve Data (800 req/day free tier).
- **The UI must label US prices as:** "Real-time (Finnhub / IEX)" with last-tick timestamp.

---

## 7. Phase 1 Architecture Requirements (Preview)

The following gaps must be filled before any feature work proceeds:

1. **WebSocket gateway** — Node.js or Python (`websockets` / `starlette` native) managing one upstream connection per feed, fanning out to all browser tabs.
2. **Redis tick store** — last-known value per symbol, TTL = 10 s (staleness window), pub/sub channel for browser fan-out.
3. **Async HTTP client migration** — replace `requests` with `httpx.AsyncClient` in all services.
4. **Circuit breaker** — per upstream (NSE, Yahoo, broker feed), with exponential backoff + jitter.
5. **Staleness indicator** — every price cell shows: source name, "live / delayed Ns / STALE" badge, last-updated timestamp.
6. **Broker API integration** — choose one India free broker (await user confirmation of account) before writing connection code.
7. **Finnhub WebSocket** — US real-time, symbol subscription rotation.
8. **Symbol-keyed atom store** (Jotai or Zustand) on frontend — one atom per symbol, components subscribe only to their symbol → no cross-symbol re-renders.
9. **react-virtual** — virtualize all symbol tables.
10. **Decimal-safe math** — Python `Decimal` for all price/Greeks computations; `decimal.js` on frontend P&L.

---

## 8. Summary Score

| Dimension | Current State | Required State |
|---|---|---|
| Live data (India) | Snapshot scrape, 30–120 s lag | WebSocket broker feed, <1 s LTP |
| Live data (US) | Polling Yahoo 60 s | Finnhub WebSocket, true real-time |
| No-refresh requirement | Not met (polling everywhere) | Met (WebSocket push) |
| Fan-out (1 upstream : N tabs) | Not met (each tab polls independently) | Met (Redis pub/sub) |
| Auto-reconnect + backoff | Not present | Required |
| Failover data sources | Not present | Required |
| Staleness indicators | Not present | Required |
| Data source transparency | Not present | Required (source + latency label per panel) |
| Decimal-safe math | Not present | Required |
| Look-ahead-bias protection | Not verified | Required for backtest engine |
| Unit tests (indicators/patterns) | None | Required |
| Observability | Rotating log file only | Latency metrics + feed-disconnect alerting |
| Security (API keys) | Plaintext in settings.json | Server-side env only |

**Verdict:** The existing codebase is a well-structured scaffold with the right frontend framework, charting library, and AI integration. The core architecture is sound for a single-user snapshot tool. It is **not yet a trader-grade real-time platform**. The polling model, absent WebSocket infrastructure, synchronous backend, and reliance on unofficial scraped data are the four structural blockers. All are fixable within the existing repo without a rewrite.

---

*Awaiting approval to proceed to Phase 1: Architecture Decision Record + data-source confirmation.*
