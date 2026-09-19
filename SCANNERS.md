# Scanner Reference — Equity (IN + US) & F&O (IN)

Complete technical reference for the three scanning surfaces in the platform, and
in particular how the **Timeframe**, **Pattern**, and **Confluence Score** filters
actually work.

| Scanner | Route | Backend | Markets | Timeframes | Instrument |
|---|---|---|---|---|---|
| **Equity Scanner** | `/equity-scanner` | `backend/routers/equity_scanner.py` | India **and** US | Daily · Weekly · Monthly | Cash stock |
| **F&O Live Scanner** | `/live-scanner` | `backend/routers/live_scanner.py` | India only | 5m · 15m · 30m · 1h · 4h · 1d · 1wk · 1mo | Options (CE/PE) |

Both scanners share the **same brain**: one confluence scorer and one pattern
registry. They differ only in universe, timeframe set, and what trade plan gets
built at the end.

---

## Table of contents

- [1. Architecture](#1-architecture)
- [2. Data source](#2-data-source)
- [3. Filter — Timeframe](#3-filter--timeframe)
- [4. Filter — Patterns](#4-filter--patterns)
- [5. Filter — Confluence Score](#5-filter--confluence-score)
- [6. Equity Scanner (IN + US)](#6-equity-scanner-in--us)
- [7. F&O Live Scanner (IN)](#7-fo-live-scanner-in)
- [8. API reference](#8-api-reference)
- [9. Known quirks & caveats](#9-known-quirks--caveats)

---

## 1. Architecture

```
Browser (Next.js)
   │
   ├─ SSE scan  ──────────────────────► FastAPI  /api/{equity|live}-scanner/scan/stream
   │   (direct to FastAPI, bypasses the Next proxy — streaming can't be proxied)
   │
   └─ everything else ─► Next route handler ─► FastAPI
       /app/api/{equity|live}-scanner/[...slug]/route.ts
```

Per-symbol pipeline, identical in both scanners:

```
symbol
  └─► get_ohlcv(symbol, interval)         one HTTP call per timeframe
        └─► add_indicators(df)             EMA20/50, VWAP, RSI14, MACD-hist, ATR14, RelVol
              └─► run_detectors(df, tf)    73 pattern detectors, TF-gated
                    └─► score(...)         confluence 0–100
                          └─► threshold?   keep if total >= threshold
                                └─► build_equity_plan()  |  build_plan()  (options)
```

Key modules:

| File | Role |
|---|---|
| `services/intraday_data.py` | Yahoo Finance fetch, ticker mapping, universes, TF→range map |
| `services/confluence_scorer.py` | Indicators + the 0–100 score |
| `services/pattern_registry.py` | 73 pattern detectors (the modern engine) |
| `services/pattern_detector.py` | 10-pattern legacy fallback detector |
| `services/scan_support.py` | Input validation, pattern post-filter, backtest, scan diagnostics |
| `services/lot_sizes.py` | Single source of truth for F&O lot sizes |
| `services/equity_advisor.py` | ATR-based stock trade plan |
| `services/option_advisor.py` | ATR-based option trade plan (strike/premium) |
| `services/breakout_service.py` | Breakout state badge |

Concurrency (per scan request):

| | Equity | F&O |
|---|---|---|
| Thread pool | `max_workers=16` (`equity-scan`) | `max_workers=12` (`fno-scan`) |
| Symbol semaphore | `10` | `8` (`/scan`), `12` (`/scan/stream`) |
| Parallel HTTP | 10 symbols × 3 TFs ≈ 30 | 8 symbols × up to 8 TFs |

Each scanner has its own pool so neither starves the other, nor the default
FastAPI pool (`max_workers=8`) used by health checks and paper trades.

---

## 2. Data source

**Yahoo Finance REST chart API.** No API key, no `yfinance` package call path —
raw HTTP against:

```
https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval={i}&range={r}
https://query2.finance.yahoo.com/...        ← fallback on HTTP 404
```

A **fresh `requests.Session()` per call** avoids shared-session rate limiting.
Timeout 15s. On total failure an empty DataFrame is returned — and the symbol is
**counted and reported**, not silently dropped: see
[scan diagnostics](#scan-diagnostics).

### Ticker resolution (`_ticker`, `intraday_data.py:369`)

Resolution order:

1. **Index map** — `NIFTY→^NSEI`, `BANKNIFTY→^NSEBANK`, `FINNIFTY→NIFTY_FIN_SERVICE.NS`, `SENSEX→^BSESN`, `MIDCPNIFTY→NIFTY_MID_SELECT.NS`, `BANKEX→BSE-BANK.BO`, `INDIAVIX→^INDIAVIX`, `SP500→^GSPC`, `NASDAQ100→^NDX`, `DOW→^DJI`, `RUSSELL2000→^RUT`, `NASDAQ→^IXIC`
2. **Equity overrides** — `TATAMOTORS→TMCV.NS`, `ETERNAL→ETERNAL.NS`
3. **US symbols** — used **as-is, no suffix**. The US set is built at import time by eagerly loading every `storage/universe/US_*.json` **and `ALL_US_LISTED.json`**
4. **Default** — append `.NS` (NSE equity)

> This is the single branch point between India and US. A symbol is "US" purely
> because it appears in one of those files. A startup assertion logs an error if
> any symbol in a US universe still resolves to a `.NS` ticker, so this can no
> longer be a silent per-symbol data outage.

### Incomplete-bar guard (`_drop_incomplete_trailing_bar`)

The last bar is dropped when it is not a fully-closed period, because pattern
detectors key off the final bar and get fooled by partial ones:

- **Intraday stub** — `volume == 0` and `open == high == low == close`. Trivially
  looks like the narrowest bar possible, so NR7/Doji/Inside-Bar fire constantly.
- **Still-forming weekly/monthly** — for `1wk`/`1mo`, if time since the last bar
  is `< 0.9 ×` the typical inter-bar gap, the bar is still forming and is dropped.

### Caching & market hours

**Process-level bar cache.** Fetched frames are cached on
`(ticker, interval, range)` with a per-timeframe TTL. The *frame* is cached,
never a score, so a cache hit and a live fetch produce identical results.
Callers get a copy, so a mutation downstream cannot poison the cache.

| Timeframe | TTL |
|---|---|
| `5m`, `15m` | 60s |
| `30m`, `1h` | 5 min |
| `4h`, `1d` | 15 min during market hours |
| `1d` (market closed) | until the next 09:15 IST weekday open |
| `1wk`, `1mo` | 6 h |

`cache_hit_rate` is reported in the scan summary. Per-request dicts
(`daily_cache`, `chain_cache`, `iv_cache`) still dedupe enrichment work within
one scan.

- **No market-hours gating on scanning.** Scans run any time; off-hours simply
  return the last closed bars. Market hours only affect the `1d` cache TTL.

---

## 3. Filter — Timeframe

### What the filter does

The timeframe filter is a **fetch-level** filter, not a display filter. Unselected
timeframes are **never requested from Yahoo at all**, so deselecting timeframes
cuts external API calls (and scan time) proportionally.

Wire format: comma-separated, e.g. `timeframes=1d,1wk`. **Omitting the parameter
entirely** = all. Passing it with an empty value (every timeframe deselected) is
an error, not a request to scan everything — it returns **HTTP 400**
`"Select at least one timeframe."`, and both UIs disable the scan button in that
state. A value outside the scanner's allowed set returns **HTTP 400** naming the
offending value rather than silently dropping it.

| Scanner | Allowed values | Default |
|---|---|---|
| Equity | `1d`, `1wk`, `1mo` | all three |
| F&O | `5m`, `15m`, `30m`, `1h`, `4h`, `1d`, `1wk`, `1mo` | all eight |

### One symbol can produce several setups

Each timeframe is scored **independently**. RELIANCE scored on 15m, 1h and 1d
yields up to three separate cards. This is why the summary distinguishes
`unique_setups` (distinct symbols) from `total_setups` (cards).

### Timeframe → history fetched

`_YF_RANGE` in `intraday_data.py:38`:

| Timeframe | Yahoo `interval` | Yahoo `range` | Approx bars |
|---|---|---|---|
| `5m` | `5m` | `5d` | ~375 |
| `15m` | `15m` | `15d` | ~375 |
| `30m` | `30m` | `20d` | ~250 |
| `1h` | `1h` | `60d` | ~390 |
| `4h` | *derived* | — | ~100 |
| `1d` | `1d` | `1y` | ~250 |
| `1wk` | `1wk` | `5y` | ~260 |
| `1mo` | `1mo` | `5y` | ~60 |

**`4h` has no native Yahoo interval.** It is resampled from `1h` bars into
**session-aligned** buckets anchored to the 09:15 IST open, so on NSE they run
**09:15–13:15** and **13:15–15:30** (the final bucket is short). 4h divides 24h
exactly, so one origin at the first session open repeats the same boundaries
every day. If you select `4h` without `1h`, `1h` is still fetched internally as a
dependency and then discarded.

The F&O mini-chart reads `4h` from `/api/live-scanner/chart-data`, the endpoint
that owns the resample — `CandleChart` routes by interval.

### What the timeframe does NOT change

**Indicator lookbacks are fixed across all timeframes.** There is no per-TF
tuning:

| Indicator | Period | Notes |
|---|---|---|
| EMA fast | **20** | needs ≥20 bars |
| EMA slow | **50** | needs ≥50 bars |
| RSI | **14** | needs ≥14 bars |
| MACD histogram | **12/26/9** | needs ≥26 bars |
| ATR | **14** | needs ≥14 bars |
| Relative volume | **20-bar** rolling mean | needs ≥20 bars |
| Swing structure | last **10** bars | new 10-bar high/low vote |

So "EMA20" means 20 five-minute bars on `5m` and 20 months on `1mo`. The
timeframe changes what a bar *means*, never how many bars are measured.

**Minimum 50 bars** to score at all — EMA50 is a trend-vote input, so a shorter
history would be scored on a systematically smaller vote set than its peers.
Below that the symbol/TF is skipped and counted in
`skipped_insufficient_bars`. Practically this bites on `1mo` (~60 bars of
history) and on `1wk` for recently-listed symbols.

### Timeframe → which patterns can fire

This is where timeframe genuinely changes behaviour. Every pattern declares a
`valid_timeframes` list, and `run_detectors` skips any pattern whose list omits
the current TF:

| Cohort | Timeframes | Applies to |
|---|---|---|
| `_A` (all) | all 8 | all candlestick, all volume, most price-action |
| `_C` (chart) | `15m,30m,1h,4h,1d,1wk,1mo` — **excludes `5m`** | all 25 chart patterns + 2 Wyckoff |
| `_EQ` (equity) | `1d,1wk,1mo` only | 52W High/Low, 52W Breakout, EMA20 pullback, 50 DMA pullback |

Consequences:

- On **`5m`**, no chart pattern and no Wyckoff pattern can ever fire — only
  candlestick, volume, and generic price-action.
- On **any intraday TF**, the four 52-week / moving-average-pullback patterns
  cannot fire. They are Daily/Weekly/Monthly only.
- Because the F&O scanner is the only one with intraday TFs, and the equity
  scanner is the only one with `_EQ`-eligible TFs, the two scanners see
  **materially different pattern sets** even though they share one registry.

**Noisy-timeframe confidence penalty:** on `5m`, `15m`, `30m`, any pattern in the
`chart` or `harmonic` family has its confidence reduced by **0.10** (floored at
0.0). Since `5m` already excludes them, this effectively penalises `15m` and `30m`.

### Timeframe → minimum bars per pattern

Each pattern also has a `min_bars` gate (`len(df) < min_bars` → skipped). Ranges
from 3 (single candles) to 90 (Cup & Handle). On `1mo` with ~60 bars of history,
Cup & Handle (90) and Rounding Bottom/Top (60, borderline) rarely or never fire.

---

## 4. Filter — Patterns

### Pattern selection is a filter, not a score modifier

`pattern_names` selects which setups you want to **see**. It does not change what
a setup is **worth**.

The full detector set always runs, and the confluence score is always computed
from the full set. The selection is then applied as a **hard post-filter**: a
card survives only if at least one of its detected patterns — or the pattern
displayed on the card — is in your selection.

> **A score of 72 means the same thing with a pattern filter as without one.**
> This is a hard guarantee, covered by a test.

| Filter | Param | Stage | Effect |
|---|---|---|---|
| **Pattern names** | `pattern_names` | **After scoring** | Hard filter — keeps only cards containing a selected pattern |
| **Pattern families** | `patterns` | After scoring | Drops cards where no detected pattern is in the named families |
| **Confidence floor** | `min_pattern_conf` | After scoring | Drops cards where no detected pattern reaches that confidence |

Valid families: `candlestick`, `price_action`, `volume`, `chart`, `harmonic`.
Matching is case-insensitive.

> **`patterns` and `min_pattern_conf` are not reachable from the UI.** Both
> scanner pages send `pattern_names` and `pattern_mode`. The family and
> confidence filters are API-only.

#### Pre-scan selection vs. the post-scan Patterns filter

Both scanner pages have **two** pattern controls, and they are not the same thing:

| Control | Where | Sent to the backend? | Effect |
|---|---|---|---|
| **Patterns** picker (above *Run Scan*) | scan configuration | yes — `pattern_names` | Narrows what the scan returns at all |
| **Patterns** multi-select (in *Filter results*) | after results load | no — client-side only | Narrows what is displayed, instantly, without re-scanning |

The post-scan filter sits next to **Direction**, is multi-select, and lists only
the patterns actually present in the current result set, each with a count. An
empty selection means "no filter". A card matches if the pattern shown on it
**or** any pattern detected on it is selected, so filtering by a pattern visible
in the *Pattern(s)* column always keeps that row. Both post-scan filters reset
when a new scan completes.

When a card survives via a *non-primary* pattern, the displayed
`card["pattern"]` is rewritten to the highest-confidence matched pattern, so the
UI always shows a pattern you actually selected.

#### `pattern_mode` — the old behaviour, behind an opt-in

| Mode | Default | Behaviour |
|---|---|---|
| `filter` | ✅ | Score from the full detector set, then hard-filter. Scores match an unfiltered scan. |
| `shape` | | Legacy. Non-selected patterns are stripped **before** Categories 4 and 5, so those collapse to 0 whenever your pattern doesn't fire. |

`shape` lowers scores by up to 30 points — the reachable maximum drops from 100
to 70 — so it must be paired with a lower threshold. It is the reason a
pattern-filtered scan used to come back nearly empty: the default threshold of 65
was only 5 points below the shaped ceiling, and clearing it required a perfect
trend vote, a healthy RSI, a rising MACD histogram **and** relvol ≥ 2.5×
simultaneously. The few cards that did survive were the ones where none of the
selected patterns had fired — the opposite of what was asked for.

### Matching is by identity, not by display text

Every emitted pattern carries a stable **`pattern_id`** (e.g. `inside_bar_breakout`)
and a **`parent_id`** linking directional variants to their base pattern.

- Matching is on `pattern_id`, case-insensitively.
- **Selecting a parent selects its variants** — `Inside Bar` also matches
  `Inside Bar Breakout` and `Inside Bar Breakdown`.
- `pattern_names` still accepts display names for backward compatibility; they
  are resolved through the id map.
- A name that resolves to nothing returns **HTTP 400** naming it, rather than
  silently producing an empty scan.

`GET /patterns` serves the **complete emitted set** — 86 entries: the 73 registry
detectors, the 6 directional variants nested under their parents, and the 3
names only the legacy fallback emits.

| Was unselectable | Now |
|---|---|
| `Inside Bar Breakout` / `Breakdown` | nested under `Inside Bar` |
| `Breakdown Retest` | nested under `Breakout Retest` |
| `Rectangle Breakdown` | nested under `Rectangle Breakout` |
| `Channel Breakdown` | nested under `Channel Breakout` |
| `Trendline Breakdown` | nested under `Trendline Breakout` |
| `Hammer / Pin Bar` | nested under `Hammer` (legacy-only) |
| `Bullish` / `Bearish Marubozu` | top-level candlestick entries (legacy-only) |

### Legacy fallback

When the registry finds nothing, the scorer falls back to a legacy 10-pattern
single-bar detector (`services/pattern_detector.py`): Morning Star, Evening Star,
Inside Bar Breakout/Breakdown, Bullish/Bearish Engulfing, Hammer / Pin Bar,
Shooting Star, Bullish/Bearish Marubozu.

Under `pattern_mode=filter` this fallback **always runs** — the selection is
applied afterwards, so the fallback can no longer defeat it. It is skipped under
`pattern_mode=shape`, where the selection has to bite before scoring.

### The registry: 73 patterns

| Family | Count | Tier | Character |
|---|---|---|---|
| `candlestick` | 23 | 1 | 1–3 bar Japanese candle shapes |
| `price_action` | 12 | 1 (11) + 2 (1) | bar structure & location context |
| `volume` | 7 | 1 | volume-relative signals |
| `chart` | 25 | 2 | classic multi-bar formations |
| `harmonic` | 2 | 2 | Wyckoff accumulation/distribution |
| `smc` | 4 | 2 | ICT/Smart-Money-Concepts — Fair Value Gap, Order Block, Break of Structure, Change of Character |

`smc` patterns count as structural for `best_for_confluence` and the Category-5
structural bonus, the same as `chart`/`price_action` Tier-2 confirmed patterns.

**Tier** — Tier 1 = fast/local signals detectable on few bars. Tier 2 = structural
multi-bar formations. **There is no Tier 3** — the concept and the `max_tier`
parameter that implied it have been removed.

**State** — `"confirmed"` (the trigger has happened) or `"forming"` (structure in
progress, no trigger yet). Candlesticks are always confirmed. Flags, channels,
cups, Wyckoff and the 52W-proximity patterns are always forming. Level-break
chart patterns are conditional on price actually breaking the level.

**Freshness gate** — Double/Triple Top & Bottom and Trendline Breakout use a
recency test: a level crossed **more than 5 bars ago and still crossed** is
"stale" and the pattern returns nothing at all. This stops the scanner
re-reporting a breakout for weeks after it happened.

**Strength → points** — `1 → 8`, `2 → 16`, `3 → 25`. This is the Candle Trigger
contribution. Several detectors scale strength dynamically (e.g. Hammer is
strength 3 when lower wick ≥ 3× body, else 2; Volume Surge is 3 when relative
volume ≥ 2.5×, else 2).

**Deduplication** — results are sorted by confidence descending, then deduped on
`(family, direction, name)`.

#### Candlestick (23) — Tier 1, all timeframes

| Pattern | Dir | Str | Min bars | Rule |
|---|---|---|---|---|
| Hammer | bull | 2–3 | 3 | `lower wick ≥ 2×body`, `upper wick < body`. Conf `0.55 + (lw/b−2)×0.10` capped 0.90; +0.05 if prior downtrend |
| Inverted Hammer | bull | 2–3 | 3 | `upper wick ≥ 2×body`, `lower wick < body`. Conf ≤0.80 |
| Dragonfly Doji | bull | 2 | 3 | `body ≤ 8% range`, `lower wick ≥ 50% range`, `upper wick ≤ 10% range`. Conf 0.65 |
| Hanging Man | bear | 2 | 6 | Hammer shape **plus** confirmed uptrend (`close[−6] < close[−2]`). Conf 0.62 |
| Shooting Star | bear | 2–3 | 3 | `upper wick ≥ 2×body`, `lower wick < body`. Conf ≤0.88 |
| Gravestone Doji | bear | 2 | 3 | `body ≤ 8% range`, `upper wick ≥ 50% range`, `lower wick ≤ 10% range`. Conf 0.65 |
| Doji | neutral | 1 | 3 | `body ≤ 8% range`, both wicks ≤ 50% range. Conf 0.55 |
| Long-Legged Doji | neutral | 2 | 3 | `body ≤ 8% range`, both wicks ≥ 30% range. Conf 0.62 |
| Spinning Top | neutral | 1 | 3 | `0.08 < body/range < 0.25`, both wicks ≥ 50% body. Conf 0.55 |
| Doji at Support | bull | 2 | 20 | Doji within 2% of the 20-bar low. Conf 0.68 |
| Doji at Resistance | bear | 2 | 20 | Doji within 2% of the 20-bar high. Conf 0.67 |
| Bullish Engulfing | bull | 3 | 4 | Bear then bull bar; current body engulfs prior and is larger. Conf 0.78, +0.08 if volume > 1.3× prior |
| Piercing | bull | 2 | 4 | Opens below prior close, closes above prior midpoint but under prior open. Conf 0.70 |
| Tweezer Bottom | bull | 2 | 4 | Two lows within 0.3%; bear then bull. Conf 0.68 |
| Bearish Engulfing | bear | 3 | 4 | Mirror of bullish engulfing. Conf 0.76, +0.08 on volume |
| Dark Cloud Cover | bear | 2 | 4 | Opens above prior close, closes below prior midpoint but above prior open. Conf 0.70 |
| Tweezer Top | bear | 2 | 4 | Two highs within 0.3%; bull then bear. Conf 0.68 |
| Morning Star | bull | 3 | 5 | Big bear → small body (<30%) gapping down → bull closing above bar-1 midpoint. Conf 0.80 |
| Three White Soldiers | bull | 3 | 5 | 3 rising bull bars, each upper wick ≤ 30% body. Conf 0.82 |
| Abandoned Baby Bottom | bull | 3 | 5 | Bear → island doji (gap both sides) → bull. Conf 0.85 |
| Evening Star | bear | 3 | 5 | Mirror of morning star. Conf 0.78 |
| Three Black Crows | bear | 3 | 5 | 3 falling bear bars, each lower wick ≤ 30% body. Conf 0.80 |
| Abandoned Baby Top | bear | 3 | 5 | Mirror of abandoned baby bottom. Conf 0.85 |

#### Price action (12)

| Pattern | Dir | Str | TF | Min bars | Rule |
|---|---|---|---|---|---|
| Inside Bar | neutral | 1 | all | 5 | Bar contained in prior range, no break. State `forming`, conf 0.50 |
| ↳ Inside Bar Breakout | bull | 2 | all | 5 | Same, then close > mother high. Conf 0.72 |
| ↳ Inside Bar Breakdown | bear | 2 | all | 5 | Same, then close < mother low. Conf 0.72 |
| Outside Bar | bull/bear | 2 | all | 4 | Higher high **and** lower low than prior. Direction from close vs open. Conf 0.65 |
| NR7 | neutral | 1 | all | 9 | Last bar's range is the strict minimum of the last 7. Conf 0.60 |
| Fakey | bull/bear | 2 | all | 6 | Inside bar, false break of mother bar, then reversal bar. Conf 0.73 |
| Breakout Retest | bull | 2 | all | 20 | Close above prior 15-bar resistance, pulled back to within −3%/+2% of it, now rising. Conf 0.75 |
| ↳ Breakdown Retest | bear | 2 | all | 20 | Mirror. Conf 0.75 |
| Near 52W High | bull | 2 | `_EQ` | 52 | Within 5% of the 52-period high. State `forming`, conf 0.65 |
| Near 52W Low | bear | 2 | `_EQ` | 52 | Within 5% of the 52-period low. Conf 0.63 |
| Pullback to 20 EMA | bull | 2 | `_EQ` | 30 | Rising EMA20, price within 1.5% of it, closing up. Conf 0.70 |
| Pullback to 50 DMA | bull | 2 | `_EQ` | 60 | Rising SMA50, price within 2% of it, closing up. Conf 0.68 |
| Overbought Reversal | bear | 2 | all | 20 | RSI was >70 three bars ago, now ≤70, closing down. Conf 0.68 |
| Oversold Bounce | bull | 2 | all | 20 | RSI was <30 three bars ago, now ≥30, closing up. Conf 0.68 |
| **52W High Breakout** | bull | 3 | `_EQ` | 52 | **Tier 2.** Close exceeds the 52-period max close. Conf 0.78, +0.10 on 1.5× volume |

#### Volume (7) — Tier 1, all timeframes

All require real volume (`volume.tail(20).sum() > 0`), so they never fire on indices.

| Pattern | Dir | Str | Min bars | Rule |
|---|---|---|---|---|
| Volume Surge on Breakout | bull | 2–3 | 22 | RelVol ≥ 1.8× **and** close ≥ 99% of the prior 20-bar high. Conf `0.65 + (rv−1.8)×0.05` ≤0.90 |
| Volume Dry Up | bull | 1 | 22 | Last 3 bars' mean volume ≤ 50% of the 20-bar average, price holding above EMA20. State `forming`, conf 0.62 |
| Accumulation Phase | bull | 2 | 12 | Over 10 bars, mean up-bar volume > 1.4× mean down-bar volume. `forming`, conf 0.68 |
| Distribution Phase | bear | 2 | 12 | Mirror. `forming`, conf 0.68 |
| Selling Climax | bull | 2 | 22 | RelVol ≥ 2.5×, new 20-bar low, close in the upper half of the bar. Conf ≤0.85 |
| Volume Breakdown | bear | 2–3 | 22 | RelVol ≥ 1.8× and close below the prior 20-bar low. Conf ≤0.88 |
| Gap Up with Volume | bull | 2–3 | 10 | Open > 100.5% of prior high, volume ≥ 1.5× average. Conf `0.65 + gap%×0.02` ≤0.85 |

#### Chart (25) — Tier 2, `_C` timeframes (no `5m`)

Swing points come from a 3-bar-either-side pivot scan.

| Pattern | Dir | Str | Min bars | Rule |
|---|---|---|---|---|
| Head & Shoulders | bear | 2–3 | 40 | Head > both shoulders by 2%; shoulder asymmetry < 8%. Neckline = 30-bar min close. Confirmed on close below neckline |
| Inverse Head & Shoulders | bull | 2–3 | 40 | Mirror; neckline = 30-bar max close |
| Double Bottom | bull | 2–3 | 25 | Two swing lows within 4%, ≥5 bars apart. Neckline = max high between. Fresh break only |
| Double Top | bear | 2–3 | 25 | Mirror. Fresh break only |
| Triple Bottom | bull | 2–3 | 40 | Three swing lows within 4% of each other. Fresh break only |
| Triple Top | bear | 2–3 | 40 | Mirror. Fresh break only |
| Rounding Bottom | bull | 2 | 60 | 60 bars in thirds; middle third lowest, first third ≥3% above it. `forming` |
| Rounding Top | bear | 2 | 60 | Mirror. `forming` |
| Ascending Triangle | bull | 2–3 | 25 | Flat highs (range <4%) + rising lows (slope >0.1%). Confirmed above resistance ×1.01 |
| Descending Triangle | bear | 2–3 | 25 | Flat lows + falling highs. Confirmed below support ×0.99 |
| Symmetrical Triangle Breakout | bull/bear/neutral | 1–2 | 25 | Highs slope < −0.08 **and** lows slope > 0.08. Direction from which side breaks |
| Bull Flag | bull | 2–3 | 30 | Pole ≥ +8% over 10/15/20 bars, then 10-bar consolidation with range <8% drifting down |
| Bull Pennant | bull | 2 | 30 | Pole ≥ +8%, then 10-bar converging range. Conf 0.72 |
| Bear Flag | bear | 2–3 | 30 | Pole ≤ −8%, then 10-bar range <8% drifting up |
| Bear Pennant | bear | 2 | 30 | Pole ≤ −8%, then converging range. Conf 0.70 |
| Descending Wedge Breakout | bull | 2–3 | 30 | Both slopes negative, highs falling faster than lows. Confirmed above last swing high |
| Rising Wedge | bear | 2–3 | 30 | Both slopes positive, lows rising faster than highs. Confirmed below last swing low |
| Rectangle Breakout | bull | 2 | 20 | Flat support and resistance (each <4% spread), 3%<height<30%, close >res×1.01 |
| ↳ Rectangle Breakdown | bear | 2 | 20 | Close < support ×0.99 |
| Cup & Handle | bull | 2–3 | 90 | 90-bar cup: depth 10–50%, rims within 8%, floor <92% of left rim. Strength 3 with handle. `forming` |
| High Tight Flag | bull | 3 | 20 | Move ≥ +25% then 5-bar flag with range ≤15%. Conf 0.82, `forming` |
| V Bottom | bull | 2 | 20 | Fall ≥8% then rise ≥8% off a mid-window low; recovery ratio ≥0.70 |
| Channel Breakout | bull | 2 | 25 | Parallel channel (slope diff ≤0.25, not flat), close above top ×1.01 |
| ↳ Channel Breakdown | bear | 2 | 25 | Close below bottom ×0.99 |
| Trendline Breakout | bull | 2 | 35 | Fitted rising support line; close breaks 0.5% above it **now** but not 5 bars ago |
| ↳ Trendline Breakdown | bear | 2 | 35 | Mirror on a falling resistance line |
| Ascending Channel | bull | 2 | 30 | Both slopes positive & parallel; price inside. `forming`, conf 0.68 |
| Descending Channel | bear | 2 | 30 | Mirror. `forming`, conf 0.68 |

#### Harmonic / Wyckoff (2) — Tier 2, `_C` timeframes

| Pattern | Dir | Str | Min bars | Rule |
|---|---|---|---|---|
| Wyckoff Accumulation | bull | 1 | 60 | 40-bar range between 3% and 15% **following a prior decline** (price ≥3% higher 20 bars before the range began), with volume drying up in the last 20 bars. Conf **0.35**, `forming` |
| Wyckoff Distribution | bear | 1 | 60 | Same, but **following a prior advance**, plus price in the upper half of the range. Conf **0.32**, `forming` |

> Both are strength 1 (8 pts) with very low confidence — they are context flags,
> not triggers. The prior-trend requirement (added in the pattern-cleanup pass)
> is what actually differentiates these from a plain Rounding Bottom/Top — a
> quiet range by itself is no longer enough.

#### SMC / ICT (4) — Tier 2, `_C` timeframes

| Pattern | Dir | Str | Min bars | Rule |
|---|---|---|---|---|
| Bullish FVG | bull | 2 | 20 | 3-candle imbalance: `low[i] > high[i-2]`. Fires `confirmed` when price returns into the still-open gap and closes back up; `forming` if just created |
| ↳ Bearish FVG | bear | 2 | 20 | Mirror: `high[i] < low[i-2]` |
| Bullish Order Block | bull | 2 | 30 | Last bearish candle before a displacement (body ≥1.5×ATR) that breaks a recent swing high. Fires `confirmed` when price returns into that candle's range and closes back up |
| ↳ Bearish Order Block | bear | 2 | 30 | Mirror — last bullish candle before a bearish displacement breaking a swing low |
| Bullish BOS | bull | 3 | 40 | Break of Structure (continuation): prior swing structure is ascending (higher highs + higher lows) and a **fresh** close breaks above the last swing high |
| ↳ Bearish BOS | bear | 3 | 40 | Mirror on a descending structure |
| Bullish CHoCH | bull | 2 | 40 | Change of Character (reversal): prior structure descending, fresh close breaks **above** the last swing high — first sign of a reversal |
| ↳ Bearish CHoCH | bear | 2 | 40 | Mirror: prior structure ascending, fresh close breaks below the last swing low |

`smc` patterns count as structural for `best_for_confluence` (Stage 1) and the
Category-5 structural bonus, the same as confirmed Tier-2 `chart`/`price_action`
patterns — a confirmed BOS or CHoCH outranks a candlestick, matching how ICT
traders would weight it.

### Which single pattern feeds the score

`run_detectors` returns *all* matching patterns, but only **one** feeds the
Candle Trigger category. `best_for_confluence` picks it in four stages — first
non-empty stage wins:

| Stage | Requirement | Ranked by |
|---|---|---|
| 1 | Tier 2 **and** family in `{chart, price_action}` **and** confirmed **and** aligned with trend | `(strength, confidence)` |
| 2 | Tier 1 **and** family ≠ `volume` **and** confirmed **and** aligned | `(strength, confidence)` |
| 3 | Any confirmed + aligned (volume now allowed) | `(tier==2, strength, confidence)` |
| 4 | Any aligned, forming allowed | `(tier==2, confirmed, strength, confidence)` |

"Aligned" means the pattern's direction equals the trend direction — **or** the
trend is `range`, in which case everything counts as aligned.

Net effect: a confirmed structural breakout beats a candlestick, a candlestick
beats a volume signal, and volume-only setups can only win when nothing else fired.

---

## 5. Filter — Confluence Score

### The model

Every symbol/timeframe pair gets a score from **0 to 100**, built from five
categories:

| # | Category | Max (default) | Measures |
|---|---|---|---|
| 1 | Trend / Structure | **30** | EMA & VWAP alignment, swing structure |
| 2 | Momentum | **25** | RSI regime, MACD histogram slope |
| 3 | Volume confirmation | **15** | relative volume vs 20-bar average |
| 4 | Candle trigger | **25** | the single best aligned pattern |
| 5 | Structural bonus | **5** | a confirmed Tier-2 chart/price-action/smc pattern exists |
| | **Total** | **100** | |

**The five "Max" values above are user-configurable defaults**, not hardcoded
constants — `Settings → Scoring` (`GET/PATCH /api/scoring-config`,
`storage/config/scoring.json`) lets a user re-weight the five categories. Each
category's internal formula (RSI bands, MACD split, RelVol tiers, pattern
strength→points, the contradiction/range penalties) is untouched by this —
only the category *ceilings* are configurable, and the total is always
rescaled back to 0–100 regardless of what the configured weights sum to
(`services/confluence_scorer.py:ScoringWeights`). Both scanners resolve the
current config once per scan request (not per symbol) and use it to fill in
the default `threshold` when the caller doesn't pass one explicitly.

> Volume is capped at 15 (reduced from 20) specifically to prevent volume-only
> setups from clearing the threshold on a spike alone.

### Category 1 — Trend / Structure (0–30)

A **voting** system. Five possible votes, each cast bullish or bearish:

| Vote | Bullish when | Bearish when |
|---|---|---|
| Price vs EMA20 | `close > ema20` | `close < ema20` |
| Price vs EMA50 | `close > ema50` | `close < ema50` |
| EMA cross | `ema20 > ema50` | `ema50 > ema20` |
| Price vs VWAP | `close > vwap` | `close < vwap` |
| Swing structure | new 10-bar high | new 10-bar low |

The swing vote is exclusive — a bar can be a new high **or** a new low, not both,
so at most 5 votes are cast. A bar that is neither abstains, but the vote still
counted as *available*.

Points are **normalised to the votes that were actually available**:

```
if bull_votes > bear_votes:   direction = bullish,  points = round(30 × bull_votes / votes_available)
elif bear_votes > bull_votes: direction = bearish,  points = round(30 × bear_votes / votes_available)
else:                         direction = range,    points = 5
```

A vote is unavailable when its indicator is (e.g. EMA50 needs 50 bars, VWAP
needs real volume). Normalising means a shorter history is no longer penalised
purely for having fewer indicators, and the category genuinely reaches its
stated **30**.

**This category sets the direction** used by every later category.

### VWAP is timeframe-aware

| Timeframe | VWAP |
|---|---|
| `5m` … `4h` | session-reset, grouped by the **exchange's** local session date |
| `1d`, `1wk`, `1mo` | rolling **20-bar** `Σ(typical_price × volume) / Σ(volume)` |
| no volume (indices) | `NaN` — the vote is skipped, not cast |

A session-reset VWAP is meaningless on daily-or-slower bars: each bar is its own
session, so `vwap` collapses to `(high + low + close) / 3` of that same bar and
the vote degenerates into "did the bar close in the upper part of its own
range". The rolling window fixes that. Intraday grouping uses the exchange's own
timezone so a US session (19:00–02:30 IST) is not split across IST midnight.

### Category 2 — Momentum (0–25)

Two components, summed then capped at 25.

**RSI (14)** — scored *relative to the trend direction*. Every band is
reachable, and the overbought/oversold edge is a **taper**, not a cliff:

| Trend | RSI band | Points |
|---|---|---|
| bullish | `45 < rsi < 70` | **12** — healthy |
| bullish | `70 ≤ rsi < 80` | **12 → 4**, linear taper |
| bullish | `rsi ≥ 80` | **4** — deeply overbought |
| bullish | `40 < rsi ≤ 45` | **8** — building |
| bullish | `rsi ≤ 40` | **4** — weak |
| bearish | `30 < rsi < 55` | **12** — healthy |
| bearish | `20 < rsi ≤ 30` | **12 → 4**, linear taper |
| bearish | `rsi ≤ 20` | **4** — deeply oversold |
| bearish | `55 ≤ rsi < 60` | **8** — rolling over |
| bearish | `rsi ≥ 60` | **4** |
| range | `40 < rsi < 60` | **8** |
| range | otherwise | **4** |

The old table had two unreachable 8-point branches, so the real contribution was
only 12, 4 or 0 — and a bullish setup at RSI 70.1 scored 4 while one at 69.9
scored 12. That 8-point step at a round number pushed genuine setups below the
threshold; it is now a 10-point-wide ramp.

**MACD histogram:**

| Condition | Points |
|---|---|
| bullish trend **and** histogram rising vs prior bar | **13** |
| bearish trend **and** histogram falling vs prior bar | **13** |
| otherwise, `abs(hist) > abs(prev_hist)` (expanding either way) | **6** |

Maximum realistic score is 12 + 13 = 25.

### Category 3 — Volume (0–15)

Relative volume = current bar volume ÷ 20-bar rolling mean.

| RelVol | Points | Label |
|---|---|---|
| ≥ 2.5× | **15** | Vol surge |
| ≥ 1.8× | **11** | High vol |
| ≥ 1.3× | **7** | Vol above avg |
| < 1.3× | **3** | — |

**Instruments with no volume (indices) are excluded from this category, not
given neutral points.** The remaining four categories (max 85) are **rescaled to
100**, so an index and a stock are judged on the same 0–100 basis and the same
threshold means the same thing for both. The card carries
`"volume_available": false` and the UI labels it `no vol`. The 7 volume patterns
still cannot fire on a volume-less instrument.

### Category 4 — Candle trigger (0–25)

Points come from the strength of the single pattern chosen by
`best_for_confluence`:

| Pattern strength | Points |
|---|---|
| 3 (strong) | **25** |
| 2 (medium) | **16** |
| 1 (weak) | **8** |
| none | **0** |

Alignment rules:

- Pattern direction **equals** trend direction → full points.
- Trend is `range` → `points − 8` (floored at 0).
- Pattern direction **contradicts** the trend (and strength ≥ 2) → **−15 penalty
  applied to the total**, with the reason "Pattern contradicts trend (penalised)".

### Category 5 — Structural bonus (0–5)

Flat **5 points** if *any* detected pattern is simultaneously:

- family in `{chart, price_action}`, **and**
- `tier == 2`, **and**
- `state == "confirmed"`

Otherwise 0. This rewards a real confirmed structural formation independently of
whichever pattern won Category 4.

**All three conditions must hold, which excludes more than it looks.** Patterns
that only ever emit `state: "forming"` can *never* earn this bonus — that rules
out Bull Flag, Bear Flag, both Pennants, Cup & Handle, High Tight Flag, Rounding
Bottom/Top, Ascending Channel and Descending Channel. The eligible set is:

- `52W High Breakout` (the only Tier-2 `price_action` pattern), plus
- Rectangle Breakout/Breakdown, Channel Breakout/Breakdown, Trendline
  Breakout/Breakdown, V Bottom, and
- the **confirmed** branches of H&S, Inverse H&S, Double/Triple Top & Bottom,
  Ascending/Descending Triangle, Symmetrical Triangle, Rising/Descending Wedge.

### Final direction

```
if trend == "range" and pattern direction is bullish/bearish:
    final_direction = pattern direction
else:
    final_direction = trend direction
```

So a range-bound stock printing a strong engulfing candle is reported with the
candle's direction.

### Total, threshold and buckets

```
total = trend + momentum + volume + candle + structural
if pattern.strength >= 2 and pattern contradicts trend:  total -= 15
total = clamp(total, 0, 100)
```

#### Practical maximum

| Category | Max | Reachable |
|---|---|---|
| Trend / Structure | 30 | 30 (normalised — all available votes agree) |
| Momentum | 25 | 25 (12 + 13) |
| Volume | 15 | 15 |
| Candle trigger | 25 | 25 |
| Structural bonus | 5 | 5 |
| **Total** | **100** | **100** |

100 is now a real ceiling. Under `pattern_mode=shape` the reachable maximum
drops to **70**, because Categories 4 and 5 collapse whenever the selected
pattern doesn't fire.

The **threshold** filter keeps only setups with `total >= threshold`.

| | Value |
|---|---|
| Default threshold | **65** |
| UI slider | min **40**, max **90**, step **5** |
| Slider guidance | ≥80 "Strong signals only" · ≥65 "Recommended — balanced quality" · <65 "Relaxed — shows more, lower quality" |

> **The default of 65 is now loose.** Correcting Categories 1–3 shifted the whole
> distribution up. On `india_nifty50` / `1d`, 70% of symbols clear 65 (it was
> 50%). See [threshold calibration](#threshold-calibration).

Display buckets (both scanners):

| Score | Colour | Meaning |
|---|---|---|
| **≥ 80** | emerald | strong / high-confidence |
| **65 – 79** | yellow | tradeable |
| **< 65** | red | only visible if you lowered the threshold |

The summary block reports `strong_80plus` as a dedicated count.

> There is no "Strong Buy / Buy / Hold" verdict string. The score plus the
> direction (`bullish` / `bearish` / `range`) **is** the verdict.

### Every card carries its own breakdown

```json
"confluence_score": 82,
"score_breakdown": { "trend": 30, "momentum": 25, "volume": 11, "candle": 16, "structural": 5 },
"volume_available": true,
"bars_used": 250
```

plus a `reasons` array of human-readable strings accumulated during scoring
("Price>EMA20", "RSI 58 healthy", "MACD hist rising", "Vol surge 2.7×",
"Pattern: Bull Flag", "Structural pattern confirmed", …).

### Scan diagnostics

A scan reports what it could **not** do, so "no setups" is distinguishable from
"half the universe failed to download":

| Field | Meaning |
|---|---|
| `scanned` | symbols actually attempted |
| `skipped_no_data` | every requested timeframe returned an empty frame |
| `skipped_insufficient_bars` | data arrived but no timeframe reached the 50-bar gate |
| `errors[]` | `{symbol, reason}`, capped at 50; `errors_truncated` reports the overflow |
| `cache_hit_rate` | bar-cache hits ÷ (hits + misses) for this scan |

Both UIs show a warning banner when `skipped_no_data / total_symbols > 5%`, with
an expandable per-symbol reason list.

The SSE `start` event echoes the **resolved** `universe`, `timeframes`,
`threshold` and `pattern_mode`, so the UI can display what was actually scanned
rather than what it thinks it asked for. Each `progress` event carries the
symbol's `status` (`ok` / `no_data` / `insufficient_bars` / `error`).

---

## 6. Equity Scanner (IN + US)

Route `/equity-scanner` · prefix `/api/equity-scanner` · positional only
(Daily / Weekly / Monthly) · trades the **cash stock**, no options.

### Universes (34 — 19 India, 15 US)

Currency and market are attached per universe — that is the whole IN/US switch.
`all_nse` counts as India and `all_us` as US, so the two market totals cover all 34.

**India — indices & broad market**

| Key | Label | Count |
|---|---|---|
| `india_indices` | NSE / BSE Indices | 6 |
| `india_nifty50` | Nifty 50 | 50 |
| `india_nifty100` | Nifty 100 | 100 |
| `india_nifty200` | Nifty 200 | 200 |
| `india_nifty500` | Nifty 500 | 500 |
| `india_midcap150` | Nifty Midcap 150 | 150 |
| `india_smallcap250` | Nifty Smallcap 250 | 250 |

**India — sectors**

`india_bank` (14) · `india_it` (10) · `india_pharma` (20) · `india_auto` (15) ·
`india_fmcg` (15) · `india_metal` (15) · `india_energy` (40) · `india_infra` (30) ·
`india_realty` (10) · `india_psu_bank` (12) · `india_media` (10)

**US — indices & broad market**

| Key | Label | Count |
|---|---|---|
| `us_indices` | US Major Indices | 4 |
| `us_top30` | US Top 30 | 30 |
| `us_dow30` | US Dow Jones 30 | 30 |
| `us_nasdaq100` | US NASDAQ 100 | 101 |
| `us_sp100` | US S&P 100 | ~100 |
| `us_sp500` | US S&P 500 | 503 |

**US — sectors**

`us_technology` (30) · `us_financials` (30) · `us_healthcare` (30) ·
`us_energy` (20) · `us_consumer_disc` (20) · `us_communication` (20) ·
`us_industrials` (20) · `us_consumer_staples` (20)

**All-market**

| Key | Label | Count |
|---|---|---|
| `all_nse` | All NSE Stocks | 2,377 (JSON) — refreshable to ~1,800 live via nselib |
| `all_us` | All US Listed | 536 |

Universes are lazy-loaded from `storage/universe/*.json` on demand. `all_nse` and
`all_us` must be populated with the Refresh button before first use.

### India vs US — the actual differences

| | India | US |
|---|---|---|
| Ticker | `SYMBOL.NS` (+ 2 overrides) | bare ticker, no suffix |
| Universe files | `NIFTY_*.json`, `ALL_NSE.json` | `US_*.json`, `ALL_US_LISTED.json` |
| Currency symbol | `₹` | `$` |
| Frontend locale | `en-IN` / INR | `en-US` / USD |
| Indices | `^NSEI`, `^NSEBANK`, `^BSESN`, … | `^GSPC`, `^NDX`, `^DJI`, `^RUT` |
| Data source | Yahoo Finance | Yahoo Finance |
| Timeframes | 1d / 1wk / 1mo | 1d / 1wk / 1mo |
| Scoring, patterns, thresholds | **identical** | **identical** |

There is **no** separate US scoring model, no US-specific patterns, and no market
-hours logic on either side.

### Trade plan (`services/equity_advisor.py`)

ATR-based, applied directly to the stock price:

```
risk = max(ATR × 1.5, spot × 0.003)      # at least 0.3% of price

BUY  (bullish):  entry = spot
                 SL    = spot − risk
                 T1    = spot + 1.5 × risk
                 T2    = spot + 2.5 × risk

SELL (bearish):  mirrored
```

- `rr` is **always 1.5** by construction (T1 is 1.5 × risk). It is a design
  parameter, not a measurement — the plan carries `rr_basis` saying so and the
  UI labels it `(fixed)`. There is deliberately **no R:R floor**: a gate that can
  never fire reads as a safety check without being one.
- Range-direction setups get **no plan** (`plan: null`).
- Exit rule text: trail SL to entry after T1; max hold **3–5 sessions**.

### Pattern backtest

Each card with a named pattern is backtested with the **registry** detector, on
the **card's own timeframe** (`services/scan_support.backtest_pattern`):

- Resolves the pattern to the registry entry able to emit it. Directional
  variants use their parent's detector and match on the variant id; legacy-only
  names map onto their registry equivalent (`Hammer / Pin Bar` → `Hammer`).
- Walks expanding windows over the trailing **260 bars** of that timeframe,
  starting at the pattern's own `min_bars`.
- Entry = close, `risk = max(ATR×1.5, entry×0.003)`.
- **Win** = T1 (`1.5 × risk`) touched within the next 5 bars *before* the stop.
- Returns `hit_rate` only when the sample is **≥ 5**.

All 73 registry patterns are now coverable — a Bull Flag card can show a hit
rate. Only the two Marubozu names have no registry detector at all.

The result is always self-describing, never a blank:

```json
"backtest": { "hit_rate": 0.62, "sample_size": 13, "timeframe": "1wk",
              "window_bars": 260, "detector": "Bull Flag", "reason": null }
```

When a hit rate cannot be produced, `hit_rate` is `null` and `reason` says why
("Only 2 prior occurrence(s) in 260 1wk bars — needs 5 for a hit rate"). The UI
renders `no hit rate` with the reason on hover.

`get_daily(sym, period=...)` now honours `period`; it previously accepted the
argument and ignored it, so callers asking for "6mo" silently got 1 year.

---

## 7. F&O Live Scanner (IN)

Route `/live-scanner` · prefix `/api/live-scanner` · India only · all 8
timeframes · produces an **option** trade plan.

### Universes (2)

| Key | Contents |
|---|---|
| `indices` | `NIFTY`, `BANKNIFTY`, `FINNIFTY`, `SENSEX`, `MIDCPNIFTY`, `BANKEX` (6) |
| `stocks` | Live NSE F&O-eligible equities |

`stocks` resolves in three steps:

1. `nselib.capital_market.fno_equity_list()` — full live list (200+), used if >50 symbols
2. `services/fno_data_service.get_fno_symbols()` — NSE REST + lot sizes
3. Static hardcoded list (~90 symbols) as final fallback

| `dynamic` | indices + F&O equities |

The default is **`stocks`**. Any unregistered universe string returns **HTTP 400**
naming it. (`top30` used to be the default and was never registered, so every
default scan silently fell back to `indices` — 6 symbols.)

### Option plan (`services/option_advisor.py`)

Same ATR skeleton as equity, expressed in options:

```
risk_pts = max(ATR × 1.5, spot × 0.003)
strike   = ATM  (spot rounded to the strike interval)
T1_spot  = spot ± 1.5 × risk_pts
T2_spot  = spot ± 2.5 × risk_pts
premium moves ≈ 0.5 (ATM delta) × spot move
```

Strike intervals:

| Symbol | Interval |
|---|---|
| NIFTY, FINNIFTY | 50 |
| BANKNIFTY, SENSEX, BANKEX | 100 |
| MIDCPNIFTY | 25 |
| Equity < ₹200 | 5 |
| Equity < ₹500 | 10 |
| Equity < ₹1,000 | 20 |
| Equity < ₹2,000 | 50 |
| Equity < ₹5,000 | 100 |
| Equity ≥ ₹5,000 | 200 |

- Bullish → **BUY CE**, bearish → **BUY PE**.
- **Range setups get an OTM premium-sell plan when IV supports it.** The router
  computes `iv_rank` from stored ATM-IV history
  (`fno_data_service.get_iv_rank`) and threads it through. When it cannot be
  computed (fewer than 30 daily IV snapshots) the plan is `null` **with a stated
  reason** on `plan_unavailable_reason`, instead of a silently failed gate. The
  UI prints the reason.
- **There is no R:R floor.** Both plans have an `rr` fixed by construction —
  directional `1.5` (`T1 = 1.5 × risk`) and premium-sell `0.33`
  (`(1 − 0.5) / (2.5 − 1)`; the premium cancels out entirely). A floor could
  therefore only ever be a gate that never fires. Each plan carries `rr_basis`
  explaining its number, and the UI labels it `(fixed)`. An R:R below 1 is
  inherent to a credit strategy — the edge there is decay probability, not
  payoff ratio.
- Premium levels assume a flat **0.5 ATM delta**
  (`t1_premium = entry + 0.5 × 1.5 × risk`). The plan declares this as
  `delta_assumption: 0.5` and the UI says the targets are approximate.
- `iv_note` warns when IV rank is elevated (>70, or >50 on a sub-75 score).
  These fire now that a real `iv_rank` reaches the advisor.
- Entry premium comes from the live option chain when available, otherwise an
  estimate; `liquidity_ok: false` flags an unverified strike.
- Expiry = nearest available from the chain. The frontend's
  `nearestWeeklyExpiry()` prefers the chain's own expiry and only falls back to
  weekday arithmetic as a last resort — NSE has moved weekly expiry off Thursday.
- **Liquidity is reported, not enforced.** `openInterest ≥ 500` and
  `totalTradedVolume ≥ 100` are checked; failure sets `liquidity_ok: false` and
  appends a warning, but the plan is still returned.
- Lot size comes from `services/lot_sizes.py`, the **single source of truth**;
  `frontend/lib/lot-sizes.generated.ts` is generated from it by
  `scripts/gen_lot_sizes.py` and `tests/test_trade_plans.py` fails the build on
  drift. Unlisted symbols still fall back to 500 but are flagged
  `lot_size_estimated: true`.

Option chain is fetched once per symbol per scan (`chain_cache`), falling back to
a synthetic Black-Scholes chain when NSE data is unavailable.

---

## 8. API reference

### Equity Scanner — `/api/equity-scanner`

| Method | Path | Purpose |
|---|---|---|
| GET | `/scan/stream` | SSE streaming scan |
| GET | `/patterns` | All 86 emitted patterns grouped by family, variants nested |
| GET | `/universe?market=IN\|US` | Universes with live counts |
| GET | `/universe-count/{key}` | Symbol count for one universe |
| POST | `/refresh-universe/{all_nse\|all_us}` | Rebuild a universe JSON |
| GET | `/chart-data?symbol=&interval=1d&bars=80` | OHLC candles for the mini chart |
| GET | `/health` | `{"status":"ok","scanner":"equity"}` |

**`GET /scan/stream` parameters**

| Param | Type | Default | Notes |
|---|---|---|---|
| `universe` | str | `india_nifty50` | key from the universe table; **400** if unregistered |
| `threshold` | int | `65` | minimum confluence score |
| `timeframes` | str | *absent* (all) | CSV subset of `1d,1wk,1mo`; **400** on an empty or unknown value |
| `pattern_names` | str | `""` (all) | CSV pattern ids or display names; **400** if any resolves to nothing |
| `pattern_mode` | str | `filter` | `filter` (hard post-filter, scores unchanged) or `shape` (legacy, lowers scores); **400** otherwise |
| `patterns` | str | `""` | CSV families — post-filter |
| `min_pattern_conf` | float | `0.0` | 0.0–1.0 confidence floor |

**400 response shape:** `{"error": "...", "field": "timeframes"}`. Both UIs
display `error` verbatim.

### F&O Scanner — `/api/live-scanner`

| Method | Path | Purpose |
|---|---|---|
| GET | `/scan` | Blocking scan, single JSON response |
| GET | `/scan/stream` | SSE streaming scan |
| GET | `/patterns` | All 86 emitted patterns grouped by family, variants nested |
| GET | `/universe` | `indices` / `stocks` / `dynamic` |
| GET | `/chart-data?symbol=&interval=1d&bars=80` | OHLC candles (handles `4h` via resample) |
| GET | `/health` | `{"status":"ok","scanner":"live"}` |

Same parameters as the equity scanner, except `universe` defaults to **`stocks`**
(accepting `indices` / `stocks` / `dynamic`) and `timeframes` accepts all eight
values.

### SSE event sequence

```
data: {"type":"start","total":50,"universe":"india_nifty50",
       "timeframes":["1d","1wk"],"threshold":65,"pattern_mode":"filter"}
data: {"type":"progress","symbol":"RELIANCE","found":2,"status":"ok","done":1,"total":50,"setups_so_far":2}
...
data: {"type":"enriching","setups":37}
data: {"type":"result","setups":[...],"summary":{...},"currency":"₹",...}
data: [DONE]
```

`start` echoes what the backend **resolved**, not what the client sent.

### Setup card shape

```json
{
  "symbol": "RELIANCE",
  "timeframe": "1d",
  "direction": "bullish",
  "confluence_score": 82,
  "score_breakdown": { "trend": 25, "momentum": 25, "volume": 11, "candle": 16, "structural": 5 },
  "pattern": "Bull Flag",
  "trigger_price": 1432.50,
  "atr": 24.30,
  "rel_vol": 1.85,
  "reasons": ["Price>EMA20", "EMA20>EMA50", "RSI 58 healthy", "MACD hist rising", "High vol 1.9×"],
  "plan": { "action": "BUY", "entry_price": 1432.50, "sl_price": 1396.05,
            "t1_price": 1487.18, "t2_price": 1523.63, "rr": 1.5,
            "rr_basis": "fixed: T1 = 1.5 × risk by construction",
            "risk_per_share": 36.45, "currency": "₹", "exit_rule": "..." },
  "backtest": { "hit_rate": 0.62, "sample_size": 13, "timeframe": "1d",
                "window_bars": 260, "detector": "Bull Flag", "reason": null },
  "volume_available": true,
  "bars_used": 250,
  "patterns": [ { "name": "Bull Flag", "pattern_id": "bull_flag", "parent_id": "bull_flag",
                  "family": "chart", "tier": 2, "direction": "bullish",
                  "strength": 2, "confidence": 0.78, "key_levels": {...},
                  "span_bars": 25, "state": "forming", "timeframe": "1d" } ],
  "breakout_state": "FRESH_BREAKOUT",
  "breakout_label": "Fresh breakout",
  "breakout_color": "#22c55e",
  "structural_score": 5
}
```

The F&O card is identical except `plan` is an option plan (`option_type`,
`strike`, `expiry`, `entry_premium`, `sl_premium`, `t1_premium`, `t2_premium`,
`lot_size`, `lot_size_estimated`, `delta_assumption`, `iv_rank`, `iv_note`,
`liquidity_ok`), it carries `plan_unavailable_reason` when `plan` is null, and it
carries an extra `source` field.

### Summary shape

```json
{ "total_symbols": 50, "unique_setups": 31, "total_setups": 47,
  "bullish": 29, "bearish": 15, "range": 3,
  "strong_80plus": 12, "by_timeframe": { "1d": 22, "1wk": 17, "1mo": 8 },
  "scanned": 50, "skipped_no_data": 1, "skipped_insufficient_bars": 2,
  "errors": [ { "symbol": "XYZ", "reason": "no data returned for any requested timeframe" } ],
  "cache_hit_rate": 0.33 }
```

---

## 9. Known quirks & caveats

Twenty caveats were listed here. The correctness pass resolved most of them;
what follows is what is genuinely still true.

### Threshold calibration

**The default threshold of 65 is now loose.** Fixing the trend normalisation,
the VWAP and the RSI bands shifted the whole distribution upward. Measured on
`india_nifty50`, no pattern filter:

| TF | n | min | p25 | median | p75 | max | ≥65 | ≥75 | ≥80 |
|---|---|---|---|---|---|---|---|---|---|
| `1d` | 50 | 9 | 61 | 70.5 | 88 | 100 | **70%** | 46% | 40% |
| `1wk` | 49 | 9 | 49 | 62 | 68 | 88 | 37% | 14% | 10% |
| `1mo` | 48 | 14 | 40 | 65 | 74.8 | 88 | 50% | 25% | 13% |

Before the fixes, `1d` was 50% ≥65 and 22% ≥80. The threshold has **not** been
changed — that is a product call. **Recommendation: raise the default to 75**,
which restores roughly the old selectivity (46% on `1d`) on the corrected scale,
and shift the slider guidance bands up by the same 10 points. Caveat: this is one
Nifty-50 snapshot on one day in a strong tape; re-measure across a wider universe
and a flatter market before committing.

### Still true

**1. Indicator lookbacks are fixed across all timeframes.** "EMA20" means 20
five-minute bars on `5m` and 20 months on `1mo`. This is a deliberate design
choice, now documented rather than implicit. The 50-bar minimum ensures every
scored card has the full indicator set.

**2. Liquidity is reported, not enforced.** A plan with `liquidity_ok: false` is
still returned, with a warning appended to `iv_note`.

**3. `rr` is a fixed design parameter, not a measurement.** Directional plans are
always 1.5, premium-sell plans always 0.33. Both carry `rr_basis` and the UI
labels them `(fixed)`. Targets are not derived from swing structure.

**4. Premium levels assume a flat 0.5 ATM delta.** Declared on the plan as
`delta_assumption`. They are a linear approximation, not option maths.

**5. Lot sizes need periodic refresh from NSE.** Python is the single source of
truth and TypeScript is generated from it, with a test that fails on drift — but
the *values* have not been reconciled against the live NSE contract master. NSE
revises them each expiry cycle.

**6. IV rank needs history to exist.** `get_iv_rank` requires 30 daily ATM-IV
snapshots. Until `append_daily_iv_snapshot()` has run that many times, range
setups get `plan: null` with that stated as the reason.

**7. The `all_nse` / `all_us` universes must be refreshed before first use.**

**8. Backtest hit rates are in-sample and unweighted.** They count prior
occurrences of the same pattern on the same instrument over 260 bars. Small
samples are common; anything under 5 returns `null` with a reason.

**9. Wyckoff patterns are context flags, not triggers.** Strength 1, confidence
0.32–0.35.

**10. The 4h session anchor is NSE-specific.** `resample_to_4h` defaults to an
09:15 origin. The F&O scanner is India-only so this is correct today, but the
function would need a different origin for another exchange.

### Resolved

For the record, these were the documented defects and are now fixed: the F&O
`top30` default universe; VWAP on daily/weekly/monthly; VWAP splitting a US
session at IST midnight; calendar-bucketed `4h`; indices getting free volume
points; the legacy-detector backtest covering only 7 names; `needs_confirmation`
and Tier 3; six unselectable pattern names; `Trendline Breakout`'s `min_bars`;
the two stale registry tests; the absence of a bar cache; the 95-point score
ceiling; the two unreachable RSI branches; silently-swallowed universe keys;
empty `timeframes` scanning everything; range setups never getting an option
plan; empty F&O 4h charts; the two divergent lot-size tables; the hardcoded
Thursday expiry; and `ALL_US_LISTED.json` never being read.

---

*Not financial advice. These are algorithmically identified setups, not
predictions. Always use defined stop-losses.*
