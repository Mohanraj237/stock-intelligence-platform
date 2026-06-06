"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  LayoutDashboard, Compass, LineChart, Radar, Beaker, GitCompare,
  Wallet, Star, FileText, Calendar, Newspaper, Sliders, Settings, GraduationCap,
  TestTube2, Calculator,
  TrendingUp, Link2, BarChart2, Activity, Target, Gauge, Flame, Grid, BookOpen,
  Cpu, FlaskConical, Crosshair,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useRegion, type Region } from "@/lib/region";
import { useState } from "react";

type NavItem = { href: string; label: string; icon: React.ComponentType<{ className?: string }>; group: string };

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

const FO_NAV: NavItem[] = [
  { group: "F&O Markets",  href: "/fo-dashboard",    label: "F&O Dashboard",    icon: TrendingUp },
  { group: "F&O Markets",  href: "/option-chain",    label: "Option Chain",     icon: Link2 },
  { group: "F&O Markets",  href: "/oi-analytics",    label: "OI Analytics",     icon: BarChart2 },
  { group: "F&O Markets",  href: "/pcr-sentiment",   label: "PCR & Sentiment",  icon: Activity },
  { group: "F&O Markets",  href: "/expiry-heatmap",  label: "Expiry Heatmap",   icon: Grid },
  { group: "F&O Tools",    href: "/strategy-builder",label: "Strategy Builder", icon: Target },
  { group: "F&O Tools",    href: "/fo-scanner",       label: "F&O Scanner",      icon: Flame },
  { group: "F&O Tools",    href: "/options-scanner",  label: "Options Buyer",    icon: Crosshair },
  { group: "F&O Tools",    href: "/greeks",          label: "Greeks Dashboard", icon: Gauge },
  { group: "F&O AI",       href: "/fo-ai-advisor",   label: "AI Advisor",       icon: Cpu },
  { group: "F&O AI",       href: "/paper-trade",     label: "Paper Trade",      icon: FlaskConical },
  { group: "F&O Tools",    href: "/fo-learn",        label: "Learn F&O",        icon: BookOpen },
  { group: "Equity",       href: "/dashboard",       label: "Dashboard",        icon: LayoutDashboard },
  { group: "Equity",       href: "/settings",        label: "Settings",         icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const { region, setRegion } = useRegion();
  const [mode, setMode] = useState<"Equity" | "F&O">("Equity");

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
                onClick={() => { setMode(m); if (m === "F&O") router.push("/fo-dashboard"); }}
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
