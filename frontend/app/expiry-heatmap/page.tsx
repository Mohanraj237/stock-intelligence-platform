"use client";

import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";
import { getOptionChain, getMaxPain } from "@/lib/fno-api";
import {
  INDEX_SYMBOLS,
  findAtmStrike,
  type OptionChainResponse,
} from "@/lib/fno-types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
} from "@/components/ui/select";
import { PageHeader } from "@/components/common/page-header";
import { cn } from "@/lib/utils";

// ── Banners ───────────────────────────────────────────────────────────────────

function SyntheticBanner({ vix }: { vix?: number }) {
  return (
    <div className="rounded-lg border border-blue-600/30 bg-blue-600/5 px-4 py-2.5 flex items-start gap-3">
      <span className="text-blue-400 text-[13px] mt-0.5">⚗</span>
      <div>
        <span className="text-blue-300 text-xs font-medium">Theoretical prices (Black-Scholes)</span>
        <span className="text-[var(--color-text-muted)] text-xs ml-2">
          NSE live option chain is unavailable. OI values are computed from real spot &amp; India VIX
          {vix != null ? ` (${vix.toFixed(1)}%)` : ""} using a simulated distribution for illustration.
        </span>
      </div>
    </div>
  );
}

function DataUnavailable({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="rounded-lg border border-yellow-600/30 bg-yellow-600/5 p-6 text-center space-y-3">
      <div className="text-yellow-400 text-sm font-medium">NSE Option Chain Temporarily Unavailable</div>
      <p className="text-xs text-[var(--color-text-muted)] max-w-md mx-auto">
        NSE&apos;s option chain API requires browser-level session authentication (Akamai).
        VIX, OI Spurts, and the F&amp;O Scanner work normally.
      </p>
      <button
        onClick={onRetry}
        className="text-xs px-3 py-1.5 rounded bg-[var(--color-surface-2)] border border-[var(--color-border)] text-white hover:bg-[var(--color-surface)] transition-colors"
      >
        Retry
      </button>
    </div>
  );
}

// ── Constants ─────────────────────────────────────────────────────────────────

const MAX_EXPIRIES = 6;
const STRIKES_AROUND_ATM = 10; // ±10 = up to 21 rows total (capped at 20)

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtOi(n: number): string {
  if (n === 0) return "";
  if (n >= 1_00_000) return `${(n / 1_00_000).toFixed(1)}L`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return n.toLocaleString("en-IN");
}

function fmtStrike(n: number): string {
  return n.toLocaleString("en-IN");
}

// Derive per-expiry stats from raw chain rows
interface ExpiryStats {
  expiry: string;
  totalCeOi: number;
  totalPeOi: number;
  pcr: number;
  maxPain: number;
}

function buildExpiryStats(
  chain: OptionChainResponse,
  expiries: string[],
): ExpiryStats[] {
  return expiries.map((exp) => {
    const rows = chain.rows.filter((r) => r.expiry === exp);
    const totalCeOi = rows.reduce((a, r) => a + (r.CE.oi ?? 0), 0);
    const totalPeOi = rows.reduce((a, r) => a + (r.PE.oi ?? 0), 0);
    const pcr = totalCeOi > 0 ? totalPeOi / totalCeOi : 0;
    const maxPain = getMaxPain(chain, exp);
    return { expiry: exp, totalCeOi, totalPeOi, pcr, maxPain };
  });
}

// ── OI Heatmap ────────────────────────────────────────────────────────────────

