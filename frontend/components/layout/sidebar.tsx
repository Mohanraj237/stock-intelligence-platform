"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard, Compass, LineChart, Radar, Beaker, GitCompare,
  Wallet, Star, FileText, Calendar, Newspaper, Sliders, Settings, GraduationCap,
  TestTube2, Calculator,
} from "lucide-react";
import { cn } from "@/lib/utils";

type NavItem = { href: string; label: string; icon: React.ComponentType<{ className?: string }>; group: string };

const NAV: NavItem[] = [
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

export function Sidebar() {
  const pathname = usePathname();
  const groups = Array.from(new Set(NAV.map((n) => n.group)));

  return (
    <aside className="w-60 shrink-0 border-r border-[var(--color-border)] bg-[var(--color-surface)] py-4 sticky top-0 h-screen overflow-y-auto">
      <div className="px-5 pb-5">
        <Link href="/dashboard" className="flex items-center gap-2">
          <div className="size-8 rounded-md bg-[var(--color-primary)] grid place-items-center text-white font-bold">SI</div>
          <div className="text-sm leading-tight">
            <div className="font-semibold">Stock Intel</div>
            <div className="text-[var(--color-text-muted)] text-[11px]">v2.0 · Local</div>
          </div>
        </Link>
      </div>
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
