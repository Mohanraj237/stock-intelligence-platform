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
              └─► run_detectors(df, tf)    69 pattern detectors, TF-gated
                    └─► score(...)         confluence 0–100
                          └─► threshold?   keep if total >= threshold
                                └─► build_equity_plan()  |  build_plan()  (options)
```

Key modules:

| File | Role |
|---|---|
| `services/intraday_data.py` | Yahoo Finance fetch, ticker mapping, universes, TF→range map |
| `services/confluence_scorer.py` | Indicators + the 0–100 score |
| `services/pattern_registry.py` | 69 pattern detectors (the modern engine) |
| `services/pattern_detector.py` | 10-pattern legacy fallback detector |
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
Timeout 15s. On total failure an empty DataFrame is returned and the symbol is
silently skipped.

### Ticker resolution (`_ticker`, `intraday_data.py:369`)

Resolution order:

1. **Index map** — `NIFTY→^NSEI`, `BANKNIFTY→^NSEBANK`, `FINNIFTY→NIFTY_FIN_SERVICE.NS`, `SENSEX→^BSESN`, `MIDCPNIFTY→NIFTY_MID_SELECT.NS`, `BANKEX→BSE-BANK.BO`, `INDIAVIX→^INDIAVIX`, `SP500→^GSPC`, `NASDAQ100→^NDX`, `DOW→^DJI`, `RUSSELL2000→^RUT`, `NASDAQ→^IXIC`
2. **Equity overrides** — `TATAMOTORS→TMCV.NS`, `ETERNAL→ETERNAL.NS`
3. **US symbols** — used **as-is, no suffix**. The US set is built at import time by eagerly loading every `storage/universe/US_*.json`
4. **Default** — append `.NS` (NSE equity)

> This is the single branch point between India and US. A symbol is "US" purely
> because it appears in a `US_*.json` file. If a US ticker is missing from those
> files it silently becomes `TICKER.NS` and returns no data.

### Incomplete-bar guard (`_drop_incomplete_trailing_bar`)

The last bar is dropped when it is not a fully-closed period, because pattern
detectors key off the final bar and get fooled by partial ones:

- **Intraday stub** — `volume == 0` and `open == high == low == close`. Trivially
  looks like the narrowest bar possible, so NR7/Doji/Inside-Bar fire constantly.
- **Still-forming weekly/monthly** — for `1wk`/`1mo`, if time since the last bar
  is `< 0.9 ×` the typical inter-bar gap, the bar is still forming and is dropped.

### Caching & market hours

- **No persistent cache.** Every scan re-fetches from Yahoo. The only caches are
  per-request dicts (`daily_cache`, `chain_cache`) that dedupe work *within* one scan.
- **No market-hours gating.** Scans run any time; off-hours simply return the
  last closed bars.

---

## 3. Filter — Timeframe

### What the filter does

The timeframe filter is a **fetch-level** filter, not a display filter. Unselected
timeframes are **never requested from Yahoo at all**, so deselecting timeframes
cuts external API calls (and scan time) proportionally.

Wire format: comma-separated, e.g. `timeframes=1d,1wk`. Empty string = **all**.
Values not in the scanner's allowed set are silently dropped; if nothing valid
remains the filter falls back to "all".

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

**`4h` has no native Yahoo interval.** It is resampled from `1h` bars using plain
calendar 4-hour buckets (`resample("4h")`, aggregating first/max/min/last/sum) —
**not** market-session aligned. If you select `4h` without `1h`, `1h` is still
fetched internally as a dependency and then discarded.

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

**Minimum 20 bars** to score at all — below that the symbol/TF is skipped.
Practically this only bites on `1mo` for recently-listed symbols.

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

### Two independent pattern filters

This is the most commonly misunderstood part of the scanner. There are **two**
pattern filters and they work at different stages:

| Filter | Param | Stage | Effect |
|---|---|---|---|
| **Pattern names** | `pattern_names` | **Scoring time** | Only the named patterns may contribute to the *Candle Trigger* (0–25) and *Structural bonus* (0–5) score categories |
| **Pattern families** | `patterns` | **After scoring** | Drops finished cards where no detected pattern is in the named families |

**`pattern_names` shapes the score at the source.** If you select only
"Bullish Engulfing", every other pattern is stripped before Category 4 is
computed. A stock that would have scored 88 on a Bull Flag now scores 88 − 16 = 72
from trend/momentum/volume alone.

Important: a card that still clears the threshold on trend/momentum/volume alone
— with *none* of your selected patterns firing — **is still returned**. This is
deliberate: the scanner treats it as a legitimate setup that simply lacks your
preferred trigger. `pattern_names` is not re-applied as a hard post-filter.

**`patterns` (families) is a hard post-filter.** Cards with no matching pattern
are dropped entirely. Valid families: `candlestick`, `price_action`, `volume`,
`chart`, `harmonic`. Matching is case-insensitive.

There is also **`min_pattern_conf`** (0.0–1.0, default 0.0) — drops cards where no
detected pattern reaches that confidence.

> **Neither `patterns` nor `min_pattern_conf` is reachable from the UI.** Both
> scanner pages only ever send `pattern_names`. The family and confidence filters
> are API-only.

> **`pattern_names` matches the *emitted* name, exactly and case-sensitively.**
> Five detectors emit directional variants that are not in the registry list
> served by `GET /patterns`, so selecting the registry name does **not** keep
> them — selecting `Inside Bar` drops every `Inside Bar Breakout` hit. See
> [caveat 8](#9-known-quirks--caveats).

When a card survives the family filter via a *non-primary* pattern, the displayed
`card["pattern"]` is rewritten to the highest-confidence matched pattern, so the
UI always shows a pattern you actually selected.

### Legacy fallback

When **no** `pattern_names` filter is active and the registry finds nothing, the
scorer falls back to a legacy 10-pattern single-bar detector
(`services/pattern_detector.py`): Morning Star, Evening Star, Inside Bar
Breakout/Breakdown, Bullish/Bearish Engulfing, Hammer / Pin Bar, Shooting Star,
Bullish/Bearish Marubozu.

This fallback is **skipped whenever `pattern_names` is set**, because it ignores
the filter and would silently defeat your selection.

### The registry: 69 patterns

| Family | Count | Tier | Character |
|---|---|---|---|
| `candlestick` | 23 | 1 | 1–3 bar Japanese candle shapes |
| `price_action` | 12 | 1 (11) + 2 (1) | bar structure & location context |
| `volume` | 7 | 1 | volume-relative signals |
| `chart` | 25 | 2 | classic multi-bar formations |
| `harmonic` | 2 | 2 | Wyckoff accumulation/distribution |

**Tier** — Tier 1 = fast/local signals detectable on few bars. Tier 2 = structural
multi-bar formations. Tier 3 is documented in the code but **no Tier-3 patterns
exist**; `run_detectors` defaults to `max_tier=2` anyway.

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
| Trendline Breakout | bull | 2 | 30 (**35 effective**) | Fitted rising support line; close breaks 0.5% above it **now** but not 5 bars ago |
| ↳ Trendline Breakdown | bear | 2 | 30 (**35 effective**) | Mirror on a falling resistance line |
| Ascending Channel | bull | 2 | 30 | Both slopes positive & parallel; price inside. `forming`, conf 0.68 |
| Descending Channel | bear | 2 | 30 | Mirror. `forming`, conf 0.68 |

#### Harmonic / Wyckoff (2) — Tier 2, `_C` timeframes

| Pattern | Dir | Str | Min bars | Rule |
|---|---|---|---|---|
| Wyckoff Accumulation | bull | 1 | 40 | 40-bar range between 3% and 15%, with volume drying up in the last 20 bars. Conf **0.35**, `forming` |
| Wyckoff Distribution | bear | 1 | 40 | Same, plus price in the upper half of the range. Conf **0.32**, `forming` |

> Both are strength 1 (8 pts) with very low confidence — they are context flags,
> not triggers.

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

| # | Category | Max | Measures |
|---|---|---|---|
| 1 | Trend / Structure | **30** | EMA & VWAP alignment, swing structure |
| 2 | Momentum | **25** | RSI regime, MACD histogram slope |
| 3 | Volume confirmation | **15** | relative volume vs 20-bar average |
| 4 | Candle trigger | **25** | the single best aligned pattern |
| 5 | Structural bonus | **5** | a confirmed Tier-2 chart/price-action pattern exists |
| | **Total** | **100** | |

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
so at most 5 votes are cast.

```
if bull_votes > bear_votes:   direction = bullish,  points = min(30, bull_votes × 5)
elif bear_votes > bull_votes: direction = bearish,  points = min(30, bear_votes × 5)
else:                         direction = range,    points = 5
```

Votes are skipped when the indicator is unavailable (e.g. EMA50 needs 50 bars),
so short histories mechanically score lower here.

> **The 30-point cap is never reached.** With at most 5 votes × 5 points, this
> category tops out at **25**. See [practical maximum](#practical-maximum).

**This category sets the direction** used by every later category.

### Category 2 — Momentum (0–25)

Two components, summed then capped at 25.

**RSI (14)** — scored *relative to the trend direction*:

| Trend | RSI band | Points |
|---|---|---|
| bullish | `45 < rsi < 70` | **12** — healthy |
| bullish | `rsi ≥ 70` | **4** — overbought |
| bullish | `rsi > 50` * | **8** |
| bearish | `30 < rsi < 55` | **12** — healthy |
| bearish | `rsi ≤ 30` | **4** — oversold |
| bearish | `rsi < 50` * | **8** |
| range | `40 < rsi < 60` | **8** |
| range | otherwise | **4** |

\* **Dead branches.** The preceding bands already cover every value these could
match, so the 8-point RSI award is unreachable in both the bullish and bearish
paths. Effective RSI contribution is only 12, 4, or 0.

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
| no volume data (indices) | **6** | neutral |

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

The advertised ceiling is 100, but Category 1 caps at 25 rather than 30, so the
real ceiling is:

| Category | Stated max | Reachable max |
|---|---|---|
| Trend / Structure | 30 | **25** (5 votes × 5) |
| Momentum | 25 | 25 (12 + 13) |
| Volume | 15 | 15 |
| Candle trigger | 25 | 25 |
| Structural bonus | 5 | 5 |
| **Total** | **100** | **95** |

A score of 96–100 is unreachable. Treat 90+ as the top of the scale.

The **threshold** filter keeps only setups with `total >= threshold`.

| | Value |
|---|---|
| Default threshold | **65** |
| UI slider | min **40**, max **90**, step **5** |
| Slider guidance | ≥80 "Strong signals only" · ≥65 "Recommended — balanced quality" · <65 "Relaxed — shows more, lower quality" |

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
"score_breakdown": { "trend": 25, "momentum": 25, "volume": 11, "candle": 16, "structural": 5 }
```

