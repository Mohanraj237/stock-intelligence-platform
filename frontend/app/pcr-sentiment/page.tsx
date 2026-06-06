"use client";

import { useQuery } from "@tanstack/react-query";
import { Wind, TrendingUp, TrendingDown, Activity, Info } from "lucide-react";
import { getVix, getOiSpurts } from "@/lib/fno-api";
import type { VixData, OISpurtRow } from "@/lib/fno-types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
  ReferenceLine,
} from "recharts";

// ── VIX Helpers ───────────────────────────────────────────────────────────────

function getVixRegime(vix: number): {
  label: string;
  color: string;
  borderClass: string;
  bgClass: string;
} {
  if (vix > 25)
    return {
      label: "High Fear",
      color: "var(--color-danger)",
      borderClass: "border-[var(--color-danger)]/30",
      bgClass: "bg-[color-mix(in_oklab,var(--color-danger)_6%,transparent)]",
    };
  if (vix > 20)
    return {
      label: "Elevated",
      color: "#f59e0b",
      borderClass: "border-amber-500/30",
      bgClass: "bg-amber-500/5",
    };
  if (vix > 15)
    return {
      label: "Normal",
      color: "var(--color-text-muted)",
      borderClass: "border-[var(--color-border)]",
      bgClass: "",
    };
  return {
    label: "Low",
    color: "var(--color-success)",
    borderClass: "border-[var(--color-success)]/30",
    bgClass: "bg-[color-mix(in_oklab,var(--color-success)_6%,transparent)]",
  };
}

// ── OI Flow Classification ────────────────────────────────────────────────────

type FlowType = "Long Buildup" | "Short Buildup" | "Short Covering" | "Long Unwinding";

interface OIFlowCounts {
  longBuildup: number;
  shortBuildup: number;
  shortCovering: number;
  longUnwinding: number;
  total: number;
  bullishPct: number;
}

function classifyOIFlows(rows: OISpurtRow[]): OIFlowCounts {
  let longBuildup = 0;
  let shortBuildup = 0;
  let shortCovering = 0;
  let longUnwinding = 0;

  for (const r of rows) {
    if (r.oi_change_pct > 10 && r.price_chg_pct > 0) longBuildup++;
    else if (r.oi_change_pct > 10 && r.price_chg_pct <= 0) shortBuildup++;
    else if (r.oi_change_pct < -10 && r.price_chg_pct > 0) shortCovering++;
    else if (r.oi_change_pct < -10 && r.price_chg_pct <= 0) longUnwinding++;
  }

  const total = longBuildup + shortBuildup + shortCovering + longUnwinding;
  const bullishPct = total > 0 ? ((longBuildup + shortCovering) / total) * 100 : 50;

  return { longBuildup, shortBuildup, shortCovering, longUnwinding, total, bullishPct };
}

function getBullishBiasVariant(
  pct: number,
): "success" | "danger" | "default" {
  if (pct >= 55) return "success";
  if (pct <= 45) return "danger";
  return "default";
}

function getBullishBiasLabel(pct: number): string {
  if (pct >= 65) return "Strongly Bullish";
  if (pct >= 55) return "Bullish Bias";
  if (pct >= 45) return "Neutral";
  if (pct >= 35) return "Bearish Bias";
  return "Strongly Bearish";
}

// ── Sub-components ────────────────────────────────────────────────────────────

function VIXCard({ data, isLoading }: { data?: VixData; isLoading: boolean }) {
  if (isLoading || !data) {
    return (
      <Card>
        <CardHeader>
          <Skeleton className="h-4 w-28" />
        </CardHeader>
        <CardContent className="flex flex-wrap gap-8 pb-5">
          <Skeleton className="h-14 w-32" />
          <Skeleton className="h-14 w-24" />
          <Skeleton className="h-14 w-48" />
        </CardContent>
      </Card>
    );
  }

  const vix = data.vix ?? 0;
  const regime = getVixRegime(vix);
  const changeVal = data.change ?? 0;
  const changePct = data.change_pct ?? 0;
  const changePositive = changeVal >= 0;

  return (
    <Card className={cn("border", regime.borderClass, regime.bgClass)}>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Wind className="size-4" style={{ color: regime.color }} />
          India VIX
          <span
            className="ml-auto text-xs font-semibold px-2.5 py-0.5 rounded-full"
            style={{
              color: regime.color,
              background: `color-mix(in srgb, ${regime.color} 15%, transparent)`,
            }}
          >
            {regime.label}
          </span>
        </CardTitle>
      </CardHeader>
      <CardContent className="pb-5">
        <div className="flex flex-wrap items-end gap-8">
          {/* Big VIX number */}
          <div>
            <div className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)] mb-1">
              Current
            </div>
            <div
              className="text-5xl font-bold tabular-nums"
              style={{ color: regime.color }}
            >
              {vix.toFixed(2)}
            </div>
          </div>

          {/* Change */}
          <div>
            <div className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)] mb-1">
              Change
            </div>
            <div
              className={cn(
                "text-2xl font-semibold tabular-nums",
                changePositive
                  ? "text-[var(--color-danger)]"
                  : "text-[var(--color-success)]",
              )}
            >
              {changePositive ? "+" : ""}
              {changeVal.toFixed(2)}{" "}
              <span className="text-base font-medium">
                ({changePositive ? "+" : ""}
                {changePct.toFixed(2)}%)
              </span>
            </div>
          </div>

          {/* OHLV stats */}
          <div className="grid grid-cols-3 gap-5 ml-auto">
            {[
              { label: "Open", value: data.open },
              { label: "High", value: data.high },
              { label: "Low", value: data.low },
            ].map(({ label, value }) => (
              <div key={label}>
                <div className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)] mb-1">
                  {label}
                </div>
                <div className="text-sm font-medium tabular-nums text-white">
                  {value != null ? value.toFixed(2) : "—"}
                </div>
              </div>
            ))}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

