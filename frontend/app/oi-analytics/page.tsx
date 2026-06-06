"use client";

import { useState, useRef, useMemo, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ReferenceLine,
  ResponsiveContainer,
  Cell,
} from "recharts";
import { BarChart2 } from "lucide-react";
import { getOptionChain, getOiBuildup, getFnoSymbols } from "@/lib/fno-api";
import { INDEX_SYMBOLS } from "@/lib/fno-types";
import type { OIBuildupRow } from "@/lib/fno-types";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Input } from "@/components/ui/input";
import {
  Table,
  THead,
  TBody,
  TR,
  TH,
  TD,
} from "@/components/ui/table";
import { PageHeader } from "@/components/common/page-header";
import { cn } from "@/lib/utils";

// ── Constants ─────────────────────────────────────────────────────────────────

const NEAR_STRIKE_RANGE = 15;

// ── Symbol Combobox ───────────────────────────────────────────────────────────

function SymbolCombobox({
  value,
  onChange,
  symbols,
  loading,
}: {
  value: string;
  onChange: (v: string) => void;
  symbols: string[];
  loading: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const wrapRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const filtered = useMemo(() => {
    const q = query.toUpperCase();
    if (!q) return symbols.slice(0, 50);
    return symbols.filter((s) => s.includes(q)).slice(0, 50);
  }, [symbols, query]);

  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (!wrapRef.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  const select = (sym: string) => { onChange(sym); setOpen(false); setQuery(""); };

  return (
    <div ref={wrapRef} className="relative">
      <button
        onClick={() => { setOpen((o) => !o); setTimeout(() => inputRef.current?.focus(), 50); }}
        className="h-9 px-3 w-[140px] rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] text-sm text-white text-left flex items-center justify-between gap-1 hover:bg-[var(--color-surface-2)] transition-colors"
      >
        <span className="font-medium truncate">{value || "Symbol"}</span>
        <span className="text-[var(--color-text-muted)] text-[10px]">▾</span>
      </button>
      {open && (
        <div className="absolute z-50 mt-1 w-52 rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] shadow-xl">
          <div className="p-1.5 border-b border-[var(--color-border)]">
            <Input ref={inputRef} value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search symbol…" className="h-7 text-xs uppercase" />
          </div>
          <ul className="max-h-64 overflow-y-auto py-1">
            {loading && <li className="px-3 py-2 text-xs text-[var(--color-text-muted)]">Loading…</li>}
            {filtered.map((sym) => (
              <li key={sym} onMouseDown={() => select(sym)} className={cn("px-3 py-1.5 text-xs cursor-pointer transition-colors", sym === value ? "bg-[var(--color-primary)]/20 text-[var(--color-primary)]" : "text-white hover:bg-[var(--color-surface-2)]")}>
                {sym}
              </li>
            ))}
            {!loading && filtered.length === 0 && <li className="px-3 py-2 text-xs text-[var(--color-text-muted)]">No match</li>}
          </ul>
        </div>
      )}
    </div>
  );
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtOI(v: number): string {
  if (v >= 1_00_00_000) return `${(v / 1_00_00_000).toFixed(2)}Cr`;
  if (v >= 1_00_000) return `${(v / 1_00_000).toFixed(1)}L`;
  if (v >= 1_000) return `${(v / 1_000).toFixed(1)}K`;
  return v.toLocaleString("en-IN");
}

function fmtPrice(v: number): string {
  return v.toLocaleString("en-IN", { maximumFractionDigits: 0 });
}

function classificationColors(c: OIBuildupRow["classification"]): string {
  switch (c) {
    case "Long Buildup":   return "bg-[var(--color-success)]/15 text-[var(--color-success)]";
    case "Short Buildup":  return "bg-[var(--color-danger)]/15 text-[var(--color-danger)]";
    case "Short Covering": return "bg-blue-500/15 text-blue-400";
    case "Long Unwinding": return "bg-orange-500/15 text-orange-400";
    default:               return "bg-[var(--color-surface-2)] text-[var(--color-text-muted)]";
  }
}

// ── Custom tooltip ────────────────────────────────────────────────────────────

function OITooltip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: { name: string; value: number; fill: string }[];
  label?: string | number;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] p-2 text-xs shadow-xl">
      <div className="font-medium text-white mb-1">Strike {label}</div>
      {payload.map((p) => (
        <div key={p.name} style={{ color: p.fill }}>
          {p.name}: {fmtOI(p.value)}
        </div>
      ))}
    </div>
  );
}

function OIChangeTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: { name: string; value: number; fill: string }[];
  label?: string | number;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] p-2 text-xs shadow-xl">
      <div className="font-medium text-white mb-1">Strike {label}</div>
      {payload.map((p, i) => (
        <div key={i} style={{ color: p.fill }}>
          {p.name}: {p.value > 0 ? "+" : ""}{fmtOI(Math.abs(p.value))}
        </div>
      ))}
    </div>
  );
}

