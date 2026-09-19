/**
 * Frontend correctness for the scanner fixes.
 *
 * Covers:
 *   3.4 — nearestWeeklyExpiry() prefers the live chain over hardcoded Thursday
 *   3.4 — the lot-size table comes from one generated source
 *   4.3 — F&O timeframes chart through the scanner that owns them
 */
import { describe, it, expect } from "vitest";
import {
  FALLBACK_WEEKLY_EXPIRY_DOW,
  nearestExpiryFromChain,
  nearestWeeklyExpiry,
} from "../lib/market-hours";
import { LOT_SIZES, DEFAULT_LOT_SIZE, getLotSize } from "../lib/fno-types";
import {
  cardMatchesPatterns,
  patternOptionsFromCards,
  cardMatchesTimeframe,
  timeframeOptionsFromCards,
  displayPatternFor,
} from "../components/scanner/MultiSelectFilter";

// ── 3.4 Expiry resolution ─────────────────────────────────────────────────────

describe("nearestWeeklyExpiry — chain first, weekday last", () => {
  it("uses the chain's expiry when one is supplied", () => {
    // A Tuesday, deliberately not the hardcoded Thursday.
    const chainExpiry = "31-Dec-2099";
    expect(nearestWeeklyExpiry(chainExpiry)).toBe(chainExpiry);
  });

  it("picks the nearest non-past expiry from a list", () => {
    const got = nearestWeeklyExpiry(["30-Dec-2099", "02-Jan-2100", "31-Dec-2099"]);
    expect(got).toBe("30-Dec-2099");
  });

  it("falls back to weekday arithmetic only when no chain expiry exists", () => {
    const fallback = nearestWeeklyExpiry();
    expect(fallback).toMatch(/^\d{2}-[A-Z][a-z]{2}-\d{4}$/);
    // Whatever it lands on must be the documented fallback weekday.
    const d = new Date(fallback.replaceAll("-", " "));
    expect(d.getDay()).toBe(FALLBACK_WEEKLY_EXPIRY_DOW);
  });

  it("treats empty / null chain input as no chain data", () => {
    expect(nearestExpiryFromChain(null)).toBeNull();
    expect(nearestExpiryFromChain([])).toBeNull();
    expect(nearestExpiryFromChain(undefined)).toBeNull();
  });

  it("returns something rather than nothing when every expiry is in the past", () => {
    expect(nearestExpiryFromChain(["01-Jan-2020"])).toBe("01-Jan-2020");
  });
});

// ── 3.4 Lot sizes ─────────────────────────────────────────────────────────────

describe("lot sizes — one generated source of truth", () => {
  it("re-exports the generated table rather than declaring its own", () => {
    expect(Object.keys(LOT_SIZES).length).toBeGreaterThan(50);
    expect(DEFAULT_LOT_SIZE).toBe(500);
  });

  it("carries the reconciled values for the seven symbols that had drifted", () => {
    // These are the entries where fno-types.ts disagreed with option_advisor.py.
    // Python is now the single source of truth; the TS file is generated from it.
    expect(LOT_SIZES.LT).toBe(150);
    expect(LOT_SIZES.MARUTI).toBe(75);
    expect(LOT_SIZES.POWERGRID).toBe(4700);
    expect(LOT_SIZES.ONGC).toBe(1925);
    expect(LOT_SIZES.NESTLEIND).toBe(40);
    expect(LOT_SIZES.TITAN).toBe(175);
    expect(LOT_SIZES.ADANIPORTS).toBe(1250);
  });

  it("getLotSize is case-insensitive and safe for unknown symbols", () => {
    expect(getLotSize("nifty")).toBe(LOT_SIZES.NIFTY);
    expect(getLotSize("NOT_LISTED")).toBe(1);
  });
});

// ── Post-scan pattern filter ──────────────────────────────────────────────────

const CARDS = [
  { pattern: "Bull Flag",         patterns: [{ name: "Bull Flag" }, { name: "NR7" }] },
  { pattern: "Bullish Engulfing", patterns: [{ name: "Bullish Engulfing" }] },
  { pattern: "Bull Flag",         patterns: [{ name: "Bull Flag" }] },
  { pattern: "None",              patterns: [] },
  { pattern: "Hammer / Pin Bar",  patterns: [] },   // legacy name, no rows
];

describe("patternOptionsFromCards", () => {
  it("lists distinct patterns, most common first, with counts", () => {
    const opts = patternOptionsFromCards(CARDS);
    expect(opts[0]).toEqual({ value: "Bull Flag", label: "Bull Flag", count: 2 });
    expect(opts.map((o) => o.value)).toContain("NR7");
    expect(opts.map((o) => o.value)).toContain("Hammer / Pin Bar");
  });

  it("never offers 'None' as a choice", () => {
    expect(patternOptionsFromCards(CARDS).map((o) => o.value)).not.toContain("None");
  });

  it("counts a card once even when the primary is also in patterns[]", () => {
    const opts = patternOptionsFromCards([
      { pattern: "NR7", patterns: [{ name: "NR7" }] },
    ]);
    expect(opts).toEqual([{ value: "NR7", label: "NR7", count: 1 }]);
  });

  it("handles an empty result set", () => {
    expect(patternOptionsFromCards([])).toEqual([]);
  });
});

