"use client";

import { useState } from "react";
import { AlertTriangle, ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";
import type { ScanDiagnostics } from "@/lib/scanner-types";

/** Fraction of the universe that may fail to download before we warn. */
const NO_DATA_WARN_RATIO = 0.05;

/**
 * Warns when a meaningful slice of the universe never made it into the scan.
 *
 * Without this, "no setups" and "half the universe failed to download" look
 * identical to the user.
 */
export function ScanQualityBanner({
  summary,
  totalSymbols,
}: {
  summary: ScanDiagnostics | undefined;
  totalSymbols: number;
}) {
  const [open, setOpen] = useState(false);
  if (!summary || totalSymbols <= 0) return null;

  const noData      = summary.skipped_no_data ?? 0;
  const shortHist   = summary.skipped_insufficient_bars ?? 0;
  const errors      = summary.errors ?? [];
  const noDataRatio = noData / totalSymbols;

  // Short history is expected (recent listings on Monthly) — mention it, but
  // only a genuine download shortfall is worth a warning colour.
  const warn = noDataRatio > NO_DATA_WARN_RATIO;
  if (!warn && shortHist === 0) return null;

  const pct = Math.round(noDataRatio * 100);

  return (
    <div
      className={cn(
        "rounded-xl border p-3.5 text-[12px]",
        warn
          ? "bg-amber-500/10 border-amber-500/30 text-amber-200"
          : "bg-white/5 border-white/10 text-[var(--color-text-muted)]",
      )}
    >
      <div className="flex items-start gap-2.5">
        {warn && <AlertTriangle className="size-4 mt-0.5 shrink-0" />}
        <div className="flex-1 space-y-1">
          {warn && (
            <p className="font-semibold">
              {noData} of {totalSymbols} symbols ({pct}%) returned no data — these
              results cover only part of the universe.
            </p>
          )}
          <p className={cn(warn && "opacity-80")}>
            Scanned <span className="font-medium">{summary.scanned ?? totalSymbols}</span>
            {noData > 0 && <> · <span className="font-medium">{noData}</span> no data</>}
            {shortHist > 0 && (
              <> · <span className="font-medium">{shortHist}</span> too little history</>
            )}
            {typeof summary.cache_hit_rate === "number" && (
              <> · cache hits {Math.round(summary.cache_hit_rate * 100)}%</>
            )}
          </p>
        </div>
        {errors.length > 0 && (
          <button
            onClick={() => setOpen((v) => !v)}
            className="shrink-0 flex items-center gap-1 text-[11px] underline underline-offset-2 opacity-80 hover:opacity-100"
          >
            <ChevronDown className={cn("size-3 transition-transform", !open && "-rotate-90")} />
            {open ? "Hide" : "Show"} details
          </button>
        )}
      </div>

      {open && errors.length > 0 && (
        <div className="mt-2.5 rounded-lg bg-black/25 border border-white/10 p-2.5 font-mono text-[11px] space-y-0.5 max-h-52 overflow-y-auto">
          {errors.map((e) => (
            <div key={`${e.symbol}-${e.reason}`} className="flex gap-2">
              <span className="w-24 shrink-0 opacity-70">{e.symbol}</span>
              <span className="opacity-60">{e.reason}</span>
            </div>
          ))}
          {summary.errors_truncated ? (
            <div className="opacity-50 pt-1">
              …and {summary.errors_truncated} more (list capped at {errors.length})
            </div>
          ) : null}
        </div>
      )}
    </div>
  );
}
