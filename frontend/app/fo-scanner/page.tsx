"use client";

import { useState } from "react";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Lock } from "lucide-react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";

// ── Types ─────────────────────────────────────────────────────────────────────

interface ScanResult {
  symbol: string;
  signal_type: string;
  metric: string;
  direction: "Bullish" | "Bearish" | "Neutral";
  strength: number;
  expiry: string;
  dte: number;
}

// ── Constants ─────────────────────────────────────────────────────────────────

const ACTIVE_SCAN_TYPES = [
  "High OI Buildup",
  "OI Unwinding",
  "Unusual Volume",
] as const;

const DISABLED_SCAN_TYPES = [
  "IV Crush Candidates",
  "PCR Extremes",
  "Max Pain Divergence",
  "Gamma Squeeze",
  "Roll Activity",
] as const;

type ActiveScanType = (typeof ACTIVE_SCAN_TYPES)[number];

// ── Helpers ───────────────────────────────────────────────────────────────────

function directionVariant(direction: string): "success" | "danger" | "default" {
  if (direction === "Bullish") return "success";
  if (direction === "Bearish") return "danger";
  return "default";
}

function directionColor(direction: string): string {
  if (direction === "Bullish") return "var(--color-success)";
  if (direction === "Bearish") return "var(--color-danger)";
  return "var(--color-text-muted)";
}

