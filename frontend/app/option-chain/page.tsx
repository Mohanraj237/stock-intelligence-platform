"use client";

import { memo, useState, useEffect, useMemo, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  getOptionChain,
  enrichChainWithGreeks,
  getMaxPain,
  getFnoSymbols,
} from "@/lib/fno-api";
import {
  INDEX_SYMBOLS,
  findAtmStrike,
  type OptionChainResponse,
  type OptionChainRow,
} from "@/lib/fno-types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
} from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { cn, formatPct } from "@/lib/utils";
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ReferenceLine,
  Legend,
} from "recharts";

// ── Banners ───────────────────────────────────────────────────────────────────

function SyntheticBanner({ vix }: { vix?: number }) {
  return (
    <div className="rounded-lg border border-blue-600/30 bg-blue-600/5 px-4 py-2.5 flex items-start gap-3">
      <span className="text-blue-400 text-[13px] mt-0.5">⚗</span>
      <div>
        <span className="text-blue-300 text-xs font-medium">Theoretical prices (Black-Scholes)</span>
        <span className="text-[var(--color-text-muted)] text-xs ml-2">
          NSE live option chain is currently inaccessible. Prices computed from real spot &amp; India VIX
          {vix != null ? ` (${vix.toFixed(1)}%)` : ""} using Black-Scholes.
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
        NSE&apos;s option chain API requires browser-level session authentication.
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

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmt(n: number | undefined | null, dec = 2): string {
  if (n == null || isNaN(n)) return "—";
  return n.toLocaleString("en-IN", {
    minimumFractionDigits: 0,
    maximumFractionDigits: dec,
  });
}

function fmtOi(n: number | undefined): string {
  if (n == null) return "—";
  if (n >= 1_00_000) return `${(n / 1_00_000).toFixed(1)}L`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

function pctCell(n: number | undefined): { text: string; cls: string } {
  if (n == null) return { text: "—", cls: "text-[var(--color-text-muted)]" };
  const cls = n > 0 ? "up" : n < 0 ? "down" : "text-[var(--color-text-muted)]";
  return { text: formatPct(n, { sign: true }), cls };
}

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

  const select = (sym: string) => {
    onChange(sym);
    setOpen(false);
    setQuery("");
  };

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
            <Input
              ref={inputRef}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search symbol…"
              className="h-7 text-xs uppercase"
            />
          </div>
          <ul className="max-h-64 overflow-y-auto py-1">
            {loading && (
              <li className="px-3 py-2 text-xs text-[var(--color-text-muted)]">Loading…</li>
            )}
            {filtered.map((sym) => (
              <li
                key={sym}
                onMouseDown={() => select(sym)}
                className={cn(
                  "px-3 py-1.5 text-xs cursor-pointer transition-colors",
                  sym === value
                    ? "bg-[var(--color-primary)]/20 text-[var(--color-primary)]"
                    : "text-white hover:bg-[var(--color-surface-2)]",
                )}
              >
                {sym}
              </li>
            ))}
            {!loading && filtered.length === 0 && (
              <li className="px-3 py-2 text-xs text-[var(--color-text-muted)]">No match</li>
            )}
          </ul>
        </div>
      )}
    </div>
  );
}

// ── Chain Table Row (memoized) ────────────────────────────────────────────────

