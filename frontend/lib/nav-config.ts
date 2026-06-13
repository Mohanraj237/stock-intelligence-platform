/**
 * Navigation constants extracted for testability.
 * Sidebar imports these and adds icon components on top.
 * Tests import this file directly — no React dependency allowed here.
 */

/**
 * URL prefixes that trigger F&O sidebar mode when a user navigates directly to
 * any of these pages (so the correct nav is shown without a manual toggle).
 * Must include every href that appears in FO_NAV_ROUTES.
 */
export const FO_PREFIXES = [
  "/live-scanner",
  "/option-chain",
  "/paper-trade",
  "/fo-learn",
  "/fo-dashboard",
  "/oi-analytics",
  "/strategy-builder",
  "/pcr-sentiment",
  "/expiry-heatmap",
] as const;

export type FoPrefix = (typeof FO_PREFIXES)[number];

/** Shape of a single nav entry (without the React icon component). */
export interface FoNavRoute {
  href: string;
  label: string;
  group: "Market" | "Scanners" | "Options" | "Risk" | "Learn";
}

/**
 * Every F&O page the sidebar must surface, in display order.
 * Grouped by: Market → Scanners → Options → Risk → Learn.
 */
export const FO_NAV_ROUTES: FoNavRoute[] = [
  // ── Market ───────────────────────────────────────────────────────────────────
  { group: "Market",   href: "/fo-dashboard",    label: "F&O Overview"     },
  { group: "Market",   href: "/pcr-sentiment",   label: "PCR & Sentiment"  },
  // ── Scanners ──────────────────────────────────────────────────────────────────
  { group: "Scanners", href: "/live-scanner",    label: "Live Scanner"     },
  // ── Options ───────────────────────────────────────────────────────────────────
  { group: "Options",  href: "/option-chain",    label: "Option Chain"     },
  { group: "Options",  href: "/expiry-heatmap",  label: "Expiry Heatmap"   },
  { group: "Options",  href: "/oi-analytics",    label: "OI Analytics"     },
  { group: "Options",  href: "/strategy-builder",label: "Strategy Builder" },
  // ── Risk ──────────────────────────────────────────────────────────────────────
  { group: "Risk",     href: "/paper-trade",     label: "Paper Trade"      },
  // ── Learn ─────────────────────────────────────────────────────────────────────
  { group: "Learn",    href: "/fo-learn",        label: "Learn F&O"        },
];

/** Back-links at the bottom of F&O nav (not F&O-specific, no prefix entry needed). */
export const FO_BACK_ROUTES = [
  { href: "/dashboard", label: "Back to Equity", group: "Equity" as const },
  { href: "/settings",  label: "Settings",       group: "Equity" as const },
];