interface FlowStatCardProps {
  label: string;
  count: number;
  color: string;
  bgColor: string;
  icon: React.ReactNode;
}

function FlowStatCard({ label, count, color, bgColor, icon }: FlowStatCardProps) {
  return (
    <div
      className="rounded-lg border border-[var(--color-border)] p-4 flex flex-col gap-2"
      style={{ background: bgColor }}
    >
      <div className="flex items-center justify-between">
        <span className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)]">
          {label}
        </span>
        <span style={{ color }}>{icon}</span>
      </div>
      <div className="text-3xl font-bold tabular-nums" style={{ color }}>
        {count}
      </div>
      <div className="text-[10px] text-[var(--color-text-muted)]">stocks</div>
    </div>
  );
}

const FLOW_COLORS: Record<FlowType, string> = {
  "Long Buildup": "var(--color-success)",
  "Short Buildup": "var(--color-danger)",
  "Short Covering": "#60a5fa",
  "Long Unwinding": "#f97316",
};

function OIFlowSection({ data, isLoading }: { data?: OISpurtRow[]; isLoading: boolean }) {
  if (isLoading || !data) {
    return (
      <Card>
        <CardHeader>
          <Skeleton className="h-4 w-48" />
        </CardHeader>
        <CardContent className="space-y-4 pb-5">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-24 w-full rounded-lg" />
            ))}
          </div>
          <Skeleton className="h-32 w-full" />
        </CardContent>
      </Card>
    );
  }

  const flows = classifyOIFlows(data);
  const biasLabel = getBullishBiasLabel(flows.bullishPct);
  const biasVariant = getBullishBiasVariant(flows.bullishPct);

  const chartData: { name: FlowType; count: number }[] = [
    { name: "Long Buildup", count: flows.longBuildup },
    { name: "Short Buildup", count: flows.shortBuildup },
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
              Bullish Bias:{" "}
              <span className="tabular-nums font-medium text-white">
                {flows.bullishPct.toFixed(1)}%
              </span>
            </span>
            <Badge variant={biasVariant}>{biasLabel}</Badge>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-5 pb-5">
        {/* 4 stat cards */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <FlowStatCard
            label="Long Buildup"
            count={flows.longBuildup}
            color={FLOW_COLORS["Long Buildup"]}
            bgColor="color-mix(in oklab, var(--color-success) 6%, transparent)"
            icon={<TrendingUp className="size-4" />}
          />
          <FlowStatCard
            label="Short Buildup"
            count={flows.shortBuildup}
            color={FLOW_COLORS["Short Buildup"]}
            bgColor="color-mix(in oklab, var(--color-danger) 6%, transparent)"
            icon={<TrendingDown className="size-4" />}
          />
          <FlowStatCard
            label="Short Covering"
            count={flows.shortCovering}
            color={FLOW_COLORS["Short Covering"]}
            bgColor="color-mix(in oklab, #60a5fa 6%, transparent)"
            icon={<TrendingUp className="size-4" />}
          />
          <FlowStatCard
            label="Long Unwinding"
            count={flows.longUnwinding}
            color={FLOW_COLORS["Long Unwinding"]}
            bgColor="color-mix(in oklab, #f97316 6%, transparent)"
            icon={<TrendingDown className="size-4" />}
          />
        </div>

        {/* Distribution bar chart */}
        <div>
          <div className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)] mb-2">
            Distribution ({flows.total} active stocks)
          </div>
          <ResponsiveContainer width="100%" height={120}>
            <BarChart
              data={chartData}
              margin={{ top: 4, right: 8, bottom: 4, left: 0 }}
              barCategoryGap="25%"
            >
              <XAxis
                dataKey="name"
                tick={{ fontSize: 10, fill: "var(--color-text-muted)" }}
                tickLine={false}
                axisLine={false}
              />
              <YAxis
                tick={{ fontSize: 10, fill: "var(--color-text-muted)" }}
                tickLine={false}
                axisLine={false}
                width={28}
              />
              <Tooltip
                cursor={{ fill: "var(--color-surface-2)", opacity: 0.5 }}
                contentStyle={{
                  background: "var(--color-surface)",
                  border: "1px solid var(--color-border)",
                  borderRadius: 6,
                  fontSize: 11,
                  color: "white",
                }}
                labelStyle={{ color: "var(--color-text-muted)" }}
              />
              <ReferenceLine y={0} stroke="var(--color-border)" strokeWidth={1} />
              <Bar dataKey="count" radius={[3, 3, 0, 0]}>
                {chartData.map((entry) => (
                  <Cell
                    key={entry.name}
                    fill={FLOW_COLORS[entry.name]}
                    fillOpacity={0.85}
                  />
                ))}
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
  const vixQuery = useQuery({
    queryKey: ["fno", "vix"],
    queryFn: getVix,
    refetchInterval: 60_000,
    staleTime: 30_000,
  });

  const oiQuery = useQuery({
    queryKey: ["fno", "oi-spurts"],
    queryFn: getOiSpurts,
    refetchInterval: 60_000,
    staleTime: 30_000,
  });

  return (
    <div className="max-w-[1400px] mx-auto space-y-5">
      {/* Header */}
      <header>
        <h1 className="text-xl font-semibold text-white">PCR &amp; Sentiment</h1>
        <p className="text-xs text-[var(--color-text-muted)] mt-0.5">
          India VIX volatility index and OI flow-based market sentiment across F&amp;O instruments.
        </p>
      </header>

      {/* VIX section */}
      <VIXCard data={vixQuery.data} isLoading={vixQuery.isLoading} />

      {vixQuery.isError && (
        <div className="rounded-md border border-[var(--color-danger)]/30 bg-[color-mix(in_oklab,var(--color-danger)_8%,transparent)] px-4 py-3 text-sm text-[var(--color-danger)]">
          Failed to load VIX data. Please try refreshing.
        </div>
      )}

      {/* OI Flow Sentiment section */}
      <OIFlowSection data={oiQuery.data} isLoading={oiQuery.isLoading} />

      {oiQuery.isError && (
        <div className="rounded-md border border-[var(--color-danger)]/30 bg-[color-mix(in_oklab,var(--color-danger)_8%,transparent)] px-4 py-3 text-sm text-[var(--color-danger)]">
          Failed to load OI flow data. Please try refreshing.
        </div>
      )}

      {/* PCR info notice */}
      <div className="rounded-md border border-[var(--color-border)] bg-[var(--color-surface-2)] px-4 py-3 flex items-start gap-3">
        <Info className="size-4 mt-0.5 shrink-0 text-[var(--color-primary)]" />
        <p className="text-xs text-[var(--color-text-muted)] leading-relaxed">
          <span className="text-white font-medium">PCR (Put-Call Ratio)</span> requires NSE option chain data.
          Showing OI flow-based sentiment as an alternative — stocks are classified into Long Buildup,
          Short Buildup, Short Covering, and Long Unwinding based on OI change and price movement.
        </p>
      </div>

      {/* VIX regime reference table */}
      <Card>
        <CardHeader>
          <CardTitle className="text-xs uppercase tracking-wider">VIX Regime Reference</CardTitle>
        </CardHeader>
        <CardContent className="pb-5">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-[11px]">
            {[
              { range: "< 15", label: "Low", color: "var(--color-success)", bgColor: "color-mix(in oklab, var(--color-success) 10%, transparent)" },
              { range: "15 – 20", label: "Normal", color: "var(--color-text-muted)", bgColor: "var(--color-surface-2)" },
              { range: "20 – 25", label: "Elevated", color: "#f59e0b", bgColor: "color-mix(in oklab, #f59e0b 10%, transparent)" },
              { range: "> 25", label: "High Fear", color: "var(--color-danger)", bgColor: "color-mix(in oklab, var(--color-danger) 10%, transparent)" },
            ].map(({ range, label, color, bgColor }) => (
              <div
                key={label}
                className="rounded-md px-2.5 py-2.5 border border-[var(--color-border)] text-center"
                style={{ background: bgColor }}
              >
                <div className="font-bold tabular-nums text-sm" style={{ color }}>
                  {range}
                </div>
                <div className="text-[var(--color-text-muted)] mt-1">{label}</div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