const ChainRow = memo(function ChainRow({
  row,
  isAtm,
}: {
  row: OptionChainRow;
  isAtm: boolean;
}) {
  const ce = row.CE;
  const pe = row.PE;

  const ceDominates = (ce.oi ?? 0) > (pe.oi ?? 0);
  const peDominates = (pe.oi ?? 0) > (ce.oi ?? 0);

  const ceOiChg = pctCell(ce.oi_chg_pct);
  const peOiChg = pctCell(pe.oi_chg_pct);

  return (
    <tr
      className={cn(
        "border-b border-[var(--color-border)] text-xs tnum transition-colors",
        isAtm
          ? "bg-[var(--color-primary)]/10"
          : ceDominates
          ? "bg-[var(--color-success)]/5 hover:bg-[var(--color-success)]/10"
          : peDominates
          ? "bg-[var(--color-danger)]/5 hover:bg-[var(--color-danger)]/10"
          : "hover:bg-[var(--color-surface-2)]/60",
      )}
    >
      <td className="px-2 py-1.5 text-right text-[var(--color-text-muted)]">{fmtOi(ce.oi)}</td>
      <td className={cn("px-2 py-1.5 text-right", ceOiChg.cls)}>{ceOiChg.text}</td>
      <td className="px-2 py-1.5 text-right text-[var(--color-text-muted)]">{fmtOi(ce.vol)}</td>
      <td className="px-2 py-1.5 text-right text-[var(--color-text-muted)]">{ce.iv ? `${fmt(ce.iv, 1)}%` : "—"}</td>
      <td className="px-2 py-1.5 text-right text-white font-medium">{ce.ltp ? `₹${fmt(ce.ltp)}` : "—"}</td>
      <td className="px-2 py-1.5 text-right text-[var(--color-text-muted)]">{ce.delta != null ? fmt(ce.delta, 3) : "—"}</td>

      <td className={cn(
        "px-3 py-1.5 text-center font-bold",
        isAtm ? "text-[var(--color-primary)] bg-[var(--color-primary)]/20" : "text-white",
      )}>
        {row.strike.toLocaleString("en-IN")}
      </td>

      <td className="px-2 py-1.5 text-left text-[var(--color-text-muted)]">{pe.delta != null ? fmt(pe.delta, 3) : "—"}</td>
      <td className="px-2 py-1.5 text-left text-white font-medium">{pe.ltp ? `₹${fmt(pe.ltp)}` : "—"}</td>
      <td className="px-2 py-1.5 text-left text-[var(--color-text-muted)]">{pe.iv ? `${fmt(pe.iv, 1)}%` : "—"}</td>
      <td className="px-2 py-1.5 text-left text-[var(--color-text-muted)]">{fmtOi(pe.vol)}</td>
      <td className={cn("px-2 py-1.5 text-left", peOiChg.cls)}>{peOiChg.text}</td>
      <td className="px-2 py-1.5 text-left text-[var(--color-text-muted)]">{fmtOi(pe.oi)}</td>
    </tr>
  );
});

// ── OI Bar Chart ──────────────────────────────────────────────────────────────

interface OiChartPoint {
  strike: number;
  CE_OI: number;
  PE_OI: number;
}