function OiHeatmap({
  chain,
  expiries,
  strikes,
  atmStrike,
}: {
  chain: OptionChainResponse;
  expiries: string[];
  strikes: number[];
  atmStrike: number;
}) {
  // Build a map: [strike][expiry] → total OI
  const oiMap = useMemo(() => {
    const m: Record<string, Record<string, number>> = {};
    for (const row of chain.rows) {
      if (!expiries.includes(row.expiry)) continue;
      if (!strikes.includes(row.strike)) continue;
      if (!m[row.strike]) m[row.strike] = {};
      m[row.strike][row.expiry] = (m[row.strike][row.expiry] ?? 0) + (row.CE.oi ?? 0) + (row.PE.oi ?? 0);
    }
    return m;
  }, [chain, expiries, strikes]);

  // Max OI across all cells for intensity scaling
  const maxOi = useMemo(() => {
    let max = 0;
    for (const strikeMap of Object.values(oiMap)) {
      for (const oi of Object.values(strikeMap)) {
        if (oi > max) max = oi;
      }
    }
    return max;
  }, [oiMap]);

  const colWidth = `${Math.floor(100 / (expiries.length + 1))}%`;

  return (
    <div className="overflow-x-auto">
      <div
        className="grid text-xs"
        style={{
          gridTemplateColumns: `80px repeat(${expiries.length}, minmax(90px, 1fr))`,
          minWidth: `${80 + expiries.length * 100}px`,
        }}
      >
        {/* Header row */}
        <div className="sticky left-0 z-20 bg-[var(--color-surface)] px-2 py-2 text-center text-[10px] uppercase tracking-wider text-[var(--color-text-muted)] border-b border-r border-[var(--color-border)] font-semibold">
          Strike
        </div>
        {expiries.map((exp) => (
          <div
            key={exp}
            className="px-2 py-2 text-center text-[10px] text-[var(--color-text-muted)] border-b border-r border-[var(--color-border)] truncate font-semibold"
            title={exp}
          >
            {exp}
          </div>
        ))}

        {/* Strike rows */}
        {[...strikes].sort((a, b) => a - b).map((strike) => {
          const isAtm = strike === atmStrike;
          return [
            /* Strike label */
            <div
              key={`label-${strike}`}
              className={cn(
                "sticky left-0 z-10 px-2 py-2 text-center font-bold border-b border-r border-[var(--color-border)] tnum",
                isAtm
                  ? "text-blue-400 bg-blue-500/10"
                  : "text-white bg-[var(--color-surface)]",
              )}
            >
              {fmtStrike(strike)}
              {isAtm && <div className="text-[8px] font-normal text-blue-400 leading-none">ATM</div>}
            </div>,

            /* OI cells per expiry */
            ...expiries.map((exp) => {
              const oi = oiMap[strike]?.[exp] ?? 0;
              const intensity = maxOi > 0 ? oi / maxOi : 0;
              return (
                <div
                  key={`${strike}-${exp}`}
                  className="px-2 py-2 text-center border-b border-r border-[var(--color-border)] tnum text-[11px] font-medium transition-colors"
                  style={{
                    backgroundColor: oi > 0 ? `rgba(30, 196, 138, ${Math.max(0.05, intensity)})` : "transparent",
                    color: intensity > 0.5 ? "#fff" : intensity > 0.2 ? "#d1fae5" : "var(--color-text-muted)",
                  }}
                  title={oi > 0 ? `OI: ${oi.toLocaleString("en-IN")}` : "No OI"}
                >
                  {oi > 0 ? fmtOi(oi) : <span className="opacity-20">·</span>}
                </div>
              );
            }),
          ];
        })}
      </div>

      {/* Legend */}
      <div className="mt-3 flex items-center gap-2 text-[11px] text-[var(--color-text-muted)]">
        <span>OI Intensity:</span>
        <div className="flex items-center gap-0">
          {[0.05, 0.2, 0.4, 0.6, 0.8, 1].map((v) => (
            <div
              key={v}
              className="w-8 h-4"
              style={{ backgroundColor: `rgba(30, 196, 138, ${v})` }}
            />
          ))}
        </div>
        <span>Low → High</span>
      </div>
    </div>
  );
}

// ── Max Pain Bar Chart ────────────────────────────────────────────────────────