// ── Skeleton loaders ──────────────────────────────────────────────────────────

function ChartSkeleton() {
  return (
    <Card>
      <CardHeader>
        <Skeleton className="h-4 w-32" />
      </CardHeader>
      <CardContent>
        <Skeleton className="h-56 w-full" />
      </CardContent>
    </Card>
  );
}

function TableSkeleton() {
  return (
    <Card>
      <CardHeader>
        <Skeleton className="h-4 w-40" />
      </CardHeader>
      <CardContent className="p-0">
        {Array.from({ length: 8 }).map((_, i) => (
          <div
            key={i}
            className="flex gap-4 px-3 py-2.5 border-b border-[var(--color-border)]"
          >
            <Skeleton className="h-4 w-24" />
            <Skeleton className="h-4 w-20 ml-auto" />
            <Skeleton className="h-4 w-16" />
            <Skeleton className="h-4 w-16" />
            <Skeleton className="h-4 w-24" />
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function OIAnalyticsPage() {
  const [symbol, setSymbol] = useState("NIFTY");

  const symbolsQuery = useQuery({
    queryKey: ["fno-symbols"],
    queryFn: getFnoSymbols,
    staleTime: 5 * 60_000,
  });
  const allSymbols = useMemo(
    () => [...new Set([...INDEX_SYMBOLS, ...(symbolsQuery.data ?? [])])].sort(),
    [symbolsQuery.data],
  );

  const chainQuery = useQuery({
    queryKey: ["option-chain", symbol],
    queryFn: () => getOptionChain(symbol),
    refetchInterval: 60_000,
    staleTime: 30_000,
  });

  const buildupQuery = useQuery({
    queryKey: ["oi-buildup"],
    queryFn: () => getOiBuildup(),
    refetchInterval: 60_000,
    staleTime: 30_000,
  });

  // ── Derive chart data from option chain ──────────────────────────────────

  const chain = chainQuery.data;
  const spot = chain?.meta.underlying ?? 0;
  const firstExpiry = chain?.meta.expiry_dates?.[0];

  const filteredRows = chain
    ? chain.rows
        .filter((r) => !firstExpiry || r.expiry === firstExpiry)
        .sort((a, b) => a.strike - b.strike)
    : [];

  // Find ATM index and limit ±NEAR_STRIKE_RANGE strikes
  const atmIdx = filteredRows.reduce(
    (best, r, i) =>
      Math.abs(r.strike - spot) < Math.abs(filteredRows[best].strike - spot)
        ? i
        : best,
    0
  );
  const visibleRows =
    filteredRows.length > 0
      ? filteredRows.slice(
          Math.max(0, atmIdx - NEAR_STRIKE_RANGE),
          atmIdx + NEAR_STRIKE_RANGE + 1
        )
      : [];

  const oiData = visibleRows.map((r) => ({
    strike: r.strike,
    ceOI: r.CE.oi ?? 0,
    peOI: r.PE.oi ?? 0,
    ceChg: r.CE.oi_chg ?? 0,
    peChg: r.PE.oi_chg ?? 0,
  }));

  const nearestSpotStrike =
    visibleRows.length > 0
      ? visibleRows.reduce((prev, cur) =>
          Math.abs(cur.strike - spot) < Math.abs(prev.strike - spot) ? cur : prev
        ).strike
      : null;

  // ── Loading / Error states ───────────────────────────────────────────────

  const chainLoading = chainQuery.isLoading;
  const buildupLoading = buildupQuery.isLoading;

  return (
    <div className="max-w-[1500px] mx-auto space-y-5">
      <PageHeader
        title="OI Analytics"
        subtitle="Open interest distribution and buildup classification for F&O symbols."
        actions={
          <div className="flex items-center gap-2">
            <span className="text-xs text-[var(--color-text-muted)]">Symbol</span>
            <SymbolCombobox
              value={symbol}
              onChange={setSymbol}
              symbols={allSymbols}
              loading={symbolsQuery.isLoading}
            />
            {spot > 0 && (
              <span className="text-xs text-[var(--color-text-muted)] tnum">
                Spot:{" "}
                <span className="text-white font-medium">
                  {fmtPrice(spot)}
                </span>
              </span>
            )}
          </div>
        }
      />

      {/* ── OI by Strike ── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {chainLoading ? (
          <>
            <ChartSkeleton />
            <ChartSkeleton />
          </>
        ) : chainQuery.isError ? (
          <div className="lg:col-span-2">
            <Card>
              <CardContent className="py-10 text-center text-sm text-[var(--color-danger)]">
                Failed to load option chain: {String(chainQuery.error)}
              </CardContent>
            </Card>
          </div>
        ) : (
          <>
            {/* CE OI */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <BarChart2 className="size-4 text-[var(--color-success)]" />
                  CE Open Interest by Strike
                </CardTitle>
              </CardHeader>
              <CardContent className="pt-2">
                <ResponsiveContainer width="100%" height={240}>
                  <BarChart
                    data={oiData}
                    margin={{ top: 4, right: 8, left: 0, bottom: 0 }}
                  >
                    <XAxis
                      dataKey="strike"
                      tick={{ fontSize: 10, fill: "var(--color-text-muted)" }}
                      tickFormatter={(v: number) =>
                        v >= 10000 ? `${(v / 1000).toFixed(0)}K` : String(v)
                      }
                      axisLine={false}
                      tickLine={false}
                    />
                    <YAxis
                      tick={{ fontSize: 10, fill: "var(--color-text-muted)" }}
                      tickFormatter={fmtOI}
                      axisLine={false}
                      tickLine={false}
                      width={48}
                    />
                    <Tooltip content={<OITooltip />} />
                    {nearestSpotStrike !== null && (
                      <ReferenceLine
                        x={nearestSpotStrike}
                        stroke="var(--color-warning)"
                        strokeDasharray="4 3"
                        label={{
                          value: "Spot",
                          position: "insideTopRight",
                          fontSize: 10,
                          fill: "var(--color-warning)",
                        }}
                      />
                    )}
                    <Bar dataKey="ceOI" name="CE OI" radius={[2, 2, 0, 0]}>
                      {oiData.map((_, i) => (
                        <Cell
                          key={i}
                          fill="var(--color-success)"
                          fillOpacity={0.75}
                        />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>

            {/* PE OI */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <BarChart2 className="size-4 text-[var(--color-danger)]" />
                  PE Open Interest by Strike
                </CardTitle>
              </CardHeader>
              <CardContent className="pt-2">
                <ResponsiveContainer width="100%" height={240}>
                  <BarChart
                    data={oiData}
                    margin={{ top: 4, right: 8, left: 0, bottom: 0 }}
                  >
                    <XAxis
                      dataKey="strike"
                      tick={{ fontSize: 10, fill: "var(--color-text-muted)" }}
                      tickFormatter={(v: number) =>
                        v >= 10000 ? `${(v / 1000).toFixed(0)}K` : String(v)
                      }
                      axisLine={false}
                      tickLine={false}
                    />
                    <YAxis
                      tick={{ fontSize: 10, fill: "var(--color-text-muted)" }}
                      tickFormatter={fmtOI}
                      axisLine={false}
                      tickLine={false}
                      width={48}
                    />
                    <Tooltip content={<OITooltip />} />
                    {nearestSpotStrike !== null && (
                      <ReferenceLine
                        x={nearestSpotStrike}
                        stroke="var(--color-warning)"
                        strokeDasharray="4 3"
                        label={{
                          value: "Spot",
                          position: "insideTopRight",
                          fontSize: 10,
                          fill: "var(--color-warning)",
                        }}
                      />
                    )}
                    <Bar dataKey="peOI" name="PE OI" radius={[2, 2, 0, 0]}>
                      {oiData.map((_, i) => (
                        <Cell
                          key={i}
                          fill="var(--color-danger)"
                          fillOpacity={0.75}
                        />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
          </>
        )}
      </div>

      {/* ── OI Change chart ── */}
      {chainLoading ? (
        <ChartSkeleton />
      ) : !chainQuery.isError && oiData.length > 0 ? (
        <Card>
          <CardHeader>
            <CardTitle>OI Change by Strike (CE vs PE)</CardTitle>
          </CardHeader>
          <CardContent className="pt-2">
            <ResponsiveContainer width="100%" height={220}>
              <BarChart
                data={oiData}
                margin={{ top: 4, right: 8, left: 0, bottom: 0 }}
              >
                <XAxis
                  dataKey="strike"
                  tick={{ fontSize: 10, fill: "var(--color-text-muted)" }}
                  tickFormatter={(v: number) =>
                    v >= 10000 ? `${(v / 1000).toFixed(0)}K` : String(v)
                  }
                  axisLine={false}
                  tickLine={false}
                />
                <YAxis
                  tick={{ fontSize: 10, fill: "var(--color-text-muted)" }}
                  tickFormatter={fmtOI}
                  axisLine={false}
                  tickLine={false}
                  width={52}
                />
                <Tooltip content={<OIChangeTooltip />} />
                <ReferenceLine y={0} stroke="var(--color-border)" />
                {nearestSpotStrike !== null && (
                  <ReferenceLine
                    x={nearestSpotStrike}
                    stroke="var(--color-warning)"
                    strokeDasharray="4 3"
                    label={{
                      value: "Spot",
                      position: "insideTopRight",
                      fontSize: 10,
                      fill: "var(--color-warning)",
                    }}
                  />
                )}
                <Bar dataKey="ceChg" name="CE OI Chg" radius={[2, 2, 0, 0]}>
                  {oiData.map((d, i) => (
                    <Cell
                      key={i}
                      fill={
                        d.ceChg >= 0
                          ? "var(--color-success)"
                          : "var(--color-danger)"
                      }
                      fillOpacity={0.8}
                    />
                  ))}
                </Bar>
                <Bar dataKey="peChg" name="PE OI Chg" radius={[2, 2, 0, 0]}>
                  {oiData.map((d, i) => (
                    <Cell
                      key={i}
                      fill={
                        d.peChg >= 0
                          ? "#ef535088"
                          : "#1ec48a88"
                      }
                      fillOpacity={0.8}
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
            <div className="flex gap-4 mt-2 justify-end text-[11px] text-[var(--color-text-muted)]">
              <span className="flex items-center gap-1">
                <span className="inline-block size-2.5 rounded-sm bg-[var(--color-success)]" />
                CE OI Change
              </span>
              <span className="flex items-center gap-1">
                <span className="inline-block size-2.5 rounded-sm bg-[var(--color-danger)]" />
                PE OI Change
              </span>
            </div>
          </CardContent>
        </Card>
      ) : null}

      {/* ── OI Spurts / Buildup Table ── */}
      {buildupLoading ? (
        <TableSkeleton />
      ) : buildupQuery.isError ? (
        <Card>
          <CardContent className="py-10 text-center text-sm text-[var(--color-danger)]">
            Failed to load OI buildup data.
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center justify-between">
              <span>OI Spurts &amp; Buildup Classification</span>
              <span className="text-[11px] font-normal text-[var(--color-text-muted)]">
                {buildupQuery.data?.length ?? 0} symbols
              </span>
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            {(buildupQuery.data?.length ?? 0) === 0 ? (
              <div className="py-12 text-center text-sm text-[var(--color-text-muted)]">
                No OI spurt data available.
              </div>
            ) : (
              <Table>
                <THead>
                  <TR>
                    <TH>Symbol</TH>
                    <TH className="text-right">OI Current</TH>
                    <TH className="text-right">OI Prev</TH>
                    <TH className="text-right">OI Change</TH>
                    <TH className="text-right">OI Chg %</TH>
                    <TH className="text-right">LTP</TH>
                    <TH className="text-right">Price Chg %</TH>
                    <TH>Classification</TH>
                  </TR>
                </THead>
                <TBody>
                  {(buildupQuery.data ?? []).map((row, i) => (
                    <TR key={`${row.symbol}-${i}`}>
                      <TD className="font-medium text-white">{row.symbol}</TD>
                      <TD className="text-right tnum text-[var(--color-text-muted)]">
                        {row.oi_current.toLocaleString("en-IN")}
                      </TD>
                      <TD className="text-right tnum text-[var(--color-text-muted)]">
                        {row.oi_prev.toLocaleString("en-IN")}
                      </TD>
                      <TD
                        className={cn(
                          "text-right tnum",
                          row.oi_change >= 0
                            ? "text-[var(--color-success)]"
                            : "text-[var(--color-danger)]"
                        )}
                      >
                        {row.oi_change >= 0 ? "+" : ""}
                        {row.oi_change.toLocaleString("en-IN")}
                      </TD>
                      <TD
                        className={cn(
                          "text-right tnum",
                          row.oi_change_pct >= 0
                            ? "text-[var(--color-success)]"
                            : "text-[var(--color-danger)]"
                        )}
                      >
                        {row.oi_change_pct >= 0 ? "+" : ""}
                        {row.oi_change_pct.toFixed(2)}%
                      </TD>
                      <TD className="text-right tnum text-white">
                        {row.ltp.toLocaleString("en-IN")}
                      </TD>
                      <TD
                        className={cn(
                          "text-right tnum",
                          row.price_chg_pct >= 0
                            ? "text-[var(--color-success)]"
                            : "text-[var(--color-danger)]"
                        )}
                      >
                        {row.price_chg_pct >= 0 ? "+" : ""}
                        {row.price_chg_pct.toFixed(2)}%
                      </TD>
                      <TD>
                        <span
                          className={cn(
                            "inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium",
                            classificationColors(row.classification)
                          )}
                        >
                          {row.classification}
                        </span>
                      </TD>
                    </TR>
                  ))}
                </TBody>
              </Table>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