plus a `reasons` array of human-readable strings accumulated during scoring
("Price>EMA20", "RSI 58 healthy", "MACD hist rising", "Vol surge 2.7×",
"Pattern: Bull Flag", "Structural pattern confirmed", …).

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

- `rr` is **always 1.5** by construction (T1 is 1.5 × risk).
- Range-direction setups get **no plan** (`plan: null`).
- Exit rule text: trail SL to entry after T1; max hold **3–5 sessions**.

### Pattern backtest

Each card with a named pattern is backtested against daily data using the
**legacy** detector:

- Walks bars `2 … len−6`, finds prior occurrences of the same pattern+direction.
- Entry = close, `risk = max(ATR×1.5, entry×0.003)`.
- **Win** = T1 (`1.5 × risk`) touched within the next 5 bars *before* the stop.
- Requires ≥30 daily bars; returns `hit_rate` only when the sample is **≥ 5**,
  otherwise `{"hit_rate": null, "note": "Low sample — unproven"}`.

Two things to know before trusting this number:

**It is not 6 months.** The call is `get_daily(sym, period="6mo")`, but
`get_daily` ignores `period` and delegates to `get_ohlcv(sym, "1d")`, which uses
`range=1y`. The backtest window is ~250 daily bars.

**It only works for 7 pattern names.** The card's `pattern` comes from the
registry, but the backtest walks the legacy detector, so a hit rate can only be
produced where the two name sets overlap: `Morning Star`, `Evening Star`,
`Bullish Engulfing`, `Bearish Engulfing`, `Shooting Star`, `Inside Bar Breakout`,
`Inside Bar Breakdown`. Everything else yields `sample_size: 0` → `backtest: null`.
Note registry `Hammer` does **not** match legacy `Hammer / Pin Bar`.