function MaxPainChart({ stats }: { stats: ExpiryStats[] }) {
  const data = stats.map((s) => ({
    expiry: s.expiry.split("-").slice(0, 2).join("-"), // "27-Mar"
    maxPain: s.maxPain,
    fullExpiry: s.expiry,
  }));

  return (
    <ResponsiveContainer width="100%" height={260}>
      <BarChart data={data} margin={{ top: 8, right: 16, bottom: 0, left: 12 }}>
        <XAxis
          dataKey="expiry"
          tick={{ fill: "#94a3b8", fontSize: 10 }}
          axisLine={false}
          tickLine={false}
        />
        <YAxis
          tick={{ fill: "#94a3b8", fontSize: 10 }}
          tickFormatter={(v: number) => v.toLocaleString("en-IN")}
          width={60}
          axisLine={false}
          tickLine={false}
        />
        <Tooltip
          contentStyle={{ background: "#131822", border: "1px solid #232a3a", fontSize: 12, color: "#fff" }}
          formatter={(val: number) => [`₹${val.toLocaleString("en-IN")}`, "Max Pain"]}
          labelFormatter={(l: string) => `Expiry: ${l}`}
        />
        <Bar dataKey="maxPain" name="Max Pain" radius={[3, 3, 0, 0]}>
          {data.map((_, i) => (
            <Cell
              key={i}
              fill={i === 0 ? "#6366f1" : "#1ec48a"}
              fillOpacity={i === 0 ? 0.9 : 0.65}
            />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

// ── Rollover Stats Table ──────────────────────────────────────────────────────

function RolloverTable({ stats }: { stats: ExpiryStats[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs min-w-[560px]">
        <thead className="sticky top-0 z-10 bg-[var(--color-surface)] border-b border-[var(--color-border)]">
          <tr className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)]">
            <th className="px-3 py-2 text-left">Expiry</th>
            <th className="px-3 py-2 text-right">Total CE OI</th>
            <th className="px-3 py-2 text-right">Total PE OI</th>
            <th className="px-3 py-2 text-right">PCR</th>
            <th className="px-3 py-2 text-right">Max Pain</th>
          </tr>
        </thead>
        <tbody>
          {stats.map((s, i) => {
            const isCurrentExpiry = i === 0;
            const pcrClass =
              s.pcr > 1.2
                ? "text-[var(--color-success)]"
                : s.pcr < 0.8
                ? "text-[var(--color-danger)]"
                : "text-[var(--color-text-muted)]";

            return (
              <tr
                key={s.expiry}
                className={cn(
                  "border-b border-[var(--color-border)] transition-colors",
                  isCurrentExpiry
                    ? "bg-[var(--color-primary)]/10"
                    : "hover:bg-[var(--color-surface-2)]/60",
                )}
              >
                <td className="px-3 py-2 font-medium text-white">
                  {s.expiry}
                  {isCurrentExpiry && (
                    <span className="ml-2 rounded-full bg-[var(--color-primary)]/20 px-1.5 py-0.5 text-[9px] text-[var(--color-primary)] font-semibold uppercase">
                      Current
                    </span>
                  )}
                </td>
                <td className="px-3 py-2 text-right tnum text-[var(--color-success)]">
                  {s.totalCeOi > 0 ? s.totalCeOi.toLocaleString("en-IN") : "—"}
                </td>
                <td className="px-3 py-2 text-right tnum text-[var(--color-danger)]">
                  {s.totalPeOi > 0 ? s.totalPeOi.toLocaleString("en-IN") : "—"}
                </td>
                <td className={cn("px-3 py-2 text-right tnum font-semibold", pcrClass)}>
                  {s.totalCeOi > 0 ? s.pcr.toFixed(2) : "—"}
                </td>
                <td className="px-3 py-2 text-right tnum text-white">
                  {s.maxPain > 0 ? `₹${s.maxPain.toLocaleString("en-IN")}` : "—"}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function ExpiryHeatmapPage() {
  const [symbol, setSymbol] = useState<string>("NIFTY");

  const chainQuery = useQuery<OptionChainResponse>({
    queryKey: ["fno", "option-chain", symbol],
    queryFn: () => getOptionChain(symbol),
    refetchInterval: (query) => {
      const d = query.state.data as OptionChainResponse | undefined;
      if (d && (d.rows.length === 0 || d.meta.synthetic)) return false;
      return 60_000;
    },
    staleTime: 30_000,
  });

  const chain = chainQuery.data;
  const spot = chain?.meta.underlying ?? 0;
  const allExpiries = chain?.meta.expiry_dates ?? [];

  // Limit to MAX_EXPIRIES
  const expiries = useMemo(() => allExpiries.slice(0, MAX_EXPIRIES), [allExpiries]);

  // All unique strikes across all rows
  const allStrikes = useMemo<number[]>(() => {
    if (!chain) return [];
    const s = new Set<number>();
    for (const row of chain.rows) {
      if (expiries.includes(row.expiry)) s.add(row.strike);
    }
    return Array.from(s).sort((a, b) => a - b);
  }, [chain, expiries]);

  // ATM and ±STRIKES_AROUND_ATM strikes
  const atmStrike = useMemo(
    () => findAtmStrike(allStrikes, spot),
    [allStrikes, spot],
  );

  const heatmapStrikes = useMemo<number[]>(() => {
    if (!allStrikes.length || atmStrike === 0) return allStrikes.slice(0, 20);
    const atmIdx = allStrikes.indexOf(atmStrike);
    if (atmIdx === -1) return allStrikes.slice(0, 20);
    const start = Math.max(0, atmIdx - STRIKES_AROUND_ATM);
    const end = Math.min(allStrikes.length, atmIdx + STRIKES_AROUND_ATM + 1);
    return allStrikes.slice(start, end).slice(0, 20);
  }, [allStrikes, atmStrike]);

  const expiryStats = useMemo<ExpiryStats[]>(() => {
    if (!chain || !expiries.length) return [];
    return buildExpiryStats(chain, expiries);
  }, [chain, expiries]);

  const isLoading = chainQuery.isLoading;
  const isError = chainQuery.isError;

  return (
    <div className="max-w-[1500px] mx-auto space-y-5">
      <PageHeader
        title="Expiry Heatmap"
        subtitle="OI distribution across expiries and strikes · Max Pain · Rollover stats."
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <Select value={symbol} onValueChange={setSymbol}>
              <SelectTrigger className="w-[140px]">
                <SelectValue placeholder="Symbol" />
              </SelectTrigger>
              <SelectContent>
                {INDEX_SYMBOLS.map((s) => (
                  <SelectItem key={s} value={s}>{s}</SelectItem>
                ))}
              </SelectContent>
            </Select>

            {spot > 0 && (
              <div className="flex items-center gap-3 text-xs text-[var(--color-text-muted)]">
                <span>Spot: <span className="text-white font-semibold tnum">₹{spot.toLocaleString("en-IN")}</span></span>
                {atmStrike > 0 && (
                  <span>ATM: <span className="text-blue-400 font-semibold tnum">{atmStrike.toLocaleString("en-IN")}</span></span>
                )}
              </div>
            )}

            {chainQuery.isFetching && !isLoading && (
              <span className="text-[10px] text-[var(--color-text-muted)] animate-pulse">refreshing…</span>
            )}
          </div>
        }
      />

      {isError ? (
        <Card>
          <CardContent className="py-10 text-center text-sm text-[var(--color-danger)]">
            Failed to load option chain: {String(chainQuery.error)}
          </CardContent>
        </Card>
      ) : isLoading ? (
        <div className="space-y-5">
          <Card>
            <CardHeader><Skeleton className="h-4 w-40" /></CardHeader>
            <CardContent>
              <Skeleton className="h-64 w-full" />
            </CardContent>
          </Card>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <Card>
              <CardHeader><Skeleton className="h-4 w-32" /></CardHeader>
              <CardContent><Skeleton className="h-48 w-full" /></CardContent>
            </Card>
            <Card>
              <CardHeader><Skeleton className="h-4 w-32" /></CardHeader>
              <CardContent><Skeleton className="h-48 w-full" /></CardContent>
            </Card>
          </div>
        </div>
      ) : chain && chain.rows.length === 0 ? (
        <DataUnavailable onRetry={() => chainQuery.refetch()} />
      ) : (
        <>
          {chain?.meta.synthetic && <SyntheticBanner vix={chain.meta.vix} />}
          {/* Section 1: OI Heatmap */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center justify-between">
                <span>OI Heatmap — {symbol} · {heatmapStrikes.length} Strikes × {expiries.length} Expiries</span>
                <span className="text-[11px] font-normal text-[var(--color-text-muted)]">
                  CE OI + PE OI per cell
                </span>
              </CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              {heatmapStrikes.length === 0 || expiries.length === 0 ? (
                <div className="py-12 text-center text-sm text-[var(--color-text-muted)]">
                  No data to display.
                </div>
              ) : (
                <div className="p-4">
                  <OiHeatmap
                    chain={chain!}
                    expiries={expiries}
                    strikes={heatmapStrikes}
                    atmStrike={atmStrike}
                  />
                </div>
              )}
            </CardContent>
          </Card>

          {/* Section 2 + 3 side by side on lg */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {/* Max Pain Chart */}
            <Card>
              <CardHeader>
                <CardTitle>Max Pain by Expiry — {symbol}</CardTitle>
              </CardHeader>
              <CardContent>
                {expiryStats.length === 0 ? (
                  <div className="py-12 text-center text-sm text-[var(--color-text-muted)]">No data.</div>
                ) : (
                  <>
                    <MaxPainChart stats={expiryStats} />
                    <p className="mt-2 text-[11px] text-[var(--color-text-muted)]">
                      Purple bar = current (near) expiry. Max pain is the strike at which option writers face minimum combined loss from CE + PE OI.
                    </p>
                  </>
                )}
              </CardContent>
            </Card>

            {/* Rollover Stats Table */}
            <Card>
              <CardHeader>
                <CardTitle>Rollover Stats — {symbol}</CardTitle>
              </CardHeader>
              <CardContent className="p-0">
                {expiryStats.length === 0 ? (
                  <div className="py-12 text-center text-sm text-[var(--color-text-muted)]">No data.</div>
                ) : (
                  <RolloverTable stats={expiryStats} />
                )}
                <div className="px-3 py-2 border-t border-[var(--color-border)] text-[11px] text-[var(--color-text-muted)]">
                  PCR{" "}
                  <span className="text-[var(--color-success)]">&gt;1.2 Bullish</span>
                  {" · "}
                  <span className="text-[var(--color-danger)]">&lt;0.8 Bearish</span>
                  {" · "}
                  <span>0.8–1.2 Neutral</span>
                </div>
              </CardContent>
            </Card>
          </div>
        </>
      )}
    </div>
  );
}
