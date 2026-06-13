"use client";

import { useState, useEffect, useCallback, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
  ResponsiveContainer,
} from "recharts";
import { cn } from "@/lib/utils";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  INDEX_SYMBOLS,
  getLotSize,
  daysToExpiry,
  findAtmStrike,
} from "@/lib/fno-types";
import type { StrategyLeg, SavedStrategy, OptionChainResponse } from "@/lib/fno-types";
import {
  getOptionChain,
  getSavedStrategies,
  saveStrategy,
  deleteStrategy,
  getFnoSymbols,
} from "@/lib/fno-api";
import {
  calculatePayoff,
  calculateBreakevens,
  calculateMaxProfitLoss,
  calculatePositionGreeks,
  estimateMargin,
  STRATEGY_TEMPLATES,
  templateToLegs,
} from "@/lib/strategy";

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmt(n: number): string {
  return n.toLocaleString("en-IN");
}

function fmtRs(n: number): string {
  return `₹${Math.abs(n).toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
}

// ── Sub-components ────────────────────────────────────────────────────────────

function MetricCard({
  label,
  value,
  variant,
  sub,
}: {
  label: string;
  value: string;
  variant?: "success" | "danger" | "default";
  sub?: string;
}) {
  return (
    <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] p-4">
      <div className="text-[11px] uppercase tracking-wider text-[var(--color-text-muted)] mb-1">
        {label}
      </div>
      <div
        className={cn(
          "text-xl font-bold tnum",
          variant === "success" && "text-[var(--color-success)]",
          variant === "danger" && "text-[var(--color-danger)]",
          variant === "default" && "text-white",
          !variant && "text-white",
        )}
      >
        {value}
      </div>
      {sub && (
        <div className="text-[10px] text-[var(--color-text-muted)] mt-0.5">{sub}</div>
      )}
    </div>
  );
}

interface TooltipPayloadEntry {
  value: number;
}

function PayoffTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: TooltipPayloadEntry[];
  label?: number;
}) {
  if (!active || !payload?.length) return null;
  const pnl = payload[0].value;
  return (
    <div className="rounded border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-xs shadow-lg">
      <div className="text-[var(--color-text-muted)]">Spot: ₹{fmt(label ?? 0)}</div>
      <div className={cn("font-semibold tnum", pnl >= 0 ? "text-[var(--color-success)]" : "text-[var(--color-danger)]")}>
        P&L: {pnl >= 0 ? "+" : ""}₹{fmt(Math.round(pnl))}
      </div>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function StrategyBuilderPage() {
  const [symbol, setSymbol] = useState("NIFTY");
  const [selectedExpiry, setSelectedExpiry] = useState("");
  const [legs, setLegs] = useState<StrategyLeg[]>([]);
  const [strategyName, setStrategyName] = useState("");
  const [selectedTemplate, setSelectedTemplate] = useState("");
  const [savedStrategies, setSavedStrategies] = useState<SavedStrategy[]>([]);
  const [saveMsg, setSaveMsg] = useState("");

  // P1-6: Load equity F&O symbols so all F&O stocks are selectable (not just indices)
  const symbolsQuery = useQuery<string[]>({
    queryKey: ["fno", "symbols"],
    queryFn: getFnoSymbols,
    staleTime: 10 * 60_000,
  });
  const allSymbols = useMemo(() => {
    const extra = (symbolsQuery.data ?? []).filter((s) => !INDEX_SYMBOLS.includes(s)).sort();
    return [...INDEX_SYMBOLS, ...extra];
  }, [symbolsQuery.data]);

  const chainQuery = useQuery<OptionChainResponse>({
    queryKey: ["fno", "option-chain", symbol],
    queryFn: () => getOptionChain(symbol),
    refetchInterval: 60_000,
    staleTime: 30_000,
  });

  const chain = chainQuery.data;
  const meta = chain?.meta;
  const spot = meta?.underlying ?? 0;
  const strikes = meta?.strike_prices ?? [];
  const expiries = meta?.expiry_dates ?? [];
  const atmStrike = strikes.length && spot ? findAtmStrike(strikes, spot) : 0;
  const dte = selectedExpiry ? daysToExpiry(selectedExpiry) : 0;

  // Set default expiry when chain loads
  useEffect(() => {
    if (expiries.length && !selectedExpiry) {
      setSelectedExpiry(expiries[0]);
    }
  }, [expiries, selectedExpiry]);

  // Load saved strategies from server on mount
  useEffect(() => {
    getSavedStrategies().then(setSavedStrategies).catch(() => {});
  }, []);

  // Helpers for LTP/IV lookup from chain
  const getLtp = useCallback(
    (strike: number, type: "CE" | "PE" | "FUT"): number => {
      if (!chain) return 0;
      const row = chain.rows.find(
        (r) => r.strike === strike && r.expiry === selectedExpiry,
      );
      if (!row) return 0;
      if (type === "CE") return row.CE.ltp ?? 0;
      if (type === "PE") return row.PE.ltp ?? 0;
      return spot;
    },
    [chain, selectedExpiry, spot],
  );

  const getIv = useCallback(
    (strike: number, type: "CE" | "PE" | "FUT"): number => {
      if (!chain) return 0;
      const row = chain.rows.find(
        (r) => r.strike === strike && r.expiry === selectedExpiry,
      );
      if (!row) return 0;
      if (type === "CE") return row.CE.iv ?? 0;
      if (type === "PE") return row.PE.iv ?? 0;
      return 0;
    },
    [chain, selectedExpiry],
  );

  // ── Template loader ────────────────────────────────────────────────────────

  function handleLoadTemplate() {
    if (!selectedTemplate || !strikes.length || !atmStrike || !spot) return;
    const lotSize = getLotSize(symbol);
    const newLegs = templateToLegs(
      selectedTemplate,
      symbol,
      selectedExpiry,
      dte,
      lotSize,
      strikes,
      atmStrike,
      getLtp,
      getIv,
      spot,
    );
    setLegs(newLegs);
  }

  // ── Leg management ─────────────────────────────────────────────────────────

  function addLeg() {
    if (legs.length >= 6) return;
    const lotSize = getLotSize(symbol);
    const strike = atmStrike || (strikes[0] ?? 0);
    setLegs((prev) => [
      ...prev,
      {
        symbol,
        expiry: selectedExpiry,
        strike,
        option_type: "CE",
        action: "BUY",
        lots: 1,
        lot_size: lotSize,
        ltp: getLtp(strike, "CE"),
        iv: getIv(strike, "CE") / 100,
        dte,
      },
    ]);
  }

  function removeLeg(idx: number) {
    setLegs((prev) => prev.filter((_, i) => i !== idx));
  }

  function updateLeg(idx: number, patch: Partial<StrategyLeg>) {
    setLegs((prev) =>
      prev.map((leg, i) => {
        if (i !== idx) return leg;
        const updated = { ...leg, ...patch };
        // Auto-fill LTP when strike or type changes
        if (patch.strike !== undefined || patch.option_type !== undefined) {
          const s = patch.strike ?? leg.strike;
          const t = patch.option_type ?? leg.option_type;
          const ltp = t === "FUT" ? spot : getLtp(s, t as "CE" | "PE");
          const iv = t === "FUT" ? 0 : getIv(s, t as "CE" | "PE") / 100;
          updated.ltp = ltp;
          updated.iv = iv;
        }
        if (patch.expiry !== undefined) {
          updated.dte = daysToExpiry(patch.expiry);
        }
        return updated;
      }),
    );
  }

  // ── Strategy results ───────────────────────────────────────────────────────

  const hasLegs = legs.length > 0 && spot > 0;
  const results = hasLegs
    ? (() => {
        const pml = calculateMaxProfitLoss(legs, spot);
        const bks = calculateBreakevens(legs, spot);
        const greeks = calculatePositionGreeks(legs, spot);
        const margin = estimateMargin(legs, spot);
        const { prices, pnl } = calculatePayoff(legs, spot, 0.12, 200);
        return { pml, bks, greeks, margin, prices, pnl };
      })()
    : null;

  const payoffData = results
    ? results.prices.map((p, i) => ({ price: p, pnl: results.pnl[i] }))
    : [];

  // ── Save strategy ──────────────────────────────────────────────────────────

  async function handleSave() {
    if (!strategyName.trim() || !legs.length) return;
    await saveStrategy(strategyName.trim(), legs).catch(() => {});
    getSavedStrategies().then(setSavedStrategies).catch(() => {});
    setSaveMsg("Saved!");
    setTimeout(() => setSaveMsg(""), 2000);
  }

  function handleLoadSaved(s: SavedStrategy) {
    setLegs(s.legs);
  }

  async function handleDeleteSaved(name: string) {
    await deleteStrategy(name).catch(() => {});
    getSavedStrategies().then(setSavedStrategies).catch(() => {});
  }

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <div className="space-y-6 max-w-[1400px] mx-auto">
      {/* Header */}
      <header>
        <h1 className="text-xl font-semibold text-white">Strategy Builder</h1>
        <p className="text-xs text-[var(--color-text-muted)] mt-0.5">
          Build, visualise and save multi-leg F&amp;O strategies
        </p>
      </header>

      {/* Top bar */}
      <Card>
        <CardContent className="p-4">
          <div className="flex flex-wrap items-center gap-4">
            {/* Symbol */}
            <div className="flex flex-col gap-1">
              <label className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)]">
                Symbol
              </label>
              <select
                value={symbol}
                onChange={(e) => {
                  setSymbol(e.target.value);
                  setSelectedExpiry("");
                  setLegs([]);
                }}
                className="rounded border border-[var(--color-border)] bg-[var(--color-surface-2)] px-3 py-1.5 text-sm text-white focus:outline-none focus:ring-1 focus:ring-[var(--color-primary)]"
              >
                <optgroup label="Indices">
                  {INDEX_SYMBOLS.map((s) => <option key={s} value={s}>{s}</option>)}
                </optgroup>
                {(symbolsQuery.data ?? []).length > 0 && (
                  <optgroup label="Equity F&amp;O">
                    {(symbolsQuery.data ?? [])
                      .filter((s) => !INDEX_SYMBOLS.includes(s))
                      .sort()
                      .map((s) => <option key={s} value={s}>{s}</option>)
                    }
                  </optgroup>
                )}
              </select>
            </div>

            {/* Expiry */}
            <div className="flex flex-col gap-1">
              <label className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)]">
                Expiry
              </label>
              <select
                value={selectedExpiry}
                onChange={(e) => setSelectedExpiry(e.target.value)}
                className="rounded border border-[var(--color-border)] bg-[var(--color-surface-2)] px-3 py-1.5 text-sm text-white focus:outline-none focus:ring-1 focus:ring-[var(--color-primary)]"
              >
                {expiries.map((e) => (
                  <option key={e} value={e}>
                    {e}
                  </option>
                ))}
              </select>
            </div>

            {/* Spot */}
            <div className="flex flex-col gap-1">
              <div className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)]">
                Spot
              </div>
              <div className="text-sm font-semibold tnum text-white">
                {spot ? `₹${fmt(spot)}` : chainQuery.isLoading ? "Loading…" : "—"}
              </div>
            </div>

            {/* ATM */}
            <div className="flex flex-col gap-1">
              <div className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)]">
                ATM Strike
              </div>
              <div className="text-sm font-semibold tnum text-[var(--color-primary)]">
                {atmStrike ? fmt(atmStrike) : "—"}
              </div>
            </div>

            {/* DTE */}
            <div className="flex flex-col gap-1">
              <div className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)]">
                DTE
              </div>
              <div className="text-sm font-semibold tnum text-white">
                {selectedExpiry ? `${dte}d` : "—"}
              </div>
            </div>

            {/* Loading indicator */}
            {chainQuery.isLoading && (
              <div className="ml-auto text-xs text-[var(--color-text-muted)] animate-pulse">
                Fetching chain…
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Template loader */}
      <Card>
        <CardHeader>
          <CardTitle>Load Template</CardTitle>
        </CardHeader>
        <CardContent className="p-4">
          <div className="flex flex-wrap items-center gap-3">
            <select
              value={selectedTemplate}
              onChange={(e) => setSelectedTemplate(e.target.value)}
              className="rounded border border-[var(--color-border)] bg-[var(--color-surface-2)] px-3 py-1.5 text-sm text-white focus:outline-none focus:ring-1 focus:ring-[var(--color-primary)]"
            >
              <option value="">— Select strategy —</option>
              {Object.keys(STRATEGY_TEMPLATES).map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
            <button
              onClick={handleLoadTemplate}
              disabled={!selectedTemplate || !spot || chainQuery.isLoading}
              className="rounded bg-[var(--color-primary)] px-4 py-1.5 text-sm font-medium text-white transition hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              Load Template
            </button>
            <span className="text-xs text-[var(--color-text-muted)]">
              Replaces current legs
            </span>
          </div>
        </CardContent>
      </Card>

      {/* Legs table */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle>Strategy Legs</CardTitle>
            <button
              onClick={addLeg}
              disabled={legs.length >= 6 || !spot}
              className="rounded bg-[var(--color-surface-2)] border border-[var(--color-border)] px-3 py-1 text-xs font-medium text-white transition hover:bg-[var(--color-border)] disabled:opacity-40 disabled:cursor-not-allowed"
            >
              + Add Leg {legs.length > 0 && `(${legs.length}/6)`}
            </button>
          </div>
        </CardHeader>
        <CardContent className="p-0 overflow-x-auto">
          {legs.length === 0 ? (
            <div className="p-8 text-center text-sm text-[var(--color-text-muted)]">
              No legs added. Load a template or click &quot;+ Add Leg&quot; to begin.
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead className="border-b border-[var(--color-border)] bg-[var(--color-surface-2)]">
                <tr className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)]">
                  <th className="text-left px-3 py-2.5">#</th>
                  <th className="text-left px-3 py-2.5">Action</th>
                  <th className="text-left px-3 py-2.5">Type</th>
                  <th className="text-left px-3 py-2.5">Strike</th>
                  <th className="text-left px-3 py-2.5">Expiry</th>
                  <th className="text-left px-3 py-2.5">Lots</th>
                  <th className="text-left px-3 py-2.5">LTP (₹)</th>
                  <th className="text-right px-3 py-2.5">Net Prem.</th>
                  <th className="px-3 py-2.5" />
                </tr>
              </thead>
              <tbody>
                {legs.map((leg, idx) => {
                  const netPrem =
                    (leg.action === "BUY" ? -1 : 1) *
                    leg.ltp *
                    leg.lots *
                    leg.lot_size;
                  return (
                    <tr
                      key={idx}
                      className="border-b border-[var(--color-border)] hover:bg-[var(--color-surface-2)]/50 transition-colors"
                    >
                      <td className="px-3 py-2 text-[var(--color-text-muted)]">
                        {idx + 1}
                      </td>
                      {/* Action */}
                      <td className="px-3 py-2">
                        <select
                          value={leg.action}
                          onChange={(e) =>
                            updateLeg(idx, {
                              action: e.target.value as "BUY" | "SELL",
                            })
                          }
                          className={cn(
                            "rounded border px-2 py-1 text-xs font-semibold focus:outline-none focus:ring-1 focus:ring-[var(--color-primary)] bg-transparent",
                            leg.action === "BUY"
                              ? "border-[var(--color-success)] text-[var(--color-success)]"
                              : "border-[var(--color-danger)] text-[var(--color-danger)]",
                          )}
                        >
                          <option value="BUY">BUY</option>
                          <option value="SELL">SELL</option>
                        </select>
                      </td>
                      {/* Type */}
                      <td className="px-3 py-2">
                        <select
                          value={leg.option_type}
                          onChange={(e) =>
                            updateLeg(idx, {
                              option_type: e.target.value as "CE" | "PE" | "FUT",
                            })
                          }
                          className="rounded border border-[var(--color-border)] bg-[var(--color-surface-2)] px-2 py-1 text-xs text-white focus:outline-none focus:ring-1 focus:ring-[var(--color-primary)]"
                        >
                          <option value="CE">CE</option>
                          <option value="PE">PE</option>
                          <option value="FUT">FUT</option>
                        </select>
                      </td>
                      {/* Strike */}
                      <td className="px-3 py-2">
                        {leg.option_type === "FUT" ? (
                          <span className="text-xs text-[var(--color-text-muted)] italic">
                            futures
                          </span>
                        ) : (
                          <select
                            value={leg.strike}
                            onChange={(e) =>
                              updateLeg(idx, { strike: Number(e.target.value) })
                            }
                            className="rounded border border-[var(--color-border)] bg-[var(--color-surface-2)] px-2 py-1 text-xs text-white focus:outline-none focus:ring-1 focus:ring-[var(--color-primary)]"
                          >
                            {strikes.map((s) => (
                              <option key={s} value={s}>
                                {s === atmStrike ? `${s} (ATM)` : s}
                              </option>
                            ))}
                          </select>
                        )}
                      </td>
                      {/* Expiry */}
                      <td className="px-3 py-2">
                        <select
                          value={leg.expiry}
                          onChange={(e) =>
                            updateLeg(idx, { expiry: e.target.value })
                          }
                          className="rounded border border-[var(--color-border)] bg-[var(--color-surface-2)] px-2 py-1 text-xs text-white focus:outline-none focus:ring-1 focus:ring-[var(--color-primary)]"
                        >
                          {expiries.map((e) => (
                            <option key={e} value={e}>
                              {e}
                            </option>
                          ))}
                        </select>
                      </td>
                      {/* Lots */}
                      <td className="px-3 py-2">
                        <input
                          type="number"
                          min={1}
                          max={100}
                          value={leg.lots}
                          onChange={(e) =>
                            updateLeg(idx, {
                              lots: Math.max(1, parseInt(e.target.value) || 1),
                            })
                          }
                          className="w-16 rounded border border-[var(--color-border)] bg-[var(--color-surface-2)] px-2 py-1 text-xs text-white tnum focus:outline-none focus:ring-1 focus:ring-[var(--color-primary)]"
                        />
                      </td>
                      {/* LTP */}
                      <td className="px-3 py-2">
                        <input
                          type="number"
                          min={0}
                          step={0.05}
                          value={leg.ltp}
                          onChange={(e) =>
                            updateLeg(idx, { ltp: parseFloat(e.target.value) || 0 })
                          }
                          className="w-24 rounded border border-[var(--color-border)] bg-[var(--color-surface-2)] px-2 py-1 text-xs text-white tnum focus:outline-none focus:ring-1 focus:ring-[var(--color-primary)]"
                        />
                      </td>
                      {/* Net premium */}
                      <td
                        className={cn(
                          "px-3 py-2 text-right text-xs font-medium tnum",
                          netPrem >= 0
                            ? "text-[var(--color-success)]"
                            : "text-[var(--color-danger)]",
                        )}
                      >
                        {netPrem >= 0 ? "+" : ""}₹
                        {Math.abs(netPrem).toLocaleString("en-IN", {
                          maximumFractionDigits: 0,
                        })}
                      </td>
                      {/* Delete */}
                      <td className="px-3 py-2 text-right">
                        <button
                          onClick={() => removeLeg(idx)}
                          className="text-[var(--color-text-muted)] hover:text-[var(--color-danger)] transition-colors text-base leading-none"
                          aria-label="Remove leg"
                        >
                          ✕
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>

      {/* Results section */}
      {results && (
        <>
          {/* Metric cards */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            <MetricCard
              label="Net Premium"
              value={fmtRs(results.pml.netPremium)}
              variant={results.pml.isDebit ? "danger" : "success"}
              sub={results.pml.isDebit ? "Debit (paid)" : "Credit (received)"}
            />
            <MetricCard
              label="Max Profit"
              value={
                results.pml.unlimitedProfit
                  ? "Unlimited"
                  : `+${fmtRs(results.pml.maxProfit)}`
              }
              variant="success"
            />
            <MetricCard
              label="Max Loss"
              value={
                results.pml.unlimitedLoss
                  ? "Unlimited"
                  : `-${fmtRs(Math.abs(results.pml.maxLoss))}`
              }
              variant="danger"
            />
            <MetricCard
              label="Est. Margin"
              value={fmtRs(results.margin.totalMargin)}
              sub={`SPAN ₹${fmt(Math.round(results.margin.spanMargin))} + Exp ₹${fmt(Math.round(results.margin.exposureMargin))}`}
            />
          </div>

          {/* Breakevens */}
          {results.bks.length > 0 && (
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs text-[var(--color-text-muted)]">
                Breakeven{results.bks.length > 1 ? "s" : ""}:
              </span>
              {results.bks.map((be, i) => (
                <Badge key={i} variant="warning">
                  ₹{fmt(Math.round(be))}
                </Badge>
              ))}
            </div>
          )}

          {/* Greeks */}
          <Card>
            <CardHeader>
              <CardTitle>Position Greeks</CardTitle>
            </CardHeader>
            <CardContent className="p-4">
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm tnum">
                {[
                  {
                    label: "Delta (Δ)",
                    value: results.greeks.delta.toFixed(4),
                    color:
                      results.greeks.delta > 0
                        ? "text-[var(--color-success)]"
                        : results.greeks.delta < 0
                        ? "text-[var(--color-danger)]"
                        : "text-white",
                  },
                  {
                    label: "Gamma (Γ)",
                    value: results.greeks.gamma.toFixed(6),
                    color: "text-white",
                  },
                  {
                    label: "Theta (Θ) /day",
                    value: results.greeks.theta.toFixed(2),
                    color:
                      results.greeks.theta > 0
                        ? "text-[var(--color-success)]"
                        : "text-[var(--color-danger)]",
                  },
                  {
                    label: "Vega (ν) /1%",
                    value: results.greeks.vega.toFixed(2),
                    color: "text-white",
                  },
                ].map(({ label, value, color }) => (
                  <div
                    key={label}
                    className="rounded border border-[var(--color-border)] bg-[var(--color-surface-2)] p-3"
                  >
                    <div className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)] mb-1">
                      {label}
                    </div>
                    <div className={cn("text-base font-bold", color)}>{value}</div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>

          {/* Payoff diagram */}
          <Card>
            <CardHeader>
              <CardTitle>Payoff at Expiry</CardTitle>
            </CardHeader>
            <CardContent className="p-4">
              <ResponsiveContainer width="100%" height={320}>
                <AreaChart
                  data={payoffData}
                  margin={{ top: 8, right: 16, bottom: 8, left: 16 }}
                >
                  <defs>
                    <linearGradient id="pnlGradient" x1="0" y1="0" x2="0" y2="1">
                      <stop
                        offset="5%"
                        stopColor="var(--color-success)"
                        stopOpacity={0.3}
                      />
                      <stop
                        offset="95%"
                        stopColor="var(--color-success)"
                        stopOpacity={0}
                      />
                    </linearGradient>
                  </defs>
                  <CartesianGrid
                    strokeDasharray="3 3"
                    stroke="var(--color-border)"
                    vertical={false}
                  />
                  <XAxis
                    dataKey="price"
                    tickFormatter={(v: number) => `₹${Math.round(v / 100) * 100}`}
                    tick={{
                      fontSize: 10,
                      fill: "var(--color-text-muted)",
                    }}
                    tickLine={false}
                    axisLine={false}
                  />
                  <YAxis
                    tickFormatter={(v: number) =>
                      v >= 0
                        ? `+₹${(Math.abs(v) / 1000).toFixed(0)}k`
                        : `-₹${(Math.abs(v) / 1000).toFixed(0)}k`
                    }
                    tick={{
                      fontSize: 10,
                      fill: "var(--color-text-muted)",
                    }}
                    tickLine={false}
                    axisLine={false}
                    width={56}
                  />
                  <Tooltip content={<PayoffTooltip />} />
                  {/* Zero line */}
                  <ReferenceLine
                    y={0}
                    stroke="var(--color-text-muted)"
                    strokeDasharray="4 2"
                    strokeWidth={1}
                  />
                  {/* Spot line */}
                  {spot > 0 && (
                    <ReferenceLine
                      x={spot}
                      stroke="var(--color-primary)"
                      strokeDasharray="4 2"
                      strokeWidth={1.5}
                      label={{
                        value: "Spot",
                        position: "insideTopRight",
                        fill: "var(--color-primary)",
                        fontSize: 10,
                      }}
                    />
                  )}
                  {/* Breakeven lines */}
                  {results.bks.map((be, i) => (
                    <ReferenceLine
                      key={i}
                      x={be}
                      stroke="#f5a623"
                      strokeDasharray="3 3"
                      strokeWidth={1}
                      label={{
                        value: `BE`,
                        position: "insideTopLeft",
                        fill: "#f5a623",
                        fontSize: 9,
                      }}
                    />
                  ))}
                  <Area
                    type="monotone"
                    dataKey="pnl"
                    stroke="var(--color-success)"
                    strokeWidth={2}
                    fill="url(#pnlGradient)"
                    dot={false}
                    activeDot={{ r: 3, fill: "var(--color-success)" }}
                  />
                </AreaChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        </>
      )}

      {/* Save strategy */}
      <Card>
        <CardHeader>
          <CardTitle>Save Strategy</CardTitle>
        </CardHeader>
        <CardContent className="p-4">
          <div className="flex flex-wrap items-center gap-3">
            <input
              type="text"
              placeholder="Strategy name…"
              value={strategyName}
              onChange={(e) => setStrategyName(e.target.value)}
              className="rounded border border-[var(--color-border)] bg-[var(--color-surface-2)] px-3 py-1.5 text-sm text-white placeholder:text-[var(--color-text-muted)] focus:outline-none focus:ring-1 focus:ring-[var(--color-primary)]"
            />
            <button
              onClick={handleSave}
              disabled={!strategyName.trim() || !legs.length}
              className="rounded bg-[var(--color-primary)] px-4 py-1.5 text-sm font-medium text-white transition hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              Save
            </button>
            {saveMsg && (
              <span className="text-xs text-[var(--color-success)]">{saveMsg}</span>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Saved strategies */}
      {savedStrategies.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Saved Strategies</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <table className="w-full text-sm">
              <thead className="border-b border-[var(--color-border)] bg-[var(--color-surface-2)]">
                <tr className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)]">
                  <th className="text-left px-4 py-2.5">Name</th>
                  <th className="text-center px-4 py-2.5">Legs</th>
                  <th className="text-left px-4 py-2.5">Saved At</th>
                  <th className="text-right px-4 py-2.5">Actions</th>
                </tr>
              </thead>
              <tbody>
                {savedStrategies.map((s) => (
                  <tr
                    key={s.name}
                    className="border-b border-[var(--color-border)] hover:bg-[var(--color-surface-2)]/60 transition-colors"
                  >
                    <td className="px-4 py-2.5 font-medium text-white">{s.name}</td>
                    <td className="px-4 py-2.5 text-center text-[var(--color-text-muted)] tnum">
                      {s.legs.length}
                    </td>
                    <td className="px-4 py-2.5 text-xs text-[var(--color-text-muted)]">
                      {new Date(s.saved_at).toLocaleString("en-IN", {
                        day: "2-digit",
                        month: "short",
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
                    </td>
                    <td className="px-4 py-2.5 text-right">
                      <div className="flex justify-end gap-2">
                        <button
                          onClick={() => handleLoadSaved(s)}
                          className="rounded border border-[var(--color-border)] px-2.5 py-1 text-xs text-white hover:bg-[var(--color-surface-2)] transition-colors"
                        >
                          Load
                        </button>
                        <button
                          onClick={() => handleDeleteSaved(s.name)}
                          className="rounded border border-[var(--color-danger)]/40 px-2.5 py-1 text-xs text-[var(--color-danger)] hover:bg-[var(--color-danger)]/10 transition-colors"
                        >
                          Delete
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