function exportCsv(rows: ScanResult[], scanType: string) {
  const header = "Rank,Symbol,Signal Type,Metric,Direction,Strength,Expiry,DTE\n";
  const body = rows
    .map(
      (r, i) =>
        `${i + 1},"${r.symbol}","${r.signal_type}","${r.metric}","${r.direction}",${r.strength},"${r.expiry}",${r.dte}`,
    )
    .join("\n");
  const blob = new Blob([header + body], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `fo-scan-${scanType.replace(/\s+/g, "-").toLowerCase()}-${Date.now()}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

// ── Sub-components ────────────────────────────────────────────────────────────

function Spinner() {
  return (
    <svg
      className="animate-spin h-4 w-4 text-[var(--color-primary)]"
      xmlns="http://www.w3.org/2000/svg"
      fill="none"
      viewBox="0 0 24 24"
    >
      <circle
        className="opacity-25"
        cx="12"
        cy="12"
        r="10"
        stroke="currentColor"
        strokeWidth="4"
      />
      <path
        className="opacity-75"
        fill="currentColor"
        d="M4 12a8 8 0 018-8v8H4z"
      />
    </svg>
  );
}

function StrengthBar({ value }: { value: number }) {
  const color =
    value >= 70
      ? "var(--color-danger)"
      : value >= 40
      ? "#f5c542"
      : "var(--color-success)";
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1.5 rounded-full bg-[var(--color-surface-2)] overflow-hidden">
        <div
          className="h-full rounded-full transition-all"
          style={{ width: `${value}%`, background: color }}
        />
      </div>
      <span className="text-[10px] tabular-nums text-[var(--color-text-muted)] w-6 text-right">
        {value}
      </span>
    </div>
  );
}

interface BarTooltipPayload {
  value: number;
  payload: ScanResult;
}

function BarTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: BarTooltipPayload[];
}) {
  if (!active || !payload?.length) return null;
  const row = payload[0].payload;
  return (
    <div className="rounded border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-xs shadow-lg">
      <div className="font-semibold text-white">{row.symbol}</div>
      <div className="text-[var(--color-text-muted)]">{row.signal_type}</div>
      <div className="text-[var(--color-text-muted)]">{row.metric}</div>
      <div className="font-medium mt-0.5" style={{ color: directionColor(row.direction) }}>
        {row.direction} · Strength {row.strength}
      </div>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function FoScannerPage() {
  const [scanType, setScanType] = useState<ActiveScanType>("High OI Buildup");
  const [results, setResults] = useState<ScanResult[]>([]);
  const [isScanning, setIsScanning] = useState(false);
  const [hasScanned, setHasScanned] = useState(false);
  const [errorMsg, setErrorMsg] = useState("");

  async function handleRunScan() {
    setErrorMsg("");
    setIsScanning(true);
    setResults([]);
    setHasScanned(false);
    try {
      const res = await fetch(
        `/api/fno/scan?scan_type=${encodeURIComponent(scanType)}`,
      );
      if (!res.ok) {
        const text = await res.text().catch(() => "");
        throw new Error(`Server error ${res.status}${text ? `: ${text.slice(0, 200)}` : ""}`);
      }
      const data: ScanResult[] = await res.json();
      setResults(Array.isArray(data) ? data : []);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      setErrorMsg(`Scan failed: ${message}`);
    } finally {
      setIsScanning(false);
      setHasScanned(true);
    }
  }

  const topResults = results.slice(0, 15);

  return (
    <div className="space-y-6 max-w-[1400px] mx-auto">
      {/* Header */}
      <header>
        <h1 className="text-xl font-semibold text-white">F&amp;O Scanner</h1>
        <p className="text-xs text-[var(--color-text-muted)] mt-0.5">
          Scan 216+ F&amp;O instruments for OI-based signals across the market.
        </p>
      </header>

      {/* Scan Parameters */}
      <Card>
        <CardHeader>
          <CardTitle>Scan Parameters</CardTitle>
        </CardHeader>
        <CardContent className="p-4 space-y-5">
          {/* Scan type chips */}
          <div className="flex flex-col gap-2">
            <label className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)]">
              Scan Type
            </label>
            <div className="flex flex-wrap gap-2">
              {/* Active scan types */}
              {ACTIVE_SCAN_TYPES.map((type) => (
                <button
                  key={type}
                  onClick={() => setScanType(type)}
                  disabled={isScanning}
                  className={cn(
                    "rounded-full px-3.5 py-1.5 text-xs font-medium transition-colors border",
                    scanType === type
                      ? "bg-[var(--color-primary)] border-[var(--color-primary)] text-white"
                      : "bg-[var(--color-surface-2)] border-[var(--color-border)] text-[var(--color-text)] hover:border-[var(--color-primary)] hover:text-white",
                    isScanning && "opacity-50 cursor-not-allowed",
                  )}
                >
                  {type}
                </button>
              ))}

              {/* Disabled scan types — option chain dependent */}
              {DISABLED_SCAN_TYPES.map((type) => (
                <div key={type} className="relative group">
                  <button
                    disabled
                    className="flex items-center gap-1.5 rounded-full px-3.5 py-1.5 text-xs font-medium border bg-[var(--color-surface-2)] border-[var(--color-border)] text-[var(--color-text-muted)] opacity-50 cursor-not-allowed"
                  >
                    <Lock className="size-3 shrink-0" />
                    {type}
                  </button>
                  <div className="pointer-events-none absolute bottom-full left-1/2 -translate-x-1/2 mb-1.5 z-10 opacity-0 group-hover:opacity-100 transition-opacity">
                    <div className="rounded bg-[var(--color-surface)] border border-[var(--color-border)] px-2 py-1 text-[10px] text-[var(--color-text-muted)] whitespace-nowrap shadow-lg">
                      Requires option chain access
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Run button */}
          <div className="flex items-center gap-3 pt-1">
            <button
              onClick={handleRunScan}
              disabled={isScanning}
              className="flex items-center gap-2 rounded bg-[var(--color-primary)] px-5 py-2 text-sm font-medium text-white transition hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isScanning && <Spinner />}
              {isScanning ? "Scanning…" : "Run Scan"}
            </button>
            {isScanning && (
              <span className="text-xs text-[var(--color-text-muted)] animate-pulse">
                Scanning 216+ F&amp;O instruments…
              </span>
            )}
          </div>

          {/* Error */}
          {errorMsg && (
            <div className="text-xs text-[var(--color-danger)] bg-[color-mix(in_oklab,var(--color-danger)_10%,transparent)] border border-[color-mix(in_oklab,var(--color-danger)_25%,transparent)] rounded px-3 py-2">
              {errorMsg}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Results — summary badge */}
      {results.length > 0 && (
        <div className="flex items-center gap-3">
          <Badge variant="info">
            {results.length} signal{results.length !== 1 ? "s" : ""} found
          </Badge>
          <span className="text-xs text-[var(--color-text-muted)]">{scanType}</span>
          <button
            onClick={() => exportCsv(results, scanType)}
            className="ml-auto rounded border border-[var(--color-border)] px-3 py-1 text-xs font-medium text-white hover:bg-[var(--color-surface-2)] transition-colors"
          >
            Export CSV
          </button>
        </div>
      )}

      {/* Results — bar chart */}
      {results.length > 0 && (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle>Top Signals by Strength</CardTitle>
              <span className="text-[10px] text-[var(--color-text-muted)]">
                Top {topResults.length} of {results.length}
              </span>
            </div>
          </CardHeader>
          <CardContent className="p-4">
            <ResponsiveContainer
              width="100%"
              height={Math.max(200, topResults.length * 30)}
            >
              <BarChart
                data={topResults}
                layout="vertical"
                margin={{ top: 4, right: 24, bottom: 4, left: 90 }}
                barCategoryGap="30%"
              >
                <XAxis
                  type="number"
                  domain={[0, 100]}
                  tickFormatter={(v: number) => `${v}`}
                  tick={{ fontSize: 10, fill: "var(--color-text-muted)" }}
                  tickLine={false}
                  axisLine={false}
                />
                <YAxis
                  type="category"
                  dataKey="symbol"
                  width={86}
                  tick={{ fontSize: 11, fill: "var(--color-text)", fontWeight: 600 }}
                  tickLine={false}
                  axisLine={false}
                />
                <Tooltip
                  content={<BarTooltip />}
                  cursor={{ fill: "var(--color-surface-2)", opacity: 0.5 }}
                />
                <Bar dataKey="strength" radius={[0, 3, 3, 0]}>
                  {topResults.map((row, i) => (
                    <Cell
                      key={i}
                      fill={directionColor(row.direction)}
                      fillOpacity={0.85}
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      )}

      {/* Results — table */}
      {results.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Scan Results · {scanType}</CardTitle>
          </CardHeader>
          <CardContent className="p-0 overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="border-b border-[var(--color-border)] bg-[var(--color-surface-2)]">
                <tr className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)]">
                  <th className="text-right px-4 py-2.5 w-10">#</th>
                  <th className="text-left px-4 py-2.5">Symbol</th>
                  <th className="text-left px-4 py-2.5">Metric</th>
                  <th className="text-left px-4 py-2.5">Direction</th>
                  <th className="text-left px-4 py-2.5 min-w-[140px]">Strength</th>
                  <th className="text-left px-4 py-2.5">Expiry</th>
                  <th className="text-right px-4 py-2.5">DTE</th>
                </tr>
              </thead>
              <tbody>
                {results.map((row, i) => (
                  <tr
                    key={`${row.symbol}-${row.signal_type}-${i}`}
                    className="border-b border-[var(--color-border)] hover:bg-[var(--color-surface-2)]/60 transition-colors"
                  >
                    <td className="px-4 py-2.5 text-right tabular-nums text-xs text-[var(--color-text-muted)]">
                      {i + 1}
                    </td>
                    <td className="px-4 py-2.5 font-semibold text-white">
                      {row.symbol}
                    </td>
                    <td className="px-4 py-2.5 text-xs tabular-nums text-[var(--color-text)]">
                      {row.metric}
                    </td>
                    <td className="px-4 py-2.5">
                      <Badge variant={directionVariant(row.direction)}>
                        {row.direction}
                      </Badge>
                    </td>
                    <td className="px-4 py-2.5">
                      <StrengthBar value={row.strength} />
                    </td>
                    <td className="px-4 py-2.5 text-xs text-[var(--color-text-muted)]">
                      {row.expiry || "—"}
                    </td>
                    <td className="px-4 py-2.5 text-right tabular-nums text-xs text-[var(--color-text-muted)]">
                      {row.dte > 0 ? `${row.dte}d` : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>
      )}

      {/* Empty state — after scan completes with 0 results */}
      {hasScanned && !isScanning && results.length === 0 && !errorMsg && (
        <div className="py-16 text-center text-sm text-[var(--color-text-muted)]">
          No signals found for this scan type.
        </div>
      )}

      {/* Initial prompt — before first scan */}
      {!hasScanned && !isScanning && !errorMsg && (
        <div className="py-14 text-center text-sm text-[var(--color-text-muted)]">
          Select a scan type above, then click{" "}
          <span className="text-white font-medium">Run Scan</span> to find signals.
        </div>
      )}

      {/* Info banner */}
      <div className="rounded-md border border-[var(--color-border)] bg-[var(--color-surface-2)] px-4 py-3 text-xs text-[var(--color-text-muted)]">
        Option-chain dependent scans (IV Crush, PCR Extremes, Max Pain Divergence, Gamma Squeeze, Roll Activity) require NSE option chain API access which is currently rate-limited.
        Active scans use OI spurts data from 216+ F&amp;O-eligible instruments.
      </div>
    </div>
  );
}
