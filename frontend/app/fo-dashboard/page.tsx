"use client";

import { memo } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  getVix,
  getIndexFutures,
  getPcr,
  getOiSpurts,
} from "@/lib/fno-api";
import type { VixData, IndexFuture, PcrData, OISpurtRow } from "@/lib/fno-types";
import { daysToExpiry } from "@/lib/fno-types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { cn, formatNum, formatPct, trendClass } from "@/lib/utils";

// ── Pure helpers (module-level, no re-creation per render) ────────────────────

function vixColour(vix: number | null): string {
  if (vix === null) return "text-white";
  if (vix > 20) return "down";
  if (vix < 15) return "up";
  return "text-yellow-400";
}

function pcrSentiment(pcr: number): { label: string; variant: "success" | "danger" | "default" } {
  if (pcr > 1.2) return { label: "Bullish", variant: "success" };
  if (pcr < 0.8) return { label: "Bearish", variant: "danger" };
  return { label: "Neutral", variant: "default" };
}

// ── VIX Card ──────────────────────────────────────────────────────────────────

const VixCard = memo(function VixCard({ data, loading }: { data?: VixData; loading: boolean }) {
  return (
    <Card>
      <CardContent className="p-5">
        {loading ? (
          <div className="space-y-2">
            <Skeleton className="h-4 w-24" />
            <Skeleton className="h-12 w-32" />
            <Skeleton className="h-3 w-40" />
          </div>
        ) : (
          <>
            <div className="text-[11px] uppercase tracking-wider text-[var(--color-text-muted)]">
              India VIX · Fear Gauge
            </div>
            <div className={cn("mt-1 text-5xl font-bold tnum", vixColour(data?.vix ?? null))}>
              {data?.vix != null ? data.vix.toFixed(2) : "—"}
            </div>
            <div className="mt-2 flex items-center gap-3 text-xs tnum">
              <span className={cn("font-medium", data?.change_pct != null && data.change_pct > 0 ? "down" : "up")}>
                {data?.change_pct != null
                  ? `${data.change_pct > 0 ? "▲" : "▼"} ${Math.abs(data.change_pct).toFixed(2)}%`
                  : "—"}
              </span>
              <span className="text-[var(--color-text-muted)]">
                H: {data?.high?.toFixed(2) ?? "—"} · L: {data?.low?.toFixed(2) ?? "—"} · Prev: {data?.prev_close?.toFixed(2) ?? "—"}
              </span>
            </div>
            <div className="mt-3 text-[11px] text-[var(--color-text-muted)]">
              {data?.vix != null && data.vix > 20
                ? "Elevated fear — wide option premiums"
                : data?.vix != null && data.vix < 15
                ? "Low fear — complacency zone, risk of snap-back"
                : "Moderate volatility environment"}
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
});

// ── Index Futures Card ────────────────────────────────────────────────────────

const IndexFutureCard = memo(function IndexFutureCard({ fut }: { fut: IndexFuture }) {
  const dte = fut.expiry ? daysToExpiry(fut.expiry) : null;
  return (
    <Card>
      <CardContent className="p-4 space-y-2">
        <div className="flex items-center justify-between">
          <span className="text-sm font-semibold text-white">{fut.symbol}</span>
          {fut.synthetic
            ? <Badge variant="default" className="text-blue-300 border-blue-600/40 bg-blue-600/10">⚗ est.</Badge>
            : dte != null && <Badge variant="default">{dte}d exp</Badge>
          }
        </div>

        <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs tnum">
          <div>
            <div className="text-[var(--color-text-muted)]">Spot</div>
            <div className="text-white font-medium">{fut.spot.toLocaleString("en-IN")}</div>
          </div>
          <div>
            <div className="text-[var(--color-text-muted)]">{fut.synthetic ? "Est. Futures" : "Fut LTP"}</div>
            <div className="text-white font-medium">{fut.futures_ltp.toLocaleString("en-IN")}</div>
          </div>
          <div>
            <div className="text-[var(--color-text-muted)]">Basis</div>
            <div className={cn("font-medium", fut.basis >= 0 ? "up" : "down")}>
              {fut.basis >= 0 ? "+" : ""}{fut.basis.toFixed(2)}{" "}
              <span className="text-[10px]">({fut.basis_pct >= 0 ? "+" : ""}{fut.basis_pct.toFixed(2)}%)</span>
            </div>
          </div>
          <div>
            <div className="text-[var(--color-text-muted)]">Chg %</div>
            <div className={cn("font-medium", trendClass(fut.change_pct))}>
              {formatPct(fut.change_pct, { sign: true })}
            </div>
          </div>
          {!fut.synthetic && (
            <div>
              <div className="text-[var(--color-text-muted)]">OI (lots)</div>
              <div className="text-white">{formatNum(fut.oi, { compact: true })}</div>
            </div>
          )}
        </div>

        {!fut.synthetic && fut.expiry && (
          <div className="text-[10px] text-[var(--color-text-muted)]">Expiry: {fut.expiry}</div>
        )}
      </CardContent>
    </Card>
  );
});

function IndexFuturesSkeleton() {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
      {[0, 1, 2].map((i) => (
        <Card key={i}>
          <CardContent className="p-4 space-y-3">
            <Skeleton className="h-4 w-24" />
            <Skeleton className="h-3 w-full" />
            <Skeleton className="h-3 w-3/4" />
            <Skeleton className="h-3 w-1/2" />
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

// ── PCR Cards ─────────────────────────────────────────────────────────────────

const PcrCard = memo(function PcrCard({ symbol, data, loading }: { symbol: string; data?: PcrData; loading: boolean }) {
  const sentiment = data ? pcrSentiment(data.pcr_oi) : null;
  return (
    <Card>
      <CardContent className="p-4">
        {loading || !data ? (
          <div className="space-y-2">
            <Skeleton className="h-3 w-20" />
            <Skeleton className="h-8 w-16" />
            <Skeleton className="h-3 w-28" />
          </div>
        ) : (
          <>
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-semibold text-white">{symbol}</span>
              {sentiment && <Badge variant={sentiment.variant}>{sentiment.label}</Badge>}
            </div>
            <div className="text-3xl font-bold tnum text-white">{data.pcr_oi.toFixed(3)}</div>
            <div className="text-[11px] text-[var(--color-text-muted)] mt-1">PCR OI</div>
            <div className="mt-2 grid grid-cols-2 gap-x-3 text-[11px] tnum text-[var(--color-text-muted)]">
              <div>CE OI: {formatNum(data.total_ce_oi, { compact: true })}</div>
              <div>PE OI: {formatNum(data.total_pe_oi, { compact: true })}</div>
              <div>PCR Vol: {data.pcr_vol.toFixed(3)}</div>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
});

// ── OI Spurts Table ───────────────────────────────────────────────────────────

const OiSpurtsTable = memo(function OiSpurtsTable({ rows, loading }: { rows?: OISpurtRow[]; loading: boolean }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>OI Spurts · Top 10</CardTitle>
      </CardHeader>
      <CardContent className="p-0 overflow-x-auto">
        {loading ? (
          <div className="p-4 space-y-2">
            {Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-8 w-full" />)}
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead className="border-b border-[var(--color-border)] bg-[var(--color-surface-2)]">
              <tr className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)]">
                <th className="text-left px-4 py-2.5">Symbol</th>
                <th className="text-right px-4 py-2.5">OI Current</th>
                <th className="text-right px-4 py-2.5">OI Chg%</th>
                <th className="text-right px-4 py-2.5">LTP (₹)</th>
                <th className="text-right px-4 py-2.5">Price Chg%</th>
              </tr>
            </thead>
            <tbody>
              {(rows ?? []).slice(0, 10).map((row, i) => (
                <tr
                  key={`${row.symbol}-${i}`}
                  className="border-b border-[var(--color-border)] hover:bg-[var(--color-surface-2)]/60 transition-colors"
                >
                  <td className="px-4 py-2.5 font-medium text-white">{row.symbol}</td>
                  <td className="px-4 py-2.5 text-right tnum text-[var(--color-text-muted)]">
                    {row.oi_current.toLocaleString("en-IN")}
                  </td>
                  <td className={cn("px-4 py-2.5 text-right tnum font-medium", trendClass(row.oi_change_pct))}>
                    {formatPct(row.oi_change_pct, { sign: true })}
                  </td>
                  <td className="px-4 py-2.5 text-right tnum text-white">₹{row.ltp.toLocaleString("en-IN")}</td>
                  <td className={cn("px-4 py-2.5 text-right tnum font-medium", trendClass(row.price_chg_pct))}>
                    {formatPct(row.price_chg_pct, { sign: true })}
                  </td>
                </tr>
              ))}
              {(rows ?? []).length === 0 && (
                <tr>
                  <td colSpan={5} className="px-4 py-8 text-center text-sm text-[var(--color-text-muted)]">
                    No OI spurt data available
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        )}
      </CardContent>
    </Card>
  );
});

// ── Page ──────────────────────────────────────────────────────────────────────

export default function FoDashboardPage() {
  const vix = useQuery<VixData>({
    queryKey: ["fno", "vix"],
    queryFn: getVix,
    refetchInterval: 60_000,
    staleTime: 30_000,
  });

  const indexFutures = useQuery<IndexFuture[]>({
    queryKey: ["fno", "index-futures"],
    queryFn: getIndexFutures,
    refetchInterval: 30_000,
    staleTime: 20_000,
  });

  const pcrNifty = useQuery<PcrData>({
    queryKey: ["fno", "pcr", "NIFTY"],
    queryFn: () => getPcr("NIFTY"),
    refetchInterval: 60_000,
    staleTime: 30_000,
  });

  const pcrBankNifty = useQuery<PcrData>({
    queryKey: ["fno", "pcr", "BANKNIFTY"],
    queryFn: () => getPcr("BANKNIFTY"),
    refetchInterval: 60_000,
    staleTime: 30_000,
  });

  const pcrFinNifty = useQuery<PcrData>({
    queryKey: ["fno", "pcr", "FINNIFTY"],
    queryFn: () => getPcr("FINNIFTY"),
    refetchInterval: 60_000,
    staleTime: 30_000,
  });

  const oiSpurts = useQuery<OISpurtRow[]>({
    queryKey: ["fno", "oi-spurts"],
    queryFn: getOiSpurts,
    refetchInterval: 60_000,
    staleTime: 30_000,
  });

  return (
    <div className="space-y-6 max-w-[1400px] mx-auto">
      <header>
        <h1 className="text-xl font-semibold text-white">F&amp;O Dashboard</h1>
        <p className="text-xs text-[var(--color-text-muted)] mt-0.5">
          Futures &amp; Options market overview · auto-refresh 30–60s
        </p>
      </header>

      {/* VIX */}
      <section>
        <h2 className="text-[11px] uppercase tracking-wider text-[var(--color-text-muted)] mb-2">Volatility</h2>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <VixCard data={vix.data} loading={vix.isLoading} />
          {vix.data && (
            <>
              <Card>
                <CardContent className="p-5 flex flex-col justify-center h-full">
                  <div className="text-[11px] uppercase tracking-wider text-[var(--color-text-muted)] mb-3">VIX Zone Reference</div>
                  <div className="space-y-2 text-xs">
                    <div className="flex items-center gap-2">
                      <span className="size-2 rounded-full bg-[var(--color-success)]" />
                      <span className="text-[var(--color-text-muted)]">Below 15 — Low fear (complacency)</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="size-2 rounded-full bg-yellow-400" />
                      <span className="text-[var(--color-text-muted)]">15–20 — Normal range</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="size-2 rounded-full bg-[var(--color-danger)]" />
                      <span className="text-[var(--color-text-muted)]">Above 20 — Elevated fear</span>
                    </div>
                  </div>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="p-5">
                  <div className="text-[11px] uppercase tracking-wider text-[var(--color-text-muted)] mb-3">VIX Today</div>
                  <div className="grid grid-cols-2 gap-3 text-xs tnum">
                    <div>
                      <div className="text-[var(--color-text-muted)]">Open</div>
                      <div className="text-white font-medium">{vix.data.open?.toFixed(2) ?? "—"}</div>
                    </div>
                    <div>
                      <div className="text-[var(--color-text-muted)]">High</div>
                      <div className="down font-medium">{vix.data.high?.toFixed(2) ?? "—"}</div>
                    </div>
                    <div>
                      <div className="text-[var(--color-text-muted)]">Low</div>
                      <div className="up font-medium">{vix.data.low?.toFixed(2) ?? "—"}</div>
                    </div>
                    <div>
                      <div className="text-[var(--color-text-muted)]">Prev Close</div>
                      <div className="text-white font-medium">{vix.data.prev_close?.toFixed(2) ?? "—"}</div>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </>
          )}
        </div>
      </section>

      {/* Index Futures */}
      <section>
        <h2 className="text-[11px] uppercase tracking-wider text-[var(--color-text-muted)] mb-2">Index Futures</h2>
        {indexFutures.isLoading ? (
          <IndexFuturesSkeleton />
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            {(indexFutures.data ?? []).map((fut) => (
              <IndexFutureCard key={fut.symbol} fut={fut} />
            ))}
            {(indexFutures.data ?? []).length === 0 && (
              <div className="col-span-3 py-8 text-center text-sm text-[var(--color-text-muted)]">
                Index futures data unavailable
              </div>
            )}
          </div>
        )}
      </section>

      {/* PCR */}
      <section>
        <h2 className="text-[11px] uppercase tracking-wider text-[var(--color-text-muted)] mb-2">Put-Call Ratio (PCR OI)</h2>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <PcrCard symbol="NIFTY" data={pcrNifty.data} loading={pcrNifty.isLoading} />
          <PcrCard symbol="BANKNIFTY" data={pcrBankNifty.data} loading={pcrBankNifty.isLoading} />
          <PcrCard symbol="FINNIFTY" data={pcrFinNifty.data} loading={pcrFinNifty.isLoading} />
        </div>
      </section>

      {/* OI Spurts */}
      <section>
        <OiSpurtsTable rows={oiSpurts.data} loading={oiSpurts.isLoading} />
      </section>
    </div>
  );
}
