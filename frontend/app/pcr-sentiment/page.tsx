"use client";

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { Wind, TrendingUp, TrendingDown, Activity } from "lucide-react";
import { getVix, getOiSpurts, getPcr, getFnoHistory } from "@/lib/fno-api";
import type { VixData, OISpurtRow, PcrData } from "@/lib/fno-types";
import { getPcrSentiment, mergeHistory, type MergedHistoryPoint } from "@/lib/fno-utils";
import { HelpTip } from "@/components/ui/tooltip";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
  Legend,
  BarChart,
  Bar,
  Cell,
} from "recharts";

// ── Helpers ───────────────────────────────────────────────────────────────────

function vixColourClass(vix: number): string {
  if (vix > 25) return "text-[var(--color-danger)]";
  if (vix > 20) return "text-amber-400";
  if (vix < 15) return "text-[var(--color-success)]";
  return "text-[var(--color-text-muted)]";
}

function getVixRegime(vix: number): {
  label: string;
  color: string;
  borderClass: string;
  bgClass: string;
} {
  if (vix > 25) return { label: "High Fear",  color: "var(--color-danger)",  borderClass: "border-[var(--color-danger)]/30",  bgClass: "bg-[color-mix(in_oklab,var(--color-danger)_6%,transparent)]"  };
  if (vix > 20) return { label: "Elevated",   color: "#f59e0b",              borderClass: "border-amber-500/30",              bgClass: "bg-amber-500/5"                                                  };
  if (vix > 15) return { label: "Normal",     color: "var(--color-text-muted)", borderClass: "border-[var(--color-border)]",  bgClass: ""                                                                };
  return         { label: "Low",          color: "var(--color-success)", borderClass: "border-[var(--color-success)]/30",  bgClass: "bg-[color-mix(in_oklab,var(--color-success)_6%,transparent)]" };
}

type FlowType = "Long Buildup" | "Short Buildup" | "Short Covering" | "Long Unwinding";
const FLOW_COLORS: Record<FlowType, string> = {
  "Long Buildup":   "var(--color-success)",
  "Short Buildup":  "var(--color-danger)",
  "Short Covering": "#60a5fa",
  "Long Unwinding": "#f97316",
};

function classifyOIFlows(rows: OISpurtRow[]) {
  let longBuildup = 0, shortBuildup = 0, shortCovering = 0, longUnwinding = 0;
  for (const r of rows) {
    if      (r.oi_change_pct > 10 && r.price_chg_pct > 0)  longBuildup++;
    else if (r.oi_change_pct > 10 && r.price_chg_pct <= 0) shortBuildup++;
    else if (r.oi_change_pct < -10 && r.price_chg_pct > 0) shortCovering++;
    else if (r.oi_change_pct < -10 && r.price_chg_pct <= 0) longUnwinding++;
  }
  const total = longBuildup + shortBuildup + shortCovering + longUnwinding;
  const bullishPct = total > 0 ? ((longBuildup + shortCovering) / total) * 100 : 50;
  return { longBuildup, shortBuildup, shortCovering, longUnwinding, total, bullishPct };
}

// ── PCR Card ──────────────────────────────────────────────────────────────────