The same backtest runs in the F&O scanner, also against daily bars regardless of
the card's own timeframe.

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

> Any other universe string — **including the default `top30`** — falls through
> to `indices`. See [caveats](#9-known-quirks--caveats).

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
- **Range setups always get `plan: null`.** The range path is an OTM *sell* plan
  that bails out when `iv_rank < 40`, and the router never passes `iv_rank`, so
  it is always the 30.0 default. The UI shows "Option plan unavailable".
- **R:R floor is 1.3** — plans below it are rejected. Since `rr` is hardcoded to
  1.5, this gate never fires for directional setups.
- Premium levels assume a flat **0.5 ATM delta**: `t1_premium = entry + 0.5 × 1.5 × risk`.
- `iv_note` warnings are also dead for the same reason (they need `iv_rank > 50`).
- Entry premium comes from the live option chain when available, otherwise an
  estimate; `liquidity_ok: false` flags an unverified strike.
- Expiry = nearest available from the chain.
- `iv_note` warns when IV rank is elevated.

- **Liquidity is reported, not enforced.** `openInterest ≥ 500` and
  `totalTradedVolume ≥ 100` are checked; failure sets `liquidity_ok: false` and
  appends a warning, but the plan is still returned.
- Lot size comes from a static table, defaulting to **500** for unlisted symbols.

Option chain is fetched once per symbol per scan (`chain_cache`), falling back to
a synthetic Black-Scholes chain when NSE data is unavailable.

---

## 8. API reference

### Equity Scanner — `/api/equity-scanner`

| Method | Path | Purpose |
|---|---|---|
| GET | `/scan/stream` | SSE streaming scan |
| GET | `/patterns` | All 69 patterns grouped by family |
| GET | `/universe?market=IN\|US` | Universes with live counts |
| GET | `/universe-count/{key}` | Symbol count for one universe |
| POST | `/refresh-universe/{all_nse\|all_us}` | Rebuild a universe JSON |
| GET | `/chart-data?symbol=&interval=1d&bars=80` | OHLC candles for the mini chart |
| GET | `/health` | `{"status":"ok","scanner":"equity"}` |

**`GET /scan/stream` parameters**

| Param | Type | Default | Notes |
|---|---|---|---|
| `universe` | str | `india_nifty50` | key from the universe table |
| `threshold` | int | `65` | minimum confluence score |
| `timeframes` | str | `""` (all) | CSV subset of `1d,1wk,1mo` |
| `pattern_names` | str | `""` (all) | CSV exact names — shapes the score |
| `patterns` | str | `""` | CSV families — post-filter |
| `min_pattern_conf` | float | `0.0` | 0.0–1.0 confidence floor |

### F&O Scanner — `/api/live-scanner`

| Method | Path | Purpose |
|---|---|---|
| GET | `/scan` | Blocking scan, single JSON response |
| GET | `/scan/stream` | SSE streaming scan |
| GET | `/patterns` | All 69 patterns grouped by family |
| GET | `/universe` | `indices` / `stocks` / `dynamic` |
| GET | `/chart-data?symbol=&interval=1d&bars=80` | OHLC candles (handles `4h` via resample) |
| GET | `/health` | `{"status":"ok","scanner":"live"}` |

Same parameters as the equity scanner, except `universe` defaults to `top30` and
`timeframes` accepts all eight values.

### SSE event sequence

```
data: {"type":"start","total":50,"universe":"india_nifty50"}
data: {"type":"progress","symbol":"RELIANCE","found":2,"done":1,"total":50,"setups_so_far":2}
...
data: {"type":"enriching","setups":37}
data: {"type":"result","setups":[...],"summary":{...},"currency":"₹",...}
data: [DONE]
```

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
            "risk_per_share": 36.45, "currency": "₹", "exit_rule": "..." },
  "backtest": { "hit_rate": 0.62, "sample_size": 13 },
  "patterns": [ { "name": "Bull Flag", "family": "chart", "tier": 2, "direction": "bullish",
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
`lot_size`, `iv_note`, `liquidity_ok`) and it carries an extra `source` field.

### Summary shape

```json
{ "total_symbols": 50, "unique_setups": 31, "total_setups": 47,
  "bullish": 29, "bearish": 15, "range": 3,
  "strong_80plus": 12, "by_timeframe": { "1d": 22, "1wk": 17, "1mo": 8 } }
```

---

## 9. Known quirks & caveats

These are real behaviours in the current code — worth knowing before you trust a
number.

**1. F&O default universe is wrong.** Both `/scan` and `/scan/stream` default to
`universe="top30"`, which is not a registered preset, so `_resolve_symbols` falls
back to `indices` (6 symbols). Pass `universe=stocks` explicitly to scan equities.

**2. VWAP on Daily/Weekly/Monthly is not a VWAP.** `_vwap_daily` resets per
calendar date. On daily-or-slower bars each bar is its own session, so
`vwap == (high + low + close) / 3` of that same bar. The "Price > VWAP" trend vote
therefore reduces to "did the bar close in the upper part of its own range" — a
within-bar test, not a session-volume measure. **This affects every equity
scanner result**, since the equity scanner only uses 1d/1wk/1mo.

**3. VWAP on US intraday splits mid-session.** All timestamps are converted to
`Asia/Kolkata` before grouping. A US session (19:00–02:30 IST) crosses IST
midnight, so intraday VWAP would reset mid-session. Not currently reachable —
the equity scanner has no intraday timeframes — but it is a live trap if
intraday is ever enabled for US.

**4. `4h` is calendar-bucketed, not session-aligned.** Resampled from 1h with
`resample("4h")`, so buckets do not line up with the 09:15–15:30 IST session.

**5. Indices get a free 6 volume points.** With no volume data the Volume
category returns a neutral 6 rather than being excluded, and all 7 volume
patterns are unavailable. Index setups are scored on a slightly different basis
than stock setups.

**6. Backtest uses the legacy detector and covers only 7 pattern names.** A Bull
Flag card can never show a hit rate. Hit rates are always computed on daily bars
regardless of the card's timeframe, and the window is ~1 year, not the "6mo" the
call site claims. See [Pattern backtest](#pattern-backtest).

**7. `needs_confirmation` and Tier 3 are dead.** `needs_confirmation` is set on 15
registry entries but never read. No Tier-3 patterns exist despite the code
documenting them.

**8. Six emitted pattern names are unselectable.** `Inside Bar Breakout`,
`Inside Bar Breakdown`, `Breakdown Retest`, `Rectangle Breakdown`,
`Channel Breakdown`, `Trendline Breakdown` are emitted by detectors but are not
in `GET /patterns`. Because `pattern_names` matches the emitted name exactly,
selecting `Inside Bar` silently discards every `Inside Bar Breakout` hit, and the
bearish breakdown variants cannot be selected at all.

Also unselectable: `Hammer / Pin Bar`, `Bullish Marubozu`, `Bearish Marubozu` —
these exist only in the legacy fallback detector, so they can appear in a card's
`pattern` field but never in `patterns[]` and never in the picker.

**9. `Trendline Breakout` needs 35 bars, not 30.** Its registered `min_bars` is 30
but an internal guard requires `30 + 5`.

**10. Two registry tests appear stale.** `test_tier3_families_present` asserts
membership in what is now an empty set, and `test_tier1_preferred_over_tier2`
contradicts the Stage-1-first ordering in `best_for_confluence`.

**11. Every scan re-fetches everything.** No persistent cache. A 503-symbol
S&P 500 scan across 3 timeframes is ~1,500 Yahoo requests and takes ~10 minutes.

**12. The score ceiling is 95, not 100.** Category 1 caps at 25 of its stated 30.

**13. Two RSI branches are unreachable.** The 8-point bullish and bearish RSI
awards can never fire; effective RSI contribution is 12, 4, or 0.

**14. Unknown universe keys fail silently.** The equity scanner falls back to
`india_nifty50`, the F&O scanner to `indices` — no error is raised.

**15. Deselecting every timeframe scans all of them.** An empty `timeframes`
string is treated as "no filter". The F&O UI warns but does not disable the
button.

**16. Range setups never get an F&O option plan** (`iv_rank` is hardcoded to 30,
below the range path's 40 floor), and `iv_note` warnings never fire for the same
reason.

**17. F&O 4h charts render empty.** `CandleChart` calls
`/api/equity-scanner/chart-data`, which has no `4h` branch, so the live scanner's
own 4h-resampling endpoint is dead code and Yahoo rejects the raw `4h` interval.

**18. Two divergent lot-size tables.** `option_advisor.LOT_SIZES` (Python) and
`fno-types.ts` (TypeScript) disagree on LT, MARUTI, POWERGRID, ONGC, NESTLEIND,
TITAN and ADANIPORTS.

**19. `nearestWeeklyExpiry()` hardcodes Thursday**, which NSE has since moved.

**20. `ALL_US_LISTED.json` is not read by the ticker resolver.** `_build_us_symbols`
globs `US_*.json`, which that filename does not match. Coverage is identical only
because the same sources are re-merged — a symbol added to `ALL_US_LISTED.json`
alone would get `.NS` appended and fail to fetch.

---

*Not financial advice. These are algorithmically identified setups, not
predictions. Always use defined stop-losses.*