const OiBarChart = memo(function OiBarChart({
  data,
  atmStrike,
}: {
  data: OiChartPoint[];
  atmStrike: number;
}) {
  return (
    <div style={{ width: "100%", height: 280 }}>
      <ResponsiveContainer>
        <BarChart data={data} margin={{ top: 8, right: 16, bottom: 0, left: 8 }} barCategoryGap="20%">
          <XAxis
            dataKey="strike"
            tick={{ fill: "#94a3b8", fontSize: 10 }}
            tickFormatter={(v: number) => v.toLocaleString("en-IN")}
            interval="preserveStartEnd"
          />
          <YAxis
            tick={{ fill: "#94a3b8", fontSize: 10 }}
            tickFormatter={(v: number) =>
              v >= 1_00_000 ? `${(v / 1_00_000).toFixed(0)}L` : `${(v / 1_000).toFixed(0)}K`
            }
            width={48}
          />
          <Tooltip
            contentStyle={{ background: "#131822", border: "1px solid #232a3a", fontSize: 12, color: "#fff" }}
            formatter={(val: number, name: string) => [fmtOi(val), name === "CE_OI" ? "CE OI" : "PE OI"]}
            labelFormatter={(label: number) => `Strike: ${label.toLocaleString("en-IN")}`}
          />
          <Legend
            wrapperStyle={{ fontSize: 11, color: "#94a3b8" }}
            formatter={(val: string) => (val === "CE_OI" ? "CE OI" : "PE OI")}
          />
          <ReferenceLine
            x={atmStrike}
            stroke="var(--color-primary)"
            strokeDasharray="4 2"
            label={{ value: "ATM", position: "top", fill: "var(--color-primary)", fontSize: 10 }}
          />
          <Bar dataKey="CE_OI" name="CE_OI" fill="#1ec48a" radius={[2, 2, 0, 0]} />
          <Bar dataKey="PE_OI" name="PE_OI" fill="#ef5350" radius={[2, 2, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
});

// ── Page ──────────────────────────────────────────────────────────────────────

export default function OptionChainPage() {
  const [symbol, setSymbol] = useState<string>("NIFTY");
  const [expiry, setExpiry] = useState<string>("");
  const [lastAttempt, setLastAttempt] = useState<string>("");

  // Load all F&O symbols
  const symbolsQuery = useQuery<string[]>({
    queryKey: ["fno", "symbols"],
    queryFn: getFnoSymbols,
    staleTime: 10 * 60_000,
    gcTime: 30 * 60_000,
  });

  const allSymbols = useMemo(() => {
    const extra = (symbolsQuery.data ?? []).filter((s) => !INDEX_SYMBOLS.includes(s));
    return [...INDEX_SYMBOLS, ...extra.sort()];
  }, [symbolsQuery.data]);

  // Fetch raw chain whenever symbol changes
  const chainQuery = useQuery<OptionChainResponse>({
    queryKey: ["fno", "option-chain", symbol],
    queryFn: async () => {
      setLastAttempt(new Date().toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", second: "2-digit" }));
      return getOptionChain(symbol);
    },
    refetchInterval: (query) => {
      const d = query.state.data as OptionChainResponse | undefined;
      if (d && (d.rows.length === 0 || d.meta.synthetic)) return false;
      return 30_000;
    },
    staleTime: 15_000,
  });

  useEffect(() => {
    const dates = chainQuery.data?.meta.expiry_dates ?? [];
    if (dates.length > 0 && (!expiry || !dates.includes(expiry))) {
      setExpiry(dates[0]);
    }
  }, [chainQuery.data, symbol]); // eslint-disable-line react-hooks/exhaustive-deps

  const enriched = useMemo<OptionChainResponse | null>(() => {
    if (!chainQuery.data) return null;
    return enrichChainWithGreeks(chainQuery.data, expiry);
  }, [chainQuery.data, expiry]);

  const maxPain = useMemo<number>(() => {
    if (!chainQuery.data) return 0;
    return getMaxPain(chainQuery.data, expiry);
  }, [chainQuery.data, expiry]);

  const spot = chainQuery.data?.meta.underlying ?? 0;
  const expiryDates = chainQuery.data?.meta.expiry_dates ?? [];

  const strikes = useMemo(() => (enriched?.rows ?? []).map((r) => r.strike), [enriched]);
  const atmStrike = useMemo(() => findAtmStrike(strikes, spot), [strikes, spot]);

  const sortedRows = useMemo(
    () => [...(enriched?.rows ?? [])].sort((a, b) => a.strike - b.strike),
    [enriched],
  );

  const chartData = useMemo<OiChartPoint[]>(() => {
    if (!sortedRows.length) return [];
    const atmIdx = sortedRows.findIndex((r) => r.strike === atmStrike);
    const center = atmIdx >= 0 ? atmIdx : Math.floor(sortedRows.length / 2);
    const window = sortedRows.slice(Math.max(0, center - 15), Math.min(sortedRows.length, center + 16));
    return window.map((r) => ({ strike: r.strike, CE_OI: r.CE.oi ?? 0, PE_OI: r.PE.oi ?? 0 }));
  }, [sortedRows, atmStrike]);

  const isLoading = chainQuery.isLoading;

  return (
    <div className="space-y-5 max-w-[1400px] mx-auto">
      {/* Header */}
      <header className="flex flex-wrap items-end gap-4 justify-between">
        <div>
          <h1 className="text-xl font-semibold text-white">Option Chain</h1>
          <p className="text-xs text-[var(--color-text-muted)] mt-0.5">
            NSE option chain with Greeks · {allSymbols.length} symbols · auto-refresh 30s
          </p>
        </div>

        <div className="flex items-center gap-3 flex-wrap">
          <SymbolCombobox
            value={symbol}
            onChange={(v) => { setSymbol(v); setExpiry(""); }}
            symbols={allSymbols}
            loading={symbolsQuery.isLoading}
          />

          <Select value={expiry} onValueChange={setExpiry} disabled={expiryDates.length === 0}>
            <SelectTrigger className="w-[160px]">
              <SelectValue placeholder="Expiry" />
            </SelectTrigger>
            <SelectContent>
              {expiryDates.map((d) => (
                <SelectItem key={d} value={d}>{d}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </header>

      {/* Stats bar */}
      {isLoading ? (
        <div className="flex gap-4">
          <Skeleton className="h-8 w-40" />
          <Skeleton className="h-8 w-40" />
          <Skeleton className="h-8 w-32" />
        </div>
      ) : (
        <div className="flex flex-wrap items-center gap-3 text-sm">
          <div className="flex items-center gap-2">
            <span className="text-[var(--color-text-muted)] text-xs uppercase tracking-wider">Spot</span>
            <span className="font-semibold text-white tnum">₹{spot.toLocaleString("en-IN")}</span>
          </div>
          <div className="w-px h-4 bg-[var(--color-border)]" />
          <div className="flex items-center gap-2">
            <span className="text-[var(--color-text-muted)] text-xs uppercase tracking-wider">ATM</span>
            <Badge variant="info">{atmStrike.toLocaleString("en-IN")}</Badge>
          </div>
          <div className="w-px h-4 bg-[var(--color-border)]" />
          <div className="flex items-center gap-2">
            <span className="text-[var(--color-text-muted)] text-xs uppercase tracking-wider">Max Pain</span>
            <Badge variant="warning">₹{maxPain.toLocaleString("en-IN")}</Badge>
          </div>

          {chainQuery.data && (
            <>
              <div className="w-px h-4 bg-[var(--color-border)]" />
              <div className="flex items-center gap-3 text-xs text-[var(--color-text-muted)]">
                <span>CE OI: <span className="up font-medium">{fmtOi(chainQuery.data.meta.total_ce_oi)}</span></span>
                <span>PE OI: <span className="down font-medium">{fmtOi(chainQuery.data.meta.total_pe_oi)}</span></span>
                <span>PCR: <span className="text-white font-medium">
                  {chainQuery.data.meta.total_ce_oi
                    ? (chainQuery.data.meta.total_pe_oi / chainQuery.data.meta.total_ce_oi).toFixed(3)
                    : "—"}
                </span></span>
              </div>
            </>
          )}

          {chainQuery.isFetching && !isLoading && (
            <span className="text-[10px] text-[var(--color-text-muted)] animate-pulse">refreshing…</span>
          )}
        </div>
      )}

      {/* Synthetic data banner */}
      {!isLoading && sortedRows.length > 0 && chainQuery.data?.meta.synthetic && (
        <SyntheticBanner vix={chainQuery.data.meta.vix} />
      )}

      {/* Data unavailable panel */}
      {!isLoading && sortedRows.length === 0 && (
        <div className="space-y-1.5">
          <DataUnavailable onRetry={() => chainQuery.refetch()} />
          {lastAttempt && (
            <p className="text-[10px] text-center text-[var(--color-text-muted)]">Last attempted: {lastAttempt}</p>
          )}
        </div>
      )}

      {/* Option chain table */}
      <Card>
        <CardContent className="p-0 overflow-x-auto">
          {isLoading ? (
            <div className="p-6 space-y-2">
              {Array.from({ length: 10 }).map((_, i) => <Skeleton key={i} className="h-8 w-full" />)}
            </div>
          ) : (
            <table className="w-full text-xs min-w-[900px]">
              <thead className="sticky top-0 z-10 border-b border-[var(--color-border)] bg-[var(--color-surface)]">
                <tr className="border-b border-[var(--color-border)]/50">
                  <th colSpan={6} className="py-1.5 text-center text-[10px] font-semibold tracking-wider up bg-[var(--color-success)]/10">CALLS (CE)</th>
                  <th className="py-1.5 bg-[var(--color-surface-2)]" />
                  <th colSpan={6} className="py-1.5 text-center text-[10px] font-semibold tracking-wider down bg-[var(--color-danger)]/10">PUTS (PE)</th>
                </tr>
                <tr className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)]">
                  <th className="px-2 py-2 text-right">OI</th>
                  <th className="px-2 py-2 text-right">OI Chg%</th>
                  <th className="px-2 py-2 text-right">Vol</th>
                  <th className="px-2 py-2 text-right">IV</th>
                  <th className="px-2 py-2 text-right">LTP</th>
                  <th className="px-2 py-2 text-right">Delta</th>
                  <th className="px-3 py-2 text-center bg-[var(--color-surface-2)] font-bold text-white">Strike</th>
                  <th className="px-2 py-2 text-left">Delta</th>
                  <th className="px-2 py-2 text-left">LTP</th>
                  <th className="px-2 py-2 text-left">IV</th>
                  <th className="px-2 py-2 text-left">Vol</th>
                  <th className="px-2 py-2 text-left">OI Chg%</th>
                  <th className="px-2 py-2 text-left">OI</th>
                </tr>
              </thead>
              <tbody>
                {sortedRows.map((row) => (
                  <ChainRow key={`${row.strike}-${row.expiry}`} row={row} isAtm={row.strike === atmStrike} />
                ))}
                {sortedRows.length === 0 && (
                  <tr>
                    <td colSpan={13} className="px-4 py-12 text-center text-sm text-[var(--color-text-muted)]">
                      {expiry ? "No data for selected expiry" : "Select a symbol to load the option chain"}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>

      {/* OI Bar Chart */}
      {chartData.length > 0 && (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle>Open Interest by Strike · {symbol} {expiry}</CardTitle>
              <div className="flex items-center gap-4 text-[11px] text-[var(--color-text-muted)]">
                <span className="inline-flex items-center gap-1">
                  <span className="size-2.5 rounded-sm" style={{ background: "#1ec48a" }} />CE OI
                </span>
                <span className="inline-flex items-center gap-1">
                  <span className="size-2.5 rounded-sm" style={{ background: "#ef5350" }} />PE OI
                </span>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            {isLoading ? <Skeleton className="h-64 w-full" /> : <OiBarChart data={chartData} atmStrike={atmStrike} />}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