function PcrCard({ data, loading }: { data?: PcrData; loading: boolean }) {
  if (loading || !data) {
    return (
      <Card>
        <CardContent className="p-5 space-y-3">
          <Skeleton className="h-4 w-28" />
          <Skeleton className="h-12 w-24" />
          <Skeleton className="h-3 w-40" />
          <Skeleton className="h-3 w-32" />
        </CardContent>
      </Card>
    );
  }

  const sentiment = getPcrSentiment(data.pcr_oi);
  const fmtOI = (n: number) => n >= 1e7 ? `${(n / 1e7).toFixed(2)}Cr` : n >= 1e5 ? `${(n / 1e5).toFixed(1)}L` : n.toLocaleString("en-IN");

  return (
    <Card>
      <CardContent className="p-5 space-y-3">
        <div className="flex items-center justify-between">
          <span className="text-xs font-semibold text-white">{data.symbol}</span>
          <Badge variant={sentiment.variant}>{sentiment.label}</Badge>
        </div>

        <div className="flex items-baseline gap-3">
          <div className="text-4xl font-bold tnum text-white">{data.pcr_oi.toFixed(3)}</div>
          <div className="text-xs text-[var(--color-text-muted)]">PCR OI</div>
        </div>

        <div className="text-xs text-[var(--color-text-muted)]">
          PCR Vol: <span className="text-white">{data.pcr_vol.toFixed(3)}</span>
        </div>

        {/* CE vs PE OI bar */}
        <div className="space-y-1">
          <div className="flex justify-between text-[10px] text-[var(--color-text-muted)]">
            <span className="text-[var(--color-success)]">CE OI: {fmtOI(data.total_ce_oi)}</span>
            <span className="text-[var(--color-danger)]">PE OI: {fmtOI(data.total_pe_oi)}</span>
          </div>
          {(data.total_ce_oi + data.total_pe_oi) > 0 && (
            <div className="h-1.5 rounded-full bg-[var(--color-surface-2)] overflow-hidden">
              <div
                className="h-full rounded-full bg-[var(--color-success)] transition-all"
                style={{ width: `${(data.total_ce_oi / (data.total_ce_oi + data.total_pe_oi)) * 100}%` }}
              />
            </div>
          )}
          <div className="flex justify-between text-[10px] text-[var(--color-text-muted)]">
            <span>CE Vol: {fmtOI(data.total_ce_vol)}</span>
            <span>PE Vol: {fmtOI(data.total_pe_vol)}</span>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

// ── History Chart ─────────────────────────────────────────────────────────────

function HistoryChart({ data, loading }: { data: MergedHistoryPoint[]; loading: boolean }) {
  if (loading) {
    return (
      <Card>
        <CardHeader><Skeleton className="h-4 w-48" /></CardHeader>
        <CardContent><Skeleton className="h-52 w-full" /></CardContent>
      </Card>
    );
  }

  if (data.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>60-Day PCR &amp; VIX History</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="h-32 flex items-center justify-center text-sm text-[var(--color-text-muted)]">
            No history yet — data accumulates one entry per trading day at startup.
          </div>
        </CardContent>
      </Card>
    );
  }

  const fmt = (v: number | null) => (v == null ? "—" : v.toFixed(2));
  const tickDate = (d: string) => d.slice(5); // "MM-DD"

  return (
    <Card>
      <CardHeader>
        <CardTitle>60-Day PCR &amp; VIX History</CardTitle>
      </CardHeader>
      <CardContent>
        <ResponsiveContainer width="100%" height={220}>
          <LineChart data={data} margin={{ top: 8, right: 48, bottom: 0, left: 0 }}>
            <XAxis
              dataKey="date"
              tick={{ fill: "#94a3b8", fontSize: 10 }}
              tickFormatter={tickDate}
              interval="preserveStartEnd"
              axisLine={false}
              tickLine={false}
            />
            {/* Left Y — PCR (0–2) */}
            <YAxis
              yAxisId="pcr"
              domain={[0, 2]}
              tick={{ fill: "#94a3b8", fontSize: 10 }}
              tickFormatter={(v: number) => v.toFixed(1)}
              width={32}
              axisLine={false}
              tickLine={false}
            />
            {/* Right Y — VIX (0–35) */}
            <YAxis
              yAxisId="vix"
              orientation="right"
              domain={[0, 35]}
              tick={{ fill: "#94a3b8", fontSize: 10 }}
              tickFormatter={(v: number) => v.toFixed(0)}
              width={32}
              axisLine={false}
              tickLine={false}
            />
            <Tooltip
              contentStyle={{ background: "#131822", border: "1px solid #232a3a", fontSize: 11, color: "#fff" }}
              formatter={(val: number, name: string) => [fmt(val), name]}
              labelFormatter={(l: string) => `Date: ${l}`}
            />
            <ReferenceLine yAxisId="pcr" y={1} stroke="#475569" strokeDasharray="3 2" label={{ value: "PCR=1", fill: "#475569", fontSize: 9 }} />
            <Legend wrapperStyle={{ fontSize: 11, color: "#94a3b8" }} />
            <Line yAxisId="pcr" type="monotone" dataKey="nifty_pcr"     name="NIFTY PCR"     stroke="#6366f1" dot={false} strokeWidth={2} connectNulls />
            <Line yAxisId="pcr" type="monotone" dataKey="banknifty_pcr" name="BankNifty PCR" stroke="#8b5cf6" dot={false} strokeWidth={1.5} strokeDasharray="4 2" connectNulls />
            <Line yAxisId="vix" type="monotone" dataKey="vix"           name="India VIX"     stroke="#ef5350" dot={false} strokeWidth={1.5} connectNulls />
          </LineChart>
        </ResponsiveContainer>
        <p className="mt-2 text-[11px] text-[var(--color-text-muted)]">
          PCR on left axis (0–2) · India VIX on right axis (0–35). Dashed line = PCR neutral (1.0).
        </p>
      </CardContent>
    </Card>
  );
}

// ── VIX Card ──────────────────────────────────────────────────────────────────

function VIXCard({ data, isLoading }: { data?: VixData; isLoading: boolean }) {
  if (isLoading || !data) {
    return (
      <Card>
        <CardHeader><Skeleton className="h-4 w-28" /></CardHeader>
        <CardContent className="flex flex-wrap gap-8 pb-5">
          <Skeleton className="h-14 w-32" /><Skeleton className="h-14 w-24" /><Skeleton className="h-14 w-48" />
        </CardContent>
      </Card>
    );
  }

  const vix = data.vix ?? 0;
  const regime = getVixRegime(vix);
  const changeVal = data.change ?? 0;
  const changePct = data.change_pct ?? 0;

  return (
    <Card className={cn("border", regime.borderClass, regime.bgClass)}>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Wind className="size-4" style={{ color: regime.color }} />
          India VIX
          <span className="ml-auto text-xs font-semibold px-2.5 py-0.5 rounded-full"
            style={{ color: regime.color, background: `color-mix(in srgb, ${regime.color} 15%, transparent)` }}>
            {regime.label}
          </span>
        </CardTitle>
      </CardHeader>
      <CardContent className="pb-5">
        <div className="flex flex-wrap items-end gap-8">
          <div>
            <div className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)] mb-1">Current</div>
            <div className="text-5xl font-bold tabular-nums" style={{ color: regime.color }}>{vix.toFixed(2)}</div>
          </div>
          <div>
            <div className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)] mb-1">Change</div>
            <div className={cn("text-2xl font-semibold tabular-nums", changeVal >= 0 ? "text-[var(--color-danger)]" : "text-[var(--color-success)]")}>
              {changeVal >= 0 ? "+" : ""}{changeVal.toFixed(2)}{" "}
              <span className="text-base font-medium">({changeVal >= 0 ? "+" : ""}{changePct.toFixed(2)}%)</span>
            </div>
          </div>
          <div className="grid grid-cols-3 gap-5 ml-auto">
            {[{ label: "Open", value: data.open }, { label: "High", value: data.high }, { label: "Low", value: data.low }].map(({ label, value }) => (
              <div key={label}>
                <div className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)] mb-1">{label}</div>
                <div className="text-sm font-medium tabular-nums text-white">{value != null ? value.toFixed(2) : "—"}</div>
              </div>
            ))}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

