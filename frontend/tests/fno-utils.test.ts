/**
 * B + C frontend unit tests — fno-utils.ts (pure functions, no React).
 * Covers:
 *   P0-1 — getPcrSentiment() threshold correctness (5 thresholds from spec §6)
 *   P1-1 — mergeHistory() date alignment and null-safety
 */
import { describe, it, expect } from "vitest";
import {
  getPcrSentiment,
  mergeHistory,
  type PcrHistoryEntry,
  type VixHistoryEntry,
} from "../lib/fno-utils";

// ── PCR Sentiment (P0-1) ──────────────────────────────────────────────────────

describe("getPcrSentiment — spec §6 thresholds (P0-1)", () => {
  it("PCR > 1.3 → Strongly Bullish / success", () => {
    const r = getPcrSentiment(1.5);
    expect(r.label).toBe("Strongly Bullish");
    expect(r.variant).toBe("success");
  });

  it("PCR = 1.3 (boundary) → Mildly Bullish / success", () => {
    // 1.3 is NOT > 1.3, so it falls into the next bucket
    const r = getPcrSentiment(1.3);
    expect(r.label).toBe("Mildly Bullish");
    expect(r.variant).toBe("success");
  });

  it("PCR 1.0–1.3 → Mildly Bullish / success", () => {
    expect(getPcrSentiment(1.1).label).toBe("Mildly Bullish");
    expect(getPcrSentiment(1.0).label).toBe("Mildly Bullish");
  });

  it("PCR 0.7–1.0 exclusive → Neutral / default", () => {
    expect(getPcrSentiment(0.85).label).toBe("Neutral");
    expect(getPcrSentiment(0.7).label).toBe("Neutral");
    expect(getPcrSentiment(0.71).label).toBe("Neutral");
  });

  it("PCR 0.5–0.7 exclusive → Mildly Bearish / warning", () => {
    const r = getPcrSentiment(0.6);
    expect(r.label).toBe("Mildly Bearish");
    expect(r.variant).toBe("warning");
    expect(getPcrSentiment(0.5).label).toBe("Mildly Bearish");
  });

  it("PCR < 0.5 → Strongly Bearish / danger", () => {
    const r = getPcrSentiment(0.3);
    expect(r.label).toBe("Strongly Bearish");
    expect(r.variant).toBe("danger");
    expect(getPcrSentiment(0.0).label).toBe("Strongly Bearish");
  });

  it("all five thresholds produce distinct labels", () => {
    const labels = [1.5, 1.1, 0.85, 0.6, 0.3].map((v) => getPcrSentiment(v).label);
    expect(new Set(labels).size).toBe(5);
  });
});

// ── History Merge (P1-1) ──────────────────────────────────────────────────────

describe("mergeHistory — 60-day PCR + VIX alignment (P1-1)", () => {
  const pcr: PcrHistoryEntry[] = [
    { date: "2026-06-07", nifty_pcr: 1.1,  banknifty_pcr: 0.9 },
    { date: "2026-06-08", nifty_pcr: 1.2,  banknifty_pcr: 1.0 },
    { date: "2026-06-09", nifty_pcr: 0.95, banknifty_pcr: 0.8 },
  ];
  const vix: VixHistoryEntry[] = [
    { date: "2026-06-07", vix: 14.2 },
    { date: "2026-06-08", vix: 13.8 },
    // No VIX for 2026-06-09
  ];

  it("merges by date and fills nulls for missing entries", () => {
    const merged = mergeHistory(pcr, vix);
    expect(merged).toHaveLength(3);

    const jun9 = merged.find((p) => p.date === "2026-06-09");
    expect(jun9).toBeDefined();
    expect(jun9?.nifty_pcr).toBe(0.95);
    expect(jun9?.vix).toBeNull(); // VIX missing for this date
  });

  it("output is sorted oldest → newest (chronological)", () => {
    const merged = mergeHistory(pcr, vix);
    for (let i = 1; i < merged.length; i++) {
      expect(merged[i].date >= merged[i - 1].date).toBe(true);
    }
  });

  it("handles empty PCR array without throwing", () => {
    const merged = mergeHistory([], vix);
    expect(merged).toHaveLength(2);
    expect(merged[0].nifty_pcr).toBeNull();
    expect(merged[0].vix).not.toBeNull();
  });

  it("handles empty VIX array without throwing", () => {
    const merged = mergeHistory(pcr, []);
    expect(merged).toHaveLength(3);
    for (const p of merged) expect(p.vix).toBeNull();
  });

  it("handles both arrays empty", () => {
    expect(mergeHistory([], [])).toHaveLength(0);
  });

  it("each merged point has date, nifty_pcr, banknifty_pcr, vix fields", () => {
    const merged = mergeHistory(pcr, vix);
    for (const p of merged) {
      expect(p).toHaveProperty("date");
      expect(p).toHaveProperty("nifty_pcr");
      expect(p).toHaveProperty("banknifty_pcr");
      expect(p).toHaveProperty("vix");
    }
  });

  it("does not produce duplicate dates", () => {
    const merged = mergeHistory(pcr, vix);
    const dates = merged.map((p) => p.date);
    expect(new Set(dates).size).toBe(dates.length);
  });
});
