"use client";

import { useState, useEffect, useMemo, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  BarChart,
  Bar,
  LineChart,
  Line,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ReferenceLine,
  ResponsiveContainer,
  Cell,
  Legend,
} from "recharts";
import {
  getOptionChain,
  buildGreeksRows,
  getGex,
  getFnoSymbols,
} from "@/lib/fno-api";
import { bsPrice, RISK_FREE_RATE } from "@/lib/greeks";
import {
  INDEX_SYMBOLS,
  findAtmStrike,
  daysToExpiry,
  getLotSize,
  type GreeksRow,
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
import { Input } from "@/components/ui/input";
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
          NSE live option chain is unavailable. Greeks are computed from real spot &amp; India VIX
          {vix != null ? ` (${vix.toFixed(1)}%)` : ""} using Black-Scholes. OI values are illustrative.
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

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmt(n: number | undefined | null, dec = 4): string {
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
  return n.toLocaleString("en-IN");
}

// ── Tabs ──────────────────────────────────────────────────────────────────────

type TabId = "table" | "gex" | "iv-skew" | "theta-decay" | "delta-neutral";

const TABS: { id: TabId; label: string }[] = [
  { id: "table",         label: "Greeks Table"   },
  { id: "gex",           label: "GEX"            },
  { id: "iv-skew",       label: "IV Skew"        },
  { id: "theta-decay",   label: "Theta Decay"    },
  { id: "delta-neutral", label: "Delta Neutral"  },
];

// ── Chart Tooltip ─────────────────────────────────────────────────────────────

function ChartTooltip({
  active,
  payload,
  label,
  labelPrefix = "Strike: ",
}: {
  active?: boolean;
  payload?: { name: string; value: number; color: string }[];
  label?: string | number;
  labelPrefix?: string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] p-2 text-xs shadow-xl">
      <div className="font-medium text-white mb-1">{labelPrefix}{label}</div>
      {payload.map((p, i) => (
        <div key={i} style={{ color: p.color }}>
          {p.name}: {fmt(p.value, 4)}
        </div>
      ))}
    </div>
  );
}

// ── Tab 1: Greeks Table ───────────────────────────────────────────────────────

