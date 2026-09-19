/**
 * Frontend correctness for the confluence-scoring config feature (Settings → Scoring).
 *
 * Covers:
 *   - scoringWeightsTotal() normalization display math
 *   - api.ts scoringConfig / patchScoringConfig / resetScoringConfig client calls
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { DEFAULT_SCORING_CONFIG, scoringWeightsTotal, type ScoringConfig } from "../lib/types";

describe("scoringWeightsTotal", () => {
  it("sums to 100 for the default weights", () => {
    expect(scoringWeightsTotal(DEFAULT_SCORING_CONFIG)).toBe(100);
  });

  it("reflects a custom weighting that does not sum to 100", () => {
    const custom: ScoringConfig = {
      trend_weight: 40, momentum_weight: 15, volume_weight: 10,
      candle_weight: 30, structural_weight: 5, default_threshold: 70,
    };
    expect(scoringWeightsTotal(custom)).toBe(100);

    const nonHundred: ScoringConfig = { ...custom, trend_weight: 60 };
    expect(scoringWeightsTotal(nonHundred)).toBe(120);
  });

  it("ignores default_threshold — only the 5 category weights count", () => {
    const cfg: ScoringConfig = { ...DEFAULT_SCORING_CONFIG, default_threshold: 999 };
    expect(scoringWeightsTotal(cfg)).toBe(100);
  });

  it("is zero when every weight is zero", () => {
    const zero: ScoringConfig = {
      trend_weight: 0, momentum_weight: 0, volume_weight: 0,
      candle_weight: 0, structural_weight: 0, default_threshold: 65,
    };
    expect(scoringWeightsTotal(zero)).toBe(0);
  });
});

describe("api.ts scoring-config client functions", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    global.fetch = vi.fn(async () =>
      new Response(JSON.stringify(DEFAULT_SCORING_CONFIG), { status: 200 })
    ) as unknown as typeof fetch;
  });

  afterEach(() => {
    global.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it("scoringConfig() issues a GET to /api/scoring-config", async () => {
    const { api } = await import("../lib/api");
    await api.scoringConfig();
    const [urlArg, init] = (global.fetch as any).mock.calls[0];
    expect(String(urlArg)).toContain("/api/scoring-config");
    expect(init?.method ?? "GET").toBe("GET");
  });

  it("patchScoringConfig() issues a PATCH with the partial body", async () => {
    const { api } = await import("../lib/api");
    await api.patchScoringConfig({ trend_weight: 45 });
    const [urlArg, init] = (global.fetch as any).mock.calls[0];
    expect(String(urlArg)).toContain("/api/scoring-config");
    expect(init.method).toBe("PATCH");
    expect(JSON.parse(init.body)).toEqual({ trend_weight: 45 });
  });

  it("resetScoringConfig() issues a POST to /api/scoring-config/reset", async () => {
    const { api } = await import("../lib/api");
    await api.resetScoringConfig();
    const [urlArg, init] = (global.fetch as any).mock.calls[0];
    expect(String(urlArg)).toContain("/api/scoring-config/reset");
    expect(init.method).toBe("POST");
  });
});