describe("cardMatchesPatterns", () => {
  it("an empty selection means no filter, not 'show nothing'", () => {
    expect(CARDS.every((c) => cardMatchesPatterns(c, new Set()))).toBe(true);
  });

  it("matches on the displayed pattern", () => {
    const kept = CARDS.filter((c) => cardMatchesPatterns(c, new Set(["Bull Flag"])));
    expect(kept).toHaveLength(2);
  });

  it("matches on a non-primary detected pattern too", () => {
    const kept = CARDS.filter((c) => cardMatchesPatterns(c, new Set(["NR7"])));
    expect(kept).toHaveLength(1);
    expect(kept[0].pattern).toBe("Bull Flag");
  });

  it("is a union across multiple selections", () => {
    const kept = CARDS.filter((c) =>
      cardMatchesPatterns(c, new Set(["Bull Flag", "Bullish Engulfing"])));
    expect(kept).toHaveLength(3);
  });

  it("matches a legacy pattern name carried only on the card", () => {
    const kept = CARDS.filter((c) => cardMatchesPatterns(c, new Set(["Hammer / Pin Bar"])));
    expect(kept).toHaveLength(1);
  });

  it("drops cards with no pattern once a filter is active", () => {
    const kept = CARDS.filter((c) => cardMatchesPatterns(c, new Set(["Bull Flag"])));
    expect(kept.some((c) => c.pattern === "None")).toBe(false);
  });
});

// ── Post-scan timeframe filter ────────────────────────────────────────────────

const TF_CARDS = [
  { symbol: "A", timeframe: "1d" },
  { symbol: "B", timeframe: "1d" },
  { symbol: "C", timeframe: "1wk" },
  { symbol: "D", timeframe: "1mo" },
];

describe("timeframeOptionsFromCards", () => {
  it("lists distinct timeframes, most common first, with counts", () => {
    const opts = timeframeOptionsFromCards(TF_CARDS);
    // "1d" (count 2) leads; "1mo"/"1wk" tie at count 1 and fall back to alphabetical order.
    expect(opts).toEqual([
      { value: "1d",  label: "1d",  count: 2 },
      { value: "1mo", label: "1mo", count: 1 },
      { value: "1wk", label: "1wk", count: 1 },
    ]);
  });

  it("applies a page-supplied label formatter", () => {
    const opts = timeframeOptionsFromCards(TF_CARDS, (tf) => tf.toUpperCase());
    expect(opts.find((o) => o.value === "1d")?.label).toBe("1D");
  });

  it("handles an empty result set", () => {
    expect(timeframeOptionsFromCards([])).toEqual([]);
  });
});

describe("cardMatchesTimeframe", () => {
  it("an empty selection means no filter, not 'show nothing'", () => {
    expect(TF_CARDS.every((c) => cardMatchesTimeframe(c, new Set()))).toBe(true);
  });

  it("keeps only cards whose timeframe is selected", () => {
    const kept = TF_CARDS.filter((c) => cardMatchesTimeframe(c, new Set(["1d"])));
    expect(kept.map((c) => c.symbol)).toEqual(["A", "B"]);
  });

  it("is a union across multiple selected timeframes", () => {
    const kept = TF_CARDS.filter((c) => cardMatchesTimeframe(c, new Set(["1wk", "1mo"])));
    expect(kept.map((c) => c.symbol)).toEqual(["C", "D"]);
  });
});

// ── displayPatternFor — reproduces the "filtered but still shows Double Top"
// bug reported live: a card can match the Patterns filter via a non-headline
// pattern (e.g. Bearish FVG buried in patterns[]), and the row must then show
// that matched pattern instead of silently keeping the original headline. ──

describe("displayPatternFor", () => {
  const CARD = {
    pattern: "Double Top",
    patterns: [
      { name: "Double Top",  confidence: 0.78 },
      { name: "Bearish FVG", confidence: 0.55 },
    ],
  };

  it("leaves the headline pattern untouched when no filter is active", () => {
    expect(displayPatternFor(CARD, new Set())).toBe("Double Top");
  });

  it("leaves the headline pattern untouched when the headline itself is selected", () => {
    expect(displayPatternFor(CARD, new Set(["Double Top"]))).toBe("Double Top");
  });

  it("rewrites to the matched non-headline pattern — the reported bug", () => {
    expect(displayPatternFor(CARD, new Set(["Bearish FVG"]))).toBe("Bearish FVG");
  });

  it("picks the highest-confidence match when multiple patterns match", () => {
    const multi = {
      pattern: "Double Top",
      patterns: [
        { name: "Bearish FVG",  confidence: 0.55 },
        { name: "Rising Wedge", confidence: 0.72 },
      ],
    };
    expect(displayPatternFor(multi, new Set(["Bearish FVG", "Rising Wedge"]))).toBe("Rising Wedge");
  });

  it("falls back to the headline pattern if nothing in the selection actually matches", () => {
    // Shouldn't happen once cardMatchesPatterns has already filtered, but must
    // never throw or return undefined if called on an unrelated card.
    expect(displayPatternFor(CARD, new Set(["Some Other Pattern"]))).toBe("Double Top");
  });
});