function GreeksTable({
  rows,
  atmStrike,
}: {
  rows: GreeksRow[];
  atmStrike: number;
}) {
  const sorted = [...rows].sort((a, b) => a.strike - b.strike);

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs min-w-[900px]">
        <thead className="sticky top-0 z-10 bg-[var(--color-surface)] border-b border-[var(--color-border)]">
          <tr>
            <th colSpan={6} className="py-1.5 text-center text-[10px] font-semibold tracking-wider text-[var(--color-success)] bg-[var(--color-success)]/10 border-r border-[var(--color-border)]">
              CALLS (CE)
            </th>
            <th className="px-3 py-1.5 text-center font-bold text-white bg-[var(--color-surface-2)] border-r border-[var(--color-border)]">
              Strike
            </th>
            <th colSpan={6} className="py-1.5 text-center text-[10px] font-semibold tracking-wider text-[var(--color-danger)] bg-[var(--color-danger)]/10">
              PUTS (PE)
            </th>
          </tr>
          <tr className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)]">
            <th className="px-2 py-2 text-right">Delta</th>
            <th className="px-2 py-2 text-right">Gamma</th>
            <th className="px-2 py-2 text-right">Theta</th>
            <th className="px-2 py-2 text-right">Vega</th>
            <th className="px-2 py-2 text-right">IV</th>
            <th className="px-2 py-2 text-right border-r border-[var(--color-border)]">LTP</th>
            <th className="px-3 py-2 text-center bg-[var(--color-surface-2)] border-r border-[var(--color-border)] text-white">Strike</th>
            <th className="px-2 py-2 text-left">LTP</th>
            <th className="px-2 py-2 text-left">IV</th>
            <th className="px-2 py-2 text-left">Vega</th>
            <th className="px-2 py-2 text-left">Theta</th>
            <th className="px-2 py-2 text-left">Gamma</th>
            <th className="px-2 py-2 text-left">Delta</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((row) => {
            const isAtm = row.strike === atmStrike;
            return (
              <tr
                key={row.strike}
                className={cn(
                  "border-b border-[var(--color-border)] transition-colors",
                  isAtm
                    ? "bg-blue-500/10"
                    : "hover:bg-[var(--color-surface-2)]/60",
                )}
              >
                {/* CE Delta */}
                <td className={cn(
                  "px-2 py-1.5 text-right tnum",
                  row.CE_delta >= 0 ? "text-[var(--color-success)]" : "text-[var(--color-danger)]"
                )}>
                  {fmt(row.CE_delta, 3)}
                </td>
                {/* CE Gamma */}
                <td className="px-2 py-1.5 text-right tnum text-[var(--color-text-muted)]">
                  {fmt(row.CE_gamma, 5)}
                </td>
                {/* CE Theta — always red */}
                <td className="px-2 py-1.5 text-right tnum text-[var(--color-danger)]">
                  {fmt(row.CE_theta, 3)}
                </td>
                {/* CE Vega */}
                <td className="px-2 py-1.5 text-right tnum text-[var(--color-text-muted)]">
                  {fmt(row.CE_vega, 3)}
                </td>
                {/* CE IV */}
                <td className="px-2 py-1.5 text-right tnum text-[var(--color-text-muted)]">
                  {row.CE_iv ? `${fmt(row.CE_iv, 1)}%` : "—"}
                </td>
                {/* CE LTP */}
                <td className="px-2 py-1.5 text-right tnum font-medium text-white border-r border-[var(--color-border)]">
                  {row.CE_ltp ? `₹${fmt(row.CE_ltp, 2)}` : "—"}
                </td>

                {/* Strike */}
                <td className={cn(
                  "px-3 py-1.5 text-center font-bold bg-[var(--color-surface-2)] border-r border-[var(--color-border)]",
                  isAtm ? "text-blue-400" : "text-white",
                )}>
                  {row.strike.toLocaleString("en-IN")}
                  {isAtm && <span className="ml-1 text-[9px] font-normal text-blue-400">ATM</span>}
                </td>

                {/* PE LTP */}
                <td className="px-2 py-1.5 text-left tnum font-medium text-white">
                  {row.PE_ltp ? `₹${fmt(row.PE_ltp, 2)}` : "—"}
                </td>
                {/* PE IV */}
                <td className="px-2 py-1.5 text-left tnum text-[var(--color-text-muted)]">
                  {row.PE_iv ? `${fmt(row.PE_iv, 1)}%` : "—"}
                </td>
                {/* PE Vega */}
                <td className="px-2 py-1.5 text-left tnum text-[var(--color-text-muted)]">
                  {fmt(row.PE_vega, 3)}
                </td>
                {/* PE Theta — always red */}
                <td className="px-2 py-1.5 text-left tnum text-[var(--color-danger)]">
                  {fmt(row.PE_theta, 3)}
                </td>
                {/* PE Gamma */}
                <td className="px-2 py-1.5 text-left tnum text-[var(--color-text-muted)]">
                  {fmt(row.PE_gamma, 5)}
                </td>
                {/* PE Delta */}
                <td className={cn(
                  "px-2 py-1.5 text-left tnum",
                  row.PE_delta >= 0 ? "text-[var(--color-success)]" : "text-[var(--color-danger)]"
                )}>
                  {fmt(row.PE_delta, 3)}
                </td>
              </tr>
            );
          })}
          {sorted.length === 0 && (
            <tr>
              <td colSpan={13} className="px-4 py-12 text-center text-sm text-[var(--color-text-muted)]">
                No data for selected expiry.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

// ── Tab 2: GEX Chart ──────────────────────────────────────────────────────────

function GexChart({
  data,
  spot,
  atmStrike,
}: {
  data: { strike: number; gex_cr: number }[];
  spot: number;
  atmStrike: number;
}) {
  const spotStrike = data.reduce(
    (prev, cur) =>
      Math.abs(cur.strike - spot) < Math.abs(prev.strike - spot) ? cur : prev,
    data[0] ?? { strike: 0 },
  ).strike;

  return (
    <ResponsiveContainer width="100%" height={340}>
      <BarChart data={data} margin={{ top: 16, right: 16, bottom: 0, left: 12 }}>
        <XAxis
          dataKey="strike"
          tick={{ fill: "#94a3b8", fontSize: 10 }}
          tickFormatter={(v: number) => v.toLocaleString("en-IN")}
          interval="preserveStartEnd"
        />
        <YAxis
          tick={{ fill: "#94a3b8", fontSize: 10 }}
          tickFormatter={(v: number) => `${v.toFixed(1)}Cr`}
          width={56}
        />
        <Tooltip
          contentStyle={{ background: "#131822", border: "1px solid #232a3a", fontSize: 12, color: "#fff" }}
          formatter={(val: number) => [`${val.toFixed(2)} Cr`, "GEX"]}
          labelFormatter={(l: number) => `Strike: ${l.toLocaleString("en-IN")}`}
        />
        <ReferenceLine
          y={0}
          stroke="#94a3b8"
          strokeDasharray="4 2"
          label={{ value: "Gamma Flip", position: "insideTopLeft", fill: "#94a3b8", fontSize: 10 }}
        />
        {spotStrike !== 0 && (
          <ReferenceLine
            x={spotStrike}
            stroke="var(--color-primary)"
            strokeDasharray="4 2"
            label={{ value: "Spot", position: "top", fill: "var(--color-primary)", fontSize: 10 }}
          />
        )}
        <Bar dataKey="gex_cr" name="GEX (Cr)" radius={[2, 2, 0, 0]}>
          {data.map((d, i) => (
            <Cell
              key={i}
              fill={d.gex_cr >= 0 ? "#1ec48a" : "#ef5350"}
            />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

// ── Tab 3: IV Skew ────────────────────────────────────────────────────────────

function IvSkewChart({ rows, atmStrike }: { rows: GreeksRow[]; atmStrike: number }) {
  const data = [...rows]
    .sort((a, b) => a.strike - b.strike)
    .map((r) => ({
      strike: r.strike,
      CE_IV: r.CE_iv || 0,
      PE_IV: r.PE_iv || 0,
    }));

  const spotX = rows.find((r) => r.strike === atmStrike)?.strike ?? 0;

  return (
    <ResponsiveContainer width="100%" height={340}>
      <LineChart data={data} margin={{ top: 16, right: 24, bottom: 0, left: 12 }}>
        <XAxis
          dataKey="strike"
          tick={{ fill: "#94a3b8", fontSize: 10 }}
          tickFormatter={(v: number) => v.toLocaleString("en-IN")}
          interval="preserveStartEnd"
        />
        <YAxis
          tick={{ fill: "#94a3b8", fontSize: 10 }}
          tickFormatter={(v: number) => `${v.toFixed(0)}%`}
          width={44}
        />
        <Tooltip
          content={
            <ChartTooltip labelPrefix="Strike: " />
          }
        />
        <Legend wrapperStyle={{ fontSize: 11, color: "#94a3b8" }} />
        {spotX !== 0 && (
          <ReferenceLine
            x={spotX}
            stroke="#6366f1"
            strokeDasharray="4 2"
            label={{ value: "ATM", position: "top", fill: "#6366f1", fontSize: 10 }}
          />
        )}
        <Line type="monotone" dataKey="CE_IV" name="CE IV" stroke="#1ec48a" dot={false} strokeWidth={2} />
        <Line type="monotone" dataKey="PE_IV" name="PE IV" stroke="#ef5350" dot={false} strokeWidth={2} />
      </LineChart>
    </ResponsiveContainer>
  );
}

// ── Tab 4: Theta Decay Curve ──────────────────────────────────────────────────

function ThetaDecayChart({
  spot,
  atmStrike,
  avgIv,
}: {
  spot: number;
  atmStrike: number;
  avgIv: number;
}) {
  const DTE_POINTS = [30, 25, 20, 15, 10, 7, 5, 3, 2, 1, 0];

  const data = DTE_POINTS.map((dte) => {
    const T = Math.max(dte, 0.001) / 365;
    const ce = bsPrice(spot, atmStrike, T, RISK_FREE_RATE, avgIv, "CE");
    const pe = bsPrice(spot, atmStrike, T, RISK_FREE_RATE, avgIv, "PE");
    return { dte, premium: +(ce + pe).toFixed(2) };
  });

  return (
    <ResponsiveContainer width="100%" height={340}>
      <AreaChart data={data} margin={{ top: 16, right: 24, bottom: 0, left: 12 }}>
        <defs>
          <linearGradient id="thetaGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor="#6366f1" stopOpacity={0.35} />
            <stop offset="95%" stopColor="#6366f1" stopOpacity={0.02} />
          </linearGradient>
        </defs>
        <XAxis
          dataKey="dte"
          reversed
          tick={{ fill: "#94a3b8", fontSize: 10 }}
          label={{ value: "Days to Expiry", position: "insideBottom", offset: -4, fill: "#94a3b8", fontSize: 11 }}
          height={36}
        />
        <YAxis
          tick={{ fill: "#94a3b8", fontSize: 10 }}
          tickFormatter={(v: number) => `₹${v.toFixed(0)}`}
          width={52}
        />
        <Tooltip
          contentStyle={{ background: "#131822", border: "1px solid #232a3a", fontSize: 12, color: "#fff" }}
          formatter={(val: number) => [`₹${val.toFixed(2)}`, "Straddle Premium"]}
          labelFormatter={(l: number) => `DTE: ${l}`}
        />
        <Area
          type="monotone"
          dataKey="premium"
          name="Straddle Premium"
          stroke="#6366f1"
          fill="url(#thetaGrad)"
          strokeWidth={2}
          dot={false}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}

// ── Tab 5: Delta Neutral ──────────────────────────────────────────────────────

function DeltaNeutralTab({
  rows,
  atmStrike,
  symbol,
  spot,
}: {
  rows: GreeksRow[];
  atmStrike: number;
  symbol: string;
  spot: number;
}) {
  const lotSize = getLotSize(symbol);
  const sorted = [...rows].sort((a, b) => a.strike - b.strike);
  const atmRow = rows.find((r) => r.strike === atmStrike);

  const netDelta = atmRow ? atmRow.CE_delta + atmRow.PE_delta : 0;
  const hedgeLots = Math.round(Math.abs(netDelta) * lotSize);

  return (
    <div className="space-y-4">
      {/* Explanation card */}
      <div className="rounded-md border border-[var(--color-border)] bg-[var(--color-surface-2)] p-4 text-sm space-y-1">
        <div className="font-medium text-white">Short Straddle Delta Exposure — {symbol}</div>
        <p className="text-xs text-[var(--color-text-muted)]">
          A short straddle at ATM ({atmStrike.toLocaleString("en-IN")}) sells one CE and one PE at the same strike.
          Net delta = CE delta + PE delta. Near ATM the net delta is close to zero; however, as spot moves
          the position develops directional exposure. Hedge using {symbol} futures: 1 lot = {lotSize.toLocaleString("en-IN")} units.
        </p>
        <div className="flex flex-wrap gap-6 pt-2 text-xs">
          <div>
            <span className="text-[var(--color-text-muted)]">ATM Strike </span>
            <span className="text-white font-semibold tnum">{atmStrike.toLocaleString("en-IN")}</span>
          </div>
          <div>
            <span className="text-[var(--color-text-muted)]">CE Delta </span>
            <span className={cn("font-semibold tnum", (atmRow?.CE_delta ?? 0) >= 0 ? "text-[var(--color-success)]" : "text-[var(--color-danger)]")}>
              {fmt(atmRow?.CE_delta, 4)}
            </span>
          </div>
          <div>
            <span className="text-[var(--color-text-muted)]">PE Delta </span>
            <span className={cn("font-semibold tnum", (atmRow?.PE_delta ?? 0) >= 0 ? "text-[var(--color-success)]" : "text-[var(--color-danger)]")}>
              {fmt(atmRow?.PE_delta, 4)}
            </span>
          </div>
          <div>
            <span className="text-[var(--color-text-muted)]">Net Delta </span>
            <span className={cn("font-semibold tnum", netDelta >= 0 ? "text-[var(--color-success)]" : "text-[var(--color-danger)]")}>
              {fmt(netDelta, 4)}
            </span>
          </div>
          <div>
            <span className="text-[var(--color-text-muted)]">Futures to hedge </span>
            <span className="text-white font-semibold tnum">
              {hedgeLots === 0 ? "None needed" : `${hedgeLots} ${hedgeLots > 0 ? "short" : "long"} units`}
            </span>
          </div>
        </div>
      </div>

      {/* Delta table */}
      <div className="overflow-x-auto">
        <table className="w-full text-xs min-w-[640px]">
          <thead className="sticky top-0 z-10 bg-[var(--color-surface)] border-b border-[var(--color-border)]">
            <tr className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)]">
              <th className="px-3 py-2 text-center font-bold text-white">Strike</th>
              <th className="px-3 py-2 text-right">CE Delta</th>
              <th className="px-3 py-2 text-right">CE Delta/Lot</th>
              <th className="px-3 py-2 text-right">PE Delta</th>
              <th className="px-3 py-2 text-right">PE Delta/Lot</th>
              <th className="px-3 py-2 text-right">Net Delta</th>
              <th className="px-3 py-2 text-right">Net Delta/Lot</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((row) => {
              const isAtm = row.strike === atmStrike;
              const netD = row.CE_delta + row.PE_delta;
              return (
                <tr
                  key={row.strike}
                  className={cn(
                    "border-b border-[var(--color-border)] transition-colors",
                    isAtm ? "bg-blue-500/10" : "hover:bg-[var(--color-surface-2)]/60",
                  )}
                >
                  <td className={cn("px-3 py-1.5 text-center font-bold tnum", isAtm ? "text-blue-400" : "text-white")}>
                    {row.strike.toLocaleString("en-IN")}
                    {isAtm && <span className="ml-1 text-[9px] font-normal">ATM</span>}
                  </td>
                  <td className={cn("px-3 py-1.5 text-right tnum", row.CE_delta >= 0 ? "text-[var(--color-success)]" : "text-[var(--color-danger)]")}>
                    {fmt(row.CE_delta, 4)}
                  </td>
                  <td className={cn("px-3 py-1.5 text-right tnum", row.CE_delta >= 0 ? "text-[var(--color-success)]" : "text-[var(--color-danger)]")}>
                    {fmt(row.CE_delta * lotSize, 2)}
                  </td>
                  <td className={cn("px-3 py-1.5 text-right tnum", row.PE_delta >= 0 ? "text-[var(--color-success)]" : "text-[var(--color-danger)]")}>
                    {fmt(row.PE_delta, 4)}
                  </td>
                  <td className={cn("px-3 py-1.5 text-right tnum", row.PE_delta >= 0 ? "text-[var(--color-success)]" : "text-[var(--color-danger)]")}>
                    {fmt(row.PE_delta * lotSize, 2)}
                  </td>
                  <td className={cn("px-3 py-1.5 text-right tnum font-semibold", netD >= 0 ? "text-[var(--color-success)]" : "text-[var(--color-danger)]")}>
                    {fmt(netD, 4)}
                  </td>
                  <td className={cn("px-3 py-1.5 text-right tnum font-semibold", netD >= 0 ? "text-[var(--color-success)]" : "text-[var(--color-danger)]")}>
                    {fmt(netD * lotSize, 2)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
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

// ── Page ──────────────────────────────────────────────────────────────────────

export default function GreeksDashboardPage() {
  const [symbol, setSymbol] = useState<string>("NIFTY");
  const [expiry, setExpiry] = useState<string>("");
  const [activeTab, setActiveTab] = useState<TabId>("table");

  const symbolsQuery = useQuery({
    queryKey: ["fno-symbols"],
    queryFn: getFnoSymbols,
    staleTime: 5 * 60_000,
  });
  const allSymbols = useMemo(
    () => [...new Set([...INDEX_SYMBOLS, ...(symbolsQuery.data ?? [])])].sort(),
    [symbolsQuery.data],
  );

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

  useEffect(() => {
    const dates = chainQuery.data?.meta.expiry_dates ?? [];
    if (dates.length > 0 && (!expiry || !dates.includes(expiry))) {
      setExpiry(dates[0]);
    }
  }, [chainQuery.data, symbol]); // eslint-disable-line react-hooks/exhaustive-deps

  const chain = chainQuery.data;
  const spot = chain?.meta.underlying ?? 0;
  const expiryDates = chain?.meta.expiry_dates ?? [];

  const greeksRows = useMemo<GreeksRow[]>(() => {
    if (!chain) return [];
    return buildGreeksRows(chain, symbol, expiry);
  }, [chain, symbol, expiry]);

  const gexData = useMemo(() => {
    if (!chain) return [];
    return getGex(chain, symbol, expiry);
  }, [chain, symbol, expiry]);

  const strikes = greeksRows.map((r) => r.strike);
  const atmStrike = findAtmStrike(strikes, spot);

  const avgIv = useMemo(() => {
    const atmRow = greeksRows.find((r) => r.strike === atmStrike);
    if (!atmRow) return 0.15;
    const ceIv = atmRow.CE_iv ? (atmRow.CE_iv > 1 ? atmRow.CE_iv / 100 : atmRow.CE_iv) : 0.15;
    const peIv = atmRow.PE_iv ? (atmRow.PE_iv > 1 ? atmRow.PE_iv / 100 : atmRow.PE_iv) : 0.15;
    return (ceIv + peIv) / 2;
  }, [greeksRows, atmStrike]);

  const isLoading = chainQuery.isLoading;
  const isError = chainQuery.isError;

  return (
    <div className="max-w-[1500px] mx-auto space-y-5">
      <PageHeader
        title="Greeks Dashboard"
        subtitle="Black-Scholes Greeks, GEX, IV Skew, Theta Decay & Delta-Neutral analysis."
        actions={
          <div className="flex flex-wrap items-center gap-2">
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

            {spot > 0 && (
              <div className="flex items-center gap-3 text-xs text-[var(--color-text-muted)]">
                <span>Spot: <span className="text-white font-semibold tnum">₹{spot.toLocaleString("en-IN")}</span></span>
                {atmStrike > 0 && (
                  <span>ATM: <span className="text-blue-400 font-semibold tnum">{atmStrike.toLocaleString("en-IN")}</span></span>
                )}
                {expiry && (
                  <span>DTE: <span className="text-white font-semibold tnum">{daysToExpiry(expiry)}</span></span>
                )}
              </div>
            )}

            {chainQuery.isFetching && !isLoading && (
              <span className="text-[10px] text-[var(--color-text-muted)] animate-pulse">refreshing…</span>
            )}
          </div>
        }
      />

      {/* Tab nav */}
      <div className="flex gap-1 border-b border-[var(--color-border)] overflow-x-auto">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={cn(
              "px-4 py-2 text-sm font-medium whitespace-nowrap transition-colors border-b-2 -mb-px",
              activeTab === tab.id
                ? "border-[var(--color-primary)] text-[var(--color-primary)]"
                : "border-transparent text-[var(--color-text-muted)] hover:text-white hover:border-[var(--color-border)]",
            )}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {isError ? (
        <Card>
          <CardContent className="py-10 text-center text-sm text-[var(--color-danger)]">
            Failed to load option chain: {String(chainQuery.error)}
          </CardContent>
        </Card>
      ) : isLoading ? (
        <Card>
          <CardContent className="space-y-2 py-6">
            {Array.from({ length: 8 }).map((_, i) => (
              <Skeleton key={i} className="h-7 w-full" />
            ))}
          </CardContent>
        </Card>
      ) : greeksRows.length === 0 ? (
        <DataUnavailable onRetry={() => chainQuery.refetch()} />
      ) : (
        <>
          {chain?.meta.synthetic && <SyntheticBanner vix={chain.meta.vix} />}
        <Card>
          {activeTab === "table" && (
            <>
              <CardHeader>
                <CardTitle>Greeks by Strike — {symbol} {expiry}</CardTitle>
              </CardHeader>
              <CardContent className="p-0">
                <GreeksTable rows={greeksRows} atmStrike={atmStrike} />
              </CardContent>
            </>
          )}

          {activeTab === "gex" && (
            <>
              <CardHeader>
                <CardTitle>Gamma Exposure (GEX) by Strike — {symbol} {expiry}</CardTitle>
              </CardHeader>
              <CardContent>
                {gexData.length === 0 ? (
                  <div className="py-12 text-center text-sm text-[var(--color-text-muted)]">No GEX data available.</div>
                ) : (
                  <GexChart data={gexData} spot={spot} atmStrike={atmStrike} />
                )}
                <p className="mt-2 text-[11px] text-[var(--color-text-muted)]">
                  Positive GEX (green) = dealers long gamma → price-dampening. Negative GEX (red) = dealers short gamma → price-amplifying. Gamma Flip = y=0 crossover.
                </p>
              </CardContent>
            </>
          )}

          {activeTab === "iv-skew" && (
            <>
              <CardHeader>
                <CardTitle>IV Skew — {symbol} {expiry}</CardTitle>
              </CardHeader>
              <CardContent>
                {greeksRows.length === 0 ? (
                  <div className="py-12 text-center text-sm text-[var(--color-text-muted)]">No IV data available.</div>
                ) : (
                  <IvSkewChart rows={greeksRows} atmStrike={atmStrike} />
                )}
                <p className="mt-2 text-[11px] text-[var(--color-text-muted)]">
                  Green = CE IV, Red = PE IV. A downward slope toward higher strikes (skew) indicates hedging demand for downside puts.
                </p>
              </CardContent>
            </>
          )}

          {activeTab === "theta-decay" && (
            <>
              <CardHeader>
                <CardTitle>ATM Straddle Theta Decay — {symbol} ATM {atmStrike.toLocaleString("en-IN")}</CardTitle>
              </CardHeader>
              <CardContent>
                {spot === 0 || atmStrike === 0 ? (
                  <div className="py-12 text-center text-sm text-[var(--color-text-muted)]">Load data to see theta decay.</div>
                ) : (
                  <ThetaDecayChart spot={spot} atmStrike={atmStrike} avgIv={avgIv} />
                )}
                <p className="mt-2 text-[11px] text-[var(--color-text-muted)]">
                  Shows how the theoretical ATM straddle premium (CE + PE) decays as DTE goes from 30 to 0.
                  Avg IV used: {(avgIv * 100).toFixed(1)}%. Note the acceleration in decay near expiry.
                </p>
              </CardContent>
            </>
          )}

          {activeTab === "delta-neutral" && (
            <>
              <CardHeader>
                <CardTitle>Delta Neutral Analysis — {symbol} {expiry}</CardTitle>
              </CardHeader>
              <CardContent className="p-0">
                <div className="p-4">
                  <DeltaNeutralTab
                    rows={greeksRows}
                    atmStrike={atmStrike}
                    symbol={symbol}
                    spot={spot}
                  />
                </div>
              </CardContent>
            </>
          )}
        </Card>
        </>
      )}
    </div>
  );
}