// ── OI Flow Section ───────────────────────────────────────────────────────────

function OIFlowSection({ data, isLoading }: { data?: OISpurtRow[]; isLoading: boolean }) {
  if (isLoading || !data) {
    return (
      <Card>
        <CardHeader><Skeleton className="h-4 w-48" /></CardHeader>
        <CardContent className="space-y-4 pb-5">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-24 w-full rounded-lg" />)}
          </div>
          <Skeleton className="h-32 w-full" />
        </CardContent>
      </Card>
    );
  }

  const flows = classifyOIFlows(data);
  const biasLabel = flows.bullishPct >= 65 ? "Strongly Bullish" : flows.bullishPct >= 55 ? "Bullish Bias"
    : flows.bullishPct >= 45 ? "Neutral" : flows.bullishPct >= 35 ? "Bearish Bias" : "Strongly Bearish";
  const biasVariant = flows.bullishPct >= 55 ? "success" : flows.bullishPct <= 45 ? "danger" : "default";

  const chartData: { name: FlowType; count: number }[] = [
    { name: "Long Buildup",   count: flows.longBuildup   },
    { name: "Short Buildup",  count: flows.shortBuildup  },
    { name: "Short Covering", count: flows.shortCovering },
    { name: "Long Unwinding", count: flows.longUnwinding },
  ];

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2">
            <Activity className="size-4 text-[var(--color-primary)]" />
            Market OI Flow Sentiment
          </CardTitle>
          <div className="flex items-center gap-2">
            <span className="text-xs text-[var(--color-text-muted)]">
              Bullish Bias: <span className="tabular-nums font-medium text-white">{flows.bullishPct.toFixed(1)}%</span>
            </span>
            <Badge variant={biasVariant as "success" | "danger" | "default"}>{biasLabel}</Badge>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-5 pb-5">
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {([
            { label: "Long Buildup",   count: flows.longBuildup,   icon: <TrendingUp  className="size-4" />, color: FLOW_COLORS["Long Buildup"]   },
            { label: "Short Buildup",  count: flows.shortBuildup,  icon: <TrendingDown className="size-4" />, color: FLOW_COLORS["Short Buildup"]  },
            { label: "Short Covering", count: flows.shortCovering, icon: <TrendingUp  className="size-4" />, color: FLOW_COLORS["Short Covering"]  },
            { label: "Long Unwinding", count: flows.longUnwinding, icon: <TrendingDown className="size-4" />, color: FLOW_COLORS["Long Unwinding"] },
          ] as const).map(({ label, count, icon, color }) => (
            <div key={label} className="rounded-lg border border-[var(--color-border)] p-4 flex flex-col gap-2"
              style={{ background: `color-mix(in oklab, ${color} 6%, transparent)` }}>
              <div className="flex items-center justify-between">
                <span className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)]">{label}</span>
                <span style={{ color }}>{icon}</span>
              </div>
              <div className="text-3xl font-bold tabular-nums" style={{ color }}>{count}</div>
              <div className="text-[10px] text-[var(--color-text-muted)]">stocks</div>
            </div>
          ))}
        </div>
        <div>
          <div className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)] mb-2">
            Distribution ({flows.total} active stocks)
          </div>
          <ResponsiveContainer width="100%" height={120}>
            <BarChart data={chartData} margin={{ top: 4, right: 8, bottom: 4, left: 0 }} barCategoryGap="25%">
              <XAxis dataKey="name" tick={{ fontSize: 10, fill: "var(--color-text-muted)" }} tickLine={false} axisLine={false} />
              <YAxis tick={{ fontSize: 10, fill: "var(--color-text-muted)" }} tickLine={false} axisLine={false} width={28} />
              <Tooltip
                cursor={{ fill: "var(--color-surface-2)", opacity: 0.5 }}
                contentStyle={{ background: "var(--color-surface)", border: "1px solid var(--color-border)", borderRadius: 6, fontSize: 11, color: "white" }}
              />
              <Bar dataKey="count" radius={[3, 3, 0, 0]}>
                {chartData.map((entry) => <Cell key={entry.name} fill={FLOW_COLORS[entry.name]} fillOpacity={0.85} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function PCRSentimentPage() {
  const vixQuery    = useQuery({ queryKey: ["fno", "vix"],                 queryFn: getVix,              refetchInterval: 60_000, staleTime: 30_000 });
  const pcrNifty    = useQuery({ queryKey: ["fno", "pcr", "NIFTY"],        queryFn: () => getPcr("NIFTY"),     refetchInterval: 60_000, staleTime: 30_000 });
  const pcrBN       = useQuery({ queryKey: ["fno", "pcr", "BANKNIFTY"],    queryFn: () => getPcr("BANKNIFTY"), refetchInterval: 60_000, staleTime: 30_000 });
  const oiQuery     = useQuery({ queryKey: ["fno", "oi-spurts"],           queryFn: getOiSpurts,         refetchInterval: 60_000, staleTime: 30_000 });
  const historyQuery = useQuery({ queryKey: ["fno", "history"],            queryFn: getFnoHistory,       staleTime: 5 * 60_000 });

  const historyPoints = useMemo(
    () => mergeHistory(historyQuery.data?.pcr ?? [], historyQuery.data?.vix ?? []),
    [historyQuery.data],
  );

  return (
    <div className="max-w-[1400px] mx-auto space-y-5">
      <header>
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-xl font-semibold text-white">PCR &amp; Sentiment</h1>
            <p className="text-xs text-[var(--color-text-muted)] mt-0.5">
              Put-Call Ratio · India VIX · 60-day history · OI flow sentiment
            </p>
          </div>
          <a href="/fo-learn#pcr" className="text-[11px] text-[var(--color-primary)] hover:underline whitespace-nowrap mt-1">
            Learn about PCR →
          </a>
        </div>
      </header>

      {/* PCR Cards — NIFTY + BANKNIFTY (P0-1 fix) */}
      <section>
        <h2 className="text-[11px] uppercase tracking-wider text-[var(--color-text-muted)] mb-2">
          <HelpTip tip="PCR = Total PE Open Interest ÷ Total CE Open Interest. Values above 1.0 suggest more put writing (bullish market bias); below 1.0 more call writing (bearish bias).">
            Put-Call Ratio
          </HelpTip>
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <PcrCard data={pcrNifty.data}  loading={pcrNifty.isLoading}  />
          <PcrCard data={pcrBN.data}     loading={pcrBN.isLoading}     />
        </div>
        {(pcrNifty.isError || pcrBN.isError) && (
          <div className="mt-2 rounded-md border border-[var(--color-warning)]/40 bg-[color-mix(in_oklab,var(--color-warning)_8%,transparent)] px-4 py-2 text-xs text-[var(--color-warning)]">
            PCR unavailable — NSE option chain may be rate-limited outside market hours. Try again between 9:15 AM and 3:30 PM IST.
          </div>
        )}
      </section>

      {/* 60-day PCR + VIX history (P1-1 fix) */}
      <HistoryChart data={historyPoints} loading={historyQuery.isLoading} />

      {/* India VIX */}
      <VIXCard data={vixQuery.data} isLoading={vixQuery.isLoading} />
      {vixQuery.isError && (
        <div className="rounded-md border border-[var(--color-danger)]/30 bg-[color-mix(in_oklab,var(--color-danger)_8%,transparent)] px-4 py-3 text-sm text-[var(--color-danger)]">
          Failed to load VIX data — check backend connectivity and try refreshing.
        </div>
      )}

      {/* OI Flow Sentiment */}
      <OIFlowSection data={oiQuery.data} isLoading={oiQuery.isLoading} />
      {oiQuery.isError && (
        <div className="rounded-md border border-[var(--color-danger)]/30 bg-[color-mix(in_oklab,var(--color-danger)_8%,transparent)] px-4 py-3 text-sm text-[var(--color-danger)]">
          Failed to load OI flow data — NSE may be rate-limiting. Retry after a minute.
        </div>
      )}

      {/* PCR interpretation reference */}
      <Card>
        <CardHeader>
          <CardTitle className="text-xs uppercase tracking-wider">PCR Interpretation Guide</CardTitle>
        </CardHeader>
        <CardContent className="pb-5">
          <div className="grid grid-cols-2 sm:grid-cols-5 gap-2 text-[11px]">
            {[
              { range: "PCR &gt; 1.3",    label: "Strongly Bullish", color: "var(--color-success)", bg: "color-mix(in oklab, var(--color-success) 10%, transparent)" },
              { range: "1.0 – 1.3",       label: "Mildly Bullish",   color: "var(--color-success)", bg: "color-mix(in oklab, var(--color-success) 6%, transparent)"  },
              { range: "0.7 – 1.0",       label: "Neutral",          color: "var(--color-text-muted)", bg: "var(--color-surface-2)"                                  },
              { range: "0.5 – 0.7",       label: "Mildly Bearish",   color: "var(--color-warning)", bg: "color-mix(in oklab, var(--color-warning) 8%, transparent)"  },
              { range: "PCR &lt; 0.5",    label: "Strongly Bearish", color: "var(--color-danger)",  bg: "color-mix(in oklab, var(--color-danger) 10%, transparent)"  },
            ].map(({ range, label, color, bg }) => (
              <div key={label} className="rounded-md px-2.5 py-2.5 border border-[var(--color-border)] text-center" style={{ background: bg }}>
                <div className="font-bold text-sm" style={{ color }} dangerouslySetInnerHTML={{ __html: range }} />
                <div className="text-[var(--color-text-muted)] mt-1">{label}</div>
              </div>
            ))}
          </div>
          <p className="mt-3 text-[11px] text-[var(--color-text-muted)]">
            PCR = Total PE Open Interest ÷ Total CE Open Interest. Values above 1.0 indicate more put writing (bullish), below 1.0 more call writing (bearish). Extreme readings (above 1.5 or below 0.4) often signal reversal zones.
          </p>
        </CardContent>
      </Card>

      {/* VIX Regime reference */}
      <Card>
        <CardHeader>
          <CardTitle className="text-xs uppercase tracking-wider">VIX Regime Reference</CardTitle>
        </CardHeader>
        <CardContent className="pb-5">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-[11px]">
            {[
              { range: "Below 15", label: "Low",       color: "var(--color-success)", bg: "color-mix(in oklab, var(--color-success) 10%, transparent)" },
              { range: "15 – 20",  label: "Normal",    color: "var(--color-text-muted)", bg: "var(--color-surface-2)"                                  },
              { range: "20 – 25",  label: "Elevated",  color: "#f59e0b",              bg: "color-mix(in oklab, #f59e0b 10%, transparent)"               },
              { range: "Above 25", label: "High Fear", color: "var(--color-danger)",  bg: "color-mix(in oklab, var(--color-danger) 10%, transparent)"   },
            ].map(({ range, label, color, bg }) => (
              <div key={label} className="rounded-md px-2.5 py-2.5 border border-[var(--color-border)] text-center" style={{ background: bg }}>
                <div className="font-bold text-sm" style={{ color }}>{range}</div>
                <div className="text-[var(--color-text-muted)] mt-1">{label}</div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
