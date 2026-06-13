"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  // Equity nav icons
  LayoutDashboard, Compass, LineChart, Radar, Beaker, GitCompare,
  Wallet, Star, FileText, Calendar, Newspaper, Sliders, Settings, GraduationCap,
  TestTube2, Calculator,
  // F&O nav icons
  Zap,          // Live Scanner
  BarChart2,    // F&O Overview
  Activity,     // PCR & Sentiment
  Link2,        // Option Chain
  CalendarDays, // Expiry Heatmap
  BarChart3,    // OI Analytics
  Layers,       // Strategy Builder
  FlaskConical, // Paper Trade
  BookOpen,     // Learn F&O
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useRegion, type Region } from "@/lib/region";
import { useState, useEffect } from "react";
import { FO_PREFIXES, FO_NAV_ROUTES, FO_BACK_ROUTES } from "@/lib/nav-config";

type NavItem = {
  href: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  group: string;
};

const EQUITY_NAV: NavItem[] = [
  { group: "Market",   href: "/dashboard",        label: "Dashboard",         icon: LayoutDashboard },
  { group: "Market",   href: "/universe",         label: "Universe Explorer", icon: Compass },
  { group: "Market",   href: "/news",             label: "News",              icon: Newspaper },
  { group: "Market",   href: "/earnings",         label: "Earnings",          icon: Calendar },
  { group: "Analysis", href: "/analyzer",         label: "Stock Analyzer",    icon: LineChart },
  { group: "Analysis", href: "/scanner",          label: "Scanner",           icon: Radar },
  { group: "Analysis", href: "/patterns",         label: "Pattern Lab",       icon: Beaker },
  { group: "Analysis", href: "/compare",          label: "Compare",           icon: GitCompare },
  { group: "Analysis", href: "/backtest",         label: "Backtest",          icon: TestTube2 },
  { group: "Tools",    href: "/position-sizing",  label: "Position Sizing",   icon: Calculator },
  { group: "Tools",    href: "/rules",            label: "Rule Engine",       icon: Sliders },
  { group: "Tools",    href: "/portfolio",        label: "Portfolio",         icon: Wallet },
  { group: "Tools",    href: "/watchlist",        label: "Watchlist",         icon: Star },
  { group: "Tools",    href: "/reports",          label: "Reports",           icon: FileText },
  { group: "Tools",    href: "/settings",         label: "Settings",          icon: Settings },
  { group: "Help",     href: "/learn",            label: "Learn",             icon: GraduationCap },
];

/**
 * Icon map keyed by href. Covers every route in FO_NAV_ROUTES + FO_BACK_ROUTES.
 * Adding a new page: add an entry here and a matching route in lib/nav-config.ts.
 */
const FO_ICON_MAP: Record<string, React.ComponentType<{ className?: string }>> = {
  // Market
  "/fo-dashboard":    BarChart2,
  "/pcr-sentiment":   Activity,
  // Scanners
  "/live-scanner":    Zap,
  // Options
  "/option-chain":    Link2,
  "/expiry-heatmap":  CalendarDays,
  "/oi-analytics":    BarChart3,
  "/strategy-builder":Layers,
  // Risk
  "/paper-trade":     FlaskConical,
  // Learn
  "/fo-learn":        BookOpen,
  // Back links
  "/dashboard":       LayoutDashboard,
  "/settings":        Settings,
};

/** Build typed NavItem array from route config + icon map. */
function buildFoNav(): NavItem[] {
  const items: NavItem[] = FO_NAV_ROUTES.map((r) => ({
    href:  r.href,
    label: r.label,
    group: r.group,
    icon:  FO_ICON_MAP[r.href] ?? BarChart2,
  }));
  FO_BACK_ROUTES.forEach((r) => {
    items.push({
      href:  r.href,
      label: r.label,
      group: r.group,
      icon:  FO_ICON_MAP[r.href] ?? LayoutDashboard,
    });
  });
  return items;
}

const FO_NAV: NavItem[] = buildFoNav();

export function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const { region, setRegion } = useRegion();
  const [mode, setMode] = useState<"Equity" | "F&O">("Equity");

  // Auto-switch to F&O mode when navigating directly to any F&O page
  useEffect(() => {
    if (region === "IN" && FO_PREFIXES.some((p) => pathname?.startsWith(p))) {
      setMode("F&O");
    }
  }, [pathname, region]);

  const NAV = region === "IN" && mode === "F&O" ? FO_NAV : EQUITY_NAV;
  const groups = Array.from(new Set(NAV.map((n) => n.group)));

  return (
    <aside className="w-60 shrink-0 border-r border-[var(--color-border)] bg-[var(--color-surface)] py-4 sticky top-0 h-screen overflow-y-auto">
      {/* Brand */}
      <div className="px-5 pb-4">
        <Link href="/dashboard" className="flex items-center gap-2">
          <div className="size-8 rounded-md bg-[var(--color-primary)] grid place-items-center text-white font-bold">SI</div>
          <div className="text-sm leading-tight">
            <div className="font-semibold">Stock Intel</div>
            <div className="text-[var(--color-text-muted)] text-[11px]">v2.0 · Local</div>
          </div>
        </Link>
      </div>

      {/* Market Region Toggle */}
      <div className="mx-3 mb-3 px-3 py-2.5 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)]">
        <div className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)] mb-2">Market Region</div>
        <div className="flex gap-1">
          {(["IN", "US"] as Region[]).map((r) => (
            <button
              key={r}
              onClick={() => { setRegion(r); if (r !== "IN") setMode("Equity"); }}
              className={cn(
                "flex-1 py-1 rounded text-[12px] font-medium transition-colors",
                region === r
                  ? "bg-[var(--color-primary)] text-white"
                  : "text-[var(--color-text-muted)] hover:text-white hover:bg-[var(--color-surface)]",
              )}
            >
              {r === "IN" ? "🇮🇳 India" : "🇺🇸 US"}
            </button>
          ))}
        </div>
      </div>

      {/* F&O Mode Toggle — India only */}
      {region === "IN" && (
        <div className="mx-3 mb-4 px-3 py-2.5 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)]">
          <div className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)] mb-2">Market Mode</div>
          <div className="flex gap-1">
            {(["Equity", "F&O"] as const).map((m) => (
              <button
                key={m}
                onClick={() => { setMode(m); if (m === "F&O") router.push("/live-scanner"); }}
                className={cn(
                  "flex-1 py-1 rounded text-[12px] font-medium transition-colors",
                  mode === m
                    ? "bg-[var(--color-primary)] text-white"
                    : "text-[var(--color-text-muted)] hover:text-white hover:bg-[var(--color-surface)]",
                )}
              >
                {m}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Navigation */}
      {groups.map((g) => (
        <div key={g} className="mb-3">
          <div className="px-5 pb-1 text-[10px] uppercase tracking-wider text-[var(--color-text-muted)]">{g}</div>
          <ul>
            {NAV.filter((n) => n.group === g).map((n) => {
              const active = pathname?.startsWith(n.href);
              return (
                <li key={n.href}>
                  <Link
                    href={n.href}
                    className={cn(
                      "flex items-center gap-2 mx-2 my-0.5 px-3 py-2 rounded-md text-[13px] transition-colors",
                      active
                        ? "bg-[var(--color-surface-2)] text-white"
                        : "text-[var(--color-text-muted)] hover:bg-[var(--color-surface-2)] hover:text-white",
                    )}
                  >
                    <n.icon className="size-4 shrink-0" />
                    <span className="truncate">{n.label}</span>
                  </Link>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </aside>
  );
}
