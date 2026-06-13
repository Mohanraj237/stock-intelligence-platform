/**
 * P0-2, P0-3, P2-3, P2-4 — Navigation completeness regression tests.
 *
 * These tests fail if any F&O page is removed from FO_NAV_ROUTES or FO_PREFIXES,
 * preventing silent regression of the orphaned-routes bug fixed in Workstream A.
 */
import { describe, it, expect } from "vitest";
import {
  FO_PREFIXES,
  FO_NAV_ROUTES,
  FO_BACK_ROUTES,
} from "../lib/nav-config";

/** The canonical set of 9 F&O pages every user must be able to reach from the nav. */
const REQUIRED_FO_PAGES = [
  // Previously visible
  "/live-scanner",
  "/option-chain",
  "/paper-trade",
  "/fo-learn",
  // Previously orphaned (P0-3 fix)
  "/fo-dashboard",
  "/oi-analytics",
  "/strategy-builder",
  // Previously completely missing from nav AND FO_PREFIXES (P0-2 + P2-3 + P2-4 fix)
  "/pcr-sentiment",
  "/expiry-heatmap",
] as const;

describe("FO_NAV_ROUTES completeness (P0-3)", () => {
  it("contains all 9 required F&O page routes", () => {
    const navHrefs = FO_NAV_ROUTES.map((r) => r.href);
    for (const required of REQUIRED_FO_PAGES) {
      expect(navHrefs, `Missing from FO_NAV_ROUTES: ${required}`).toContain(required);
    }
  });

  it("has exactly 9 F&O page routes (no silent additions or removals)", () => {
    expect(FO_NAV_ROUTES).toHaveLength(9);
  });

  it("has no duplicate hrefs in FO_NAV_ROUTES", () => {
    const hrefs = FO_NAV_ROUTES.map((r) => r.href);
    expect(new Set(hrefs).size).toBe(hrefs.length);
  });

  it("every route has a non-empty label", () => {
    for (const r of FO_NAV_ROUTES) {
      expect(r.label.trim().length, `Empty label for ${r.href}`).toBeGreaterThan(0);
    }
  });

  it("every route belongs to a valid group", () => {
    const VALID_GROUPS = new Set(["Market", "Scanners", "Options", "Risk", "Learn"]);
    for (const r of FO_NAV_ROUTES) {
      expect(VALID_GROUPS, `Invalid group "${r.group}" for ${r.href}`).toContain(r.group);
    }
  });
});

describe("FO_PREFIXES completeness (P2-3, P2-4)", () => {
  it("contains all 9 required F&O page prefixes", () => {
    for (const required of REQUIRED_FO_PAGES) {
      expect(
        Array.from(FO_PREFIXES),
        `Missing from FO_PREFIXES: ${required}`,
      ).toContain(required);
    }
  });

  it("every FO_NAV_ROUTES href is in FO_PREFIXES (no orphan routes)", () => {
    const prefixSet = new Set(FO_PREFIXES as readonly string[]);
    for (const r of FO_NAV_ROUTES) {
      expect(
        prefixSet.has(r.href),
        `"${r.href}" is in FO_NAV_ROUTES but missing from FO_PREFIXES — ` +
          "the sidebar will not auto-switch to F&O mode when navigating here directly.",
      ).toBe(true);
    }
  });

  it("has no duplicate entries in FO_PREFIXES", () => {
    const arr = Array.from(FO_PREFIXES);
    expect(new Set(arr).size).toBe(arr.length);
  });
});

describe("FO_BACK_ROUTES (utility links)", () => {
  it("contains back-to-equity and settings links", () => {
    const hrefs = FO_BACK_ROUTES.map((r) => r.href);
    expect(hrefs).toContain("/dashboard");
    expect(hrefs).toContain("/settings");
  });

  it("back routes are NOT in FO_PREFIXES (they are equity links)", () => {
    const prefixSet = new Set(FO_PREFIXES as readonly string[]);
    for (const r of FO_BACK_ROUTES) {
      expect(
        prefixSet.has(r.href),
        `"${r.href}" is a back-link and should not be in FO_PREFIXES`,
      ).toBe(false);
    }
  });
});
