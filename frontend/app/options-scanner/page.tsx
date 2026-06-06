"use client";

import { useState, useCallback, useEffect, useRef } from "react";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  X, RefreshCw, Download, ChevronDown, ChevronUp,
  Target, TrendingUp, TrendingDown, Activity, BarChart2,
  Clock, AlertTriangle, CheckCircle, Info,
} from "lucide-react";

// ── Types ─────────────────────────────────────────────────────────────────────

interface ScoreBreakdown {
  trend: number;
  price_action: number;
  sr_zone: number;
  volume: number;
  options_quality: number;
  mtf_bonus: number;
}

interface ScanResult {
  symbol: string;
  spot: number;
  signal: string;
  signal_icon: string;
  signal_label: string;
  strike: number;
  expiry: string;
  option_type: string;
  ltp: number;
  iv_pct: number;
  dte: number;
  oi: number;
  score: number;
  trend_aligned: boolean;
  sr_zone: string;
  volume_conf: boolean;
  entry_price: number;
  target_price: number;
  stop_loss: number;
  reward_risk: number;
  entry_zone: string;
  max_loss: number;
  lot_size: number;
  score_breakdown: ScoreBreakdown;
  reasons: string[];
  timestamp: string;
}

interface MarketContext {
  vix: number;
  vix_level: string;
  nifty: { spot: number; change_pct: number; pcr_oi: number; pcr_signal: string };
  banknifty: { spot: number; change_pct: number; pcr_oi: number; pcr_signal: string };
}

interface TimeframeData {
  trend: string;
  ema20: number;
  ema50: number;
  last_close: number;
  adx: number;
  ema_aligned: boolean;
  structure: string;
  rsi: number;
  obv_trend: string;
  volume_signal: string;
  patterns: Array<{ name: string; direction: string; strength: number; description: string }>;
  key_levels: Array<{ price: number; type: string; significance: number; description: string }>;
  cpr: { pivot: number; bc: number; tc: number; width_pct: number; is_narrow: boolean; is_wide: boolean } | null;
}

interface DeepDiveData {
  symbol: string;
  spot: number;
  lot_size: number;
  mtf: {
    monthly: TimeframeData | null;
    weekly: TimeframeData | null;
    daily: TimeframeData | null;
    hourly: TimeframeData | null;
    overall_trend: string;
    alignment_count: number;
  };
  ce_setup: ScanResult;
  pe_setup: ScanResult;
  option_chain_summary: Array<{
    strike: number;
    ce_ltp: number; ce_iv: number; ce_oi: number;
    pe_ltp: number; pe_iv: number; pe_oi: number;
  }>;
  pcr: { pcr_oi?: number; pcr_vol?: number };
  max_pain: number;
  timestamp: string;
}

// ── Constants ─────────────────────────────────────────────────────────────────

const UNIVERSE_OPTIONS = [
  { value: "nifty_50",    label: "NIFTY 50" },
  { value: "nifty_100",   label: "NIFTY 100" },
  { value: "nifty_200",   label: "NIFTY 200" },
  { value: "nifty_bank",  label: "NIFTY Bank" },
  { value: "nifty_it",    label: "NIFTY IT" },
  { value: "nifty_midcap",label: "NIFTY Midcap" },
  { value: "indices_only",label: "Indices Only" },
  { value: "all",         label: "All F&O" },
];

const SIGNAL_OPTIONS = [
  { value: "all",     label: "All Signals" },
  { value: "ce_only", label: "CE Only" },
  { value: "pe_only", label: "PE Only" },
];

// ── Helpers ───────────────────────────────────────────────────────────────────

function scoreColor(score: number): string {
  if (score >= 85) return "var(--color-success)";
  if (score >= 70) return "#22c55e";
  if (score >= 60) return "#f5c542";
  return "var(--color-text-muted)";
}

function scoreRowBg(score: number): string {
  if (score >= 85) return "bg-[color-mix(in_oklab,#22c55e_8%,transparent)]";
  if (score >= 70) return "bg-[color-mix(in_oklab,#22c55e_4%,transparent)]";
  if (score >= 60) return "bg-[color-mix(in_oklab,#f5c542_4%,transparent)]";
  return "";
}

function signalBadgeVariant(signal: string): "success" | "danger" | "info" | "default" {
  if (signal.includes("STRONG_BUY_CE") || signal.includes("BUY_CE")) return "success";
  if (signal.includes("STRONG_BUY_PE") || signal.includes("BUY_PE")) return "danger";
  if (signal.includes("WATCHLIST")) return "info";
  return "default";
}

function trendColor(trend: string): string {
  if (trend === "UPTREND")   return "var(--color-success)";
  if (trend === "DOWNTREND") return "var(--color-danger)";
  return "var(--color-text-muted)";
}

function trendIcon(trend: string) {
  if (trend === "UPTREND")   return <TrendingUp  className="size-3.5 inline" />;
  if (trend === "DOWNTREND") return <TrendingDown className="size-3.5 inline" />;
  return <Activity className="size-3.5 inline" />;
}

function fmtPct(v: number): string {
  return `${v >= 0 ? "+" : ""}${v.toFixed(2)}%`;
}

function Spinner({ size = 4 }: { size?: number }) {
  return (
    <svg
      className={`animate-spin size-${size} text-[var(--color-primary)]`}
      xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"
    >
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
    </svg>
  );
}

// ── Score gauge ───────────────────────────────────────────────────────────────

function ScoreGauge({ score }: { score: number }) {
  const r    = 28;
  const circ = 2 * Math.PI * r;
  const dash = (score / 100) * circ;
  const color = scoreColor(score);

  return (
    <div className="relative inline-flex items-center justify-center">
      <svg width="72" height="72">
        <circle cx="36" cy="36" r={r} fill="none" stroke="var(--color-surface-2)" strokeWidth="6" />
        <circle
          cx="36" cy="36" r={r} fill="none"
          stroke={color} strokeWidth="6"
          strokeDasharray={`${dash} ${circ - dash}`}
          strokeLinecap="round"
          transform="rotate(-90 36 36)"
        />
      </svg>
      <span className="absolute text-sm font-bold" style={{ color }}>
        {score}
      </span>
    </div>
  );
}

// ── Score bar strip ───────────────────────────────────────────────────────────

function ScoreBar({ label, value, max }: { label: string; value: number; max: number }) {
  const pct = (value / max) * 100;
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="w-28 text-[var(--color-text-muted)] truncate">{label}</span>
      <div className="flex-1 h-1.5 rounded-full bg-[var(--color-surface-2)] overflow-hidden">
        <div
          className="h-full rounded-full"
          style={{ width: `${pct}%`, background: "var(--color-primary)" }}
        />
      </div>
      <span className="w-8 tabular-nums text-right text-[var(--color-text)]">
        {value}/{max}
      </span>
    </div>
  );
}

// ── Market Context Bar ────────────────────────────────────────────────────────

function MarketContextBar({ ctx }: { ctx: MarketContext | null }) {
  if (!ctx) return null;

  const vixColor = ctx.vix_level === "low" ? "var(--color-success)"
    : ctx.vix_level === "high" ? "var(--color-danger)" : "#f5c542";

  const pcrColor = (pcr: number) =>
    pcr < 0.8 ? "var(--color-success)" : pcr > 1.2 ? "var(--color-danger)" : "var(--color-text-muted)";

  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
      {/* NIFTY */}
      <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] p-3">
        <div className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)] mb-1">NIFTY</div>
        <div className="text-base font-bold text-white">
          {ctx.nifty.spot > 0 ? ctx.nifty.spot.toLocaleString("en-IN", { maximumFractionDigits: 0 }) : "—"}
        </div>
        <div className="flex items-center gap-2 mt-0.5">
          <span className="text-xs" style={{ color: ctx.nifty.change_pct >= 0 ? "var(--color-success)" : "var(--color-danger)" }}>
            {fmtPct(ctx.nifty.change_pct)}
          </span>
          <span className="text-[10px]" style={{ color: pcrColor(ctx.nifty.pcr_oi) }}>
            PCR {ctx.nifty.pcr_oi.toFixed(2)}
          </span>
        </div>
      </div>

      {/* BANKNIFTY */}
      <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] p-3">
        <div className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)] mb-1">BANKNIFTY</div>
        <div className="text-base font-bold text-white">
          {ctx.banknifty.spot > 0 ? ctx.banknifty.spot.toLocaleString("en-IN", { maximumFractionDigits: 0 }) : "—"}
        </div>
        <div className="flex items-center gap-2 mt-0.5">
          <span className="text-xs" style={{ color: ctx.banknifty.change_pct >= 0 ? "var(--color-success)" : "var(--color-danger)" }}>
            {fmtPct(ctx.banknifty.change_pct)}
          </span>
          <span className="text-[10px]" style={{ color: pcrColor(ctx.banknifty.pcr_oi) }}>
            PCR {ctx.banknifty.pcr_oi.toFixed(2)}
          </span>
        </div>
      </div>

      {/* VIX */}
      <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] p-3">
        <div className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)] mb-1">India VIX</div>
        <div className="text-base font-bold" style={{ color: vixColor }}>
          {ctx.vix > 0 ? ctx.vix.toFixed(2) : "—"}
        </div>
        <div className="text-[10px] mt-0.5 capitalize" style={{ color: vixColor }}>
          {ctx.vix_level} volatility
        </div>
      </div>

      {/* Guide */}
      <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] p-3">
        <div className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)] mb-1">Strategy</div>
        <div className="text-[11px] text-[var(--color-text-muted)] leading-relaxed">
          Buy CE/PE options<br />
          ATM or 1-ITM strike<br />
          DTE ≥ 7 · IV &lt; 50%
        </div>
      </div>
    </div>
  );
}

// ── Featured Pick Card ────────────────────────────────────────────────────────

function FeaturedCard({
  rank, result, onDeepDive, onAddWatchlist,
}: {
  rank: number;
  result: ScanResult;
  onDeepDive: (r: ScanResult) => void;
  onAddWatchlist: (r: ScanResult) => void;
}) {
  const isCe = result.option_type === "CE";

  return (
    <div className={cn(
      "relative rounded-xl border p-4 flex flex-col gap-3",
      result.score >= 85
        ? "border-[color-mix(in_oklab,#22c55e_40%,var(--color-border))] bg-[color-mix(in_oklab,#22c55e_5%,var(--color-surface))]"
        : "border-[var(--color-border)] bg-[var(--color-surface)]",
    )}>
      {/* Rank badge */}
      <div className="absolute top-3 right-3 text-[10px] font-bold text-[var(--color-text-muted)]">#{rank}</div>

      {/* Header */}
      <div className="flex items-start gap-3">
        <ScoreGauge score={result.score} />
        <div className="flex-1 min-w-0">
          <div className="font-bold text-white text-base leading-tight">{result.symbol}</div>
          <div className="text-xs text-[var(--color-text-muted)] mt-0.5">
            {result.signal_icon} {result.signal_label}
          </div>
          <div className="text-xs text-[var(--color-text)] mt-1">
            <span className={isCe ? "text-[var(--color-success)]" : "text-[var(--color-danger)]"}>
              {result.option_type} {result.strike}
            </span>
            {" · "}Exp {result.expiry.slice(0, 6)} · DTE {result.dte}d
          </div>
        </div>
      </div>

      {/* Entry/Target/SL */}
      <div className="grid grid-cols-3 gap-2 text-center">
        <div className="rounded bg-[var(--color-surface-2)] px-2 py-1.5">
          <div className="text-[9px] uppercase tracking-wider text-[var(--color-text-muted)]">Entry</div>
          <div className="text-xs font-semibold text-white">₹{result.entry_price.toFixed(2)}</div>
        </div>
        <div className="rounded bg-[color-mix(in_oklab,var(--color-success)_10%,transparent)] px-2 py-1.5">
          <div className="text-[9px] uppercase tracking-wider text-[var(--color-success)]">Target</div>
          <div className="text-xs font-semibold text-[var(--color-success)]">₹{result.target_price.toFixed(2)}</div>
        </div>
        <div className="rounded bg-[color-mix(in_oklab,var(--color-danger)_10%,transparent)] px-2 py-1.5">
          <div className="text-[9px] uppercase tracking-wider text-[var(--color-danger)]">SL</div>
          <div className="text-xs font-semibold text-[var(--color-danger)]">₹{result.stop_loss.toFixed(2)}</div>
        </div>
      </div>

      {/* Max loss warning */}
      <div className="text-[10px] text-[var(--color-danger)] font-medium">
        Max loss / lot: ₹{result.max_loss.toLocaleString("en-IN")}
        <span className="ml-1 text-[var(--color-text-muted)] font-normal">
          · R:R {result.reward_risk}×
        </span>
      </div>

      {/* Top reason */}
      {result.reasons.length > 0 && (
        <div className="text-[11px] text-[var(--color-text-muted)] bg-[var(--color-surface-2)] rounded px-2 py-1.5 line-clamp-2">
          {result.reasons.slice(0, 2).join(" · ")}
        </div>
      )}

      {/* Actions */}
      <div className="flex gap-2 mt-auto pt-1">
        <button
          onClick={() => onDeepDive(result)}
          className="flex-1 rounded border border-[var(--color-border)] py-1.5 text-[11px] font-medium text-[var(--color-text)] hover:bg-[var(--color-surface-2)] transition-colors"
        >
          Deep Dive
        </button>
        <button
          onClick={() => onAddWatchlist(result)}
          className="flex-1 rounded bg-[var(--color-primary)] py-1.5 text-[11px] font-medium text-white hover:opacity-90 transition-opacity"
        >
          Watchlist
        </button>
      </div>
    </div>
  );
}

// ── Deep Dive Modal ───────────────────────────────────────────────────────────

function TFCard({ label, tf }: { label: string; tf: TimeframeData | null }) {
  if (!tf) return (
    <div className="rounded border border-[var(--color-border)] p-3 text-center text-xs text-[var(--color-text-muted)]">
      {label}: no data
    </div>
  );

  return (
    <div className="rounded border border-[var(--color-border)] bg-[var(--color-surface-2)] p-3 space-y-1.5">
      <div className="flex items-center justify-between">
        <span className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)]">{label}</span>
        <span className="text-[11px] font-semibold flex items-center gap-1" style={{ color: trendColor(tf.trend) }}>
          {trendIcon(tf.trend)} {tf.trend}
        </span>
      </div>
      <div className="grid grid-cols-2 gap-x-3 gap-y-0.5 text-[11px]">
        <span className="text-[var(--color-text-muted)]">EMA20</span>
        <span className="tabular-nums text-right text-[var(--color-text)]">{tf.ema20.toFixed(2)}</span>
        <span className="text-[var(--color-text-muted)]">EMA50</span>
        <span className="tabular-nums text-right text-[var(--color-text)]">{tf.ema50.toFixed(2)}</span>
        <span className="text-[var(--color-text-muted)]">ADX</span>
        <span className="tabular-nums text-right" style={{ color: tf.adx > 25 ? "var(--color-success)" : "var(--color-text-muted)" }}>
          {tf.adx.toFixed(1)} {tf.adx > 25 ? "✓" : ""}
        </span>
        <span className="text-[var(--color-text-muted)]">RSI</span>
        <span className="tabular-nums text-right text-[var(--color-text)]">{tf.rsi.toFixed(1)}</span>
        <span className="text-[var(--color-text-muted)]">Structure</span>
        <span className="tabular-nums text-right text-[var(--color-text)]">{tf.structure}</span>
        <span className="text-[var(--color-text-muted)]">OBV</span>
        <span className="tabular-nums text-right text-[var(--color-text)]">{tf.obv_trend}</span>
      </div>
      {tf.patterns.length > 0 && (
        <div className="pt-1 border-t border-[var(--color-border)]">
          {tf.patterns.slice(0, 2).map((p, i) => (
            <div key={i} className="text-[10px] text-[var(--color-text-muted)] truncate">
              {p.direction === "BULLISH" ? "🟢" : p.direction === "BEARISH" ? "🔴" : "🟡"} {p.name}
            </div>
          ))}
        </div>
      )}
      {tf.cpr && (
        <div className="pt-1 border-t border-[var(--color-border)]">
          <div className="text-[10px] text-[var(--color-text-muted)]">
            CPR: P {tf.cpr.pivot.toFixed(0)} · BC {tf.cpr.bc.toFixed(0)} · TC {tf.cpr.tc.toFixed(0)}
            {" "}
            <span className={tf.cpr.is_narrow ? "text-[var(--color-success)]" : tf.cpr.is_wide ? "text-[var(--color-danger)]" : ""}>
              ({tf.cpr.is_narrow ? "Narrow" : tf.cpr.is_wide ? "Wide" : "Normal"})
            </span>
          </div>
        </div>
      )}
    </div>
  );
}

type DeepDiveTab = "mtf" | "setup" | "chain" | "score";

function DeepDiveModal({
  symbol, data, loading, onClose,
}: {
  symbol: string;
  data: DeepDiveData | null;
  loading: boolean;
  onClose: () => void;
}) {
  const [tab, setTab] = useState<DeepDiveTab>("mtf");
  const [lots, setLots] = useState(1);

  useEffect(() => { setTab("mtf"); setLots(1); }, [symbol]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
      <div className="relative w-full max-w-4xl max-h-[90vh] overflow-y-auto rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] shadow-2xl">
        {/* Header */}
        <div className="sticky top-0 z-10 flex items-center justify-between px-5 py-4 border-b border-[var(--color-border)] bg-[var(--color-surface)]">
          <div>
            <h2 className="text-base font-semibold text-white">{symbol} — Deep Dive</h2>
            {data && (
              <p className="text-[11px] text-[var(--color-text-muted)] mt-0.5">
                Spot ₹{data.spot.toLocaleString("en-IN")} · Lot {data.lot_size} · {data.mtf.overall_trend}
              </p>
            )}
          </div>
          <button
            onClick={onClose}
            className="rounded-full p-1.5 hover:bg-[var(--color-surface-2)] transition-colors text-[var(--color-text-muted)]"
          >
            <X className="size-4" />
          </button>
        </div>

        {loading && (
          <div className="flex items-center justify-center py-20 gap-3">
            <Spinner size={6} />
            <span className="text-sm text-[var(--color-text-muted)]">Fetching MTF analysis…</span>
          </div>
        )}

        {!loading && data && (
          <>
            {/* Tabs */}
            <div className="flex gap-1 px-5 pt-4 border-b border-[var(--color-border)]">
              {(["mtf", "setup", "chain", "score"] as DeepDiveTab[]).map((t) => (
                <button
                  key={t}
                  onClick={() => setTab(t)}
                  className={cn(
                    "px-3 py-1.5 text-xs font-medium rounded-t border-b-2 -mb-px transition-colors capitalize",
                    tab === t
                      ? "border-[var(--color-primary)] text-white bg-[var(--color-surface-2)]"
                      : "border-transparent text-[var(--color-text-muted)] hover:text-white",
                  )}
                >
                  {t === "mtf" ? "MTF Analysis" : t === "setup" ? "Options Setup" : t === "chain" ? "Option Chain" : "Score Card"}
                </button>
              ))}
            </div>

            <div className="p-5 space-y-4">
              {/* TAB 1 — MTF Grid */}
              {tab === "mtf" && (
                <div className="space-y-3">
                  <div className="grid grid-cols-2 gap-3">
                    <TFCard label="Monthly" tf={data.mtf.monthly} />
                    <TFCard label="Weekly"  tf={data.mtf.weekly} />
                    <TFCard label="Daily"   tf={data.mtf.daily} />
                    <TFCard label="Hourly"  tf={data.mtf.hourly} />
                  </div>
                  <div className="text-xs text-[var(--color-text-muted)] text-center">
                    {data.mtf.alignment_count}/4 timeframes aligned · Overall: {" "}
                    <span style={{ color: trendColor(data.mtf.overall_trend) }}>
                      {trendIcon(data.mtf.overall_trend)} {data.mtf.overall_trend}
                    </span>
                  </div>
                </div>
              )}

              {/* TAB 2 — Options Setup */}
              {tab === "setup" && (
                <div className="space-y-4">
                  {[data.ce_setup, data.pe_setup].map((s) => {
                    const isCe = s.option_type === "CE";
                    const capital = s.entry_price * s.lot_size * lots;
                    const maxLoss = (s.entry_price - s.stop_loss) * s.lot_size * lots;
                    const profit  = (s.target_price - s.entry_price) * s.lot_size * lots;

                    return (
                      <div key={s.option_type} className={cn(
                        "rounded-lg border p-4 space-y-3",
                        s.signal === "NO_TRADE"
                          ? "border-[var(--color-border)] opacity-50"
                          : isCe
                          ? "border-[color-mix(in_oklab,var(--color-success)_30%,var(--color-border))]"
                          : "border-[color-mix(in_oklab,var(--color-danger)_30%,var(--color-border))]",
                      )}>
                        <div className="flex items-center justify-between">
                          <div className="font-semibold text-white">
                            {s.option_type} {s.strike} · {s.expiry.slice(0, 6)} · DTE {s.dte}d
                          </div>
                          <Badge variant={signalBadgeVariant(s.signal)}>
                            {s.signal_icon} {s.signal_label}
                          </Badge>
                        </div>

                        {s.signal !== "NO_TRADE" && s.entry_price > 0 && (
                          <>
                            <div className="grid grid-cols-3 gap-3 text-center">
                              <div>
                                <div className="text-[9px] uppercase text-[var(--color-text-muted)]">Entry</div>
                                <div className="text-sm font-bold text-white">₹{s.entry_price.toFixed(2)}</div>
                              </div>
                              <div>
                                <div className="text-[9px] uppercase text-[var(--color-success)]">Target (2.5×)</div>
                                <div className="text-sm font-bold text-[var(--color-success)]">₹{s.target_price.toFixed(2)}</div>
                              </div>
                              <div>
                                <div className="text-[9px] uppercase text-[var(--color-danger)]">SL (35%)</div>
                                <div className="text-sm font-bold text-[var(--color-danger)]">₹{s.stop_loss.toFixed(2)}</div>
                              </div>
                            </div>

                            {/* Risk calculator */}
                            <div className="rounded bg-[var(--color-surface-2)] p-3 space-y-2">
                              <div className="flex items-center justify-between">
                                <span className="text-xs text-[var(--color-text-muted)]">Lots</span>
                                <div className="flex items-center gap-2">
                                  <button onClick={() => setLots(Math.max(1, lots-1))} className="size-6 rounded bg-[var(--color-border)] text-white text-xs">−</button>
                                  <span className="text-sm font-semibold text-white w-6 text-center">{lots}</span>
                                  <button onClick={() => setLots(lots+1)} className="size-6 rounded bg-[var(--color-border)] text-white text-xs">+</button>
                                </div>
                              </div>
                              <div className="grid grid-cols-3 gap-2 text-xs">
                                <div>
                                  <div className="text-[var(--color-text-muted)]">Capital</div>
                                  <div className="text-white font-medium">₹{capital.toLocaleString("en-IN", { maximumFractionDigits: 0 })}</div>
                                </div>
                                <div>
                                  <div className="text-[var(--color-danger)]">Max Loss</div>
                                  <div className="text-[var(--color-danger)] font-bold">₹{maxLoss.toLocaleString("en-IN", { maximumFractionDigits: 0 })}</div>
                                </div>
                                <div>
                                  <div className="text-[var(--color-success)]">Target Profit</div>
                                  <div className="text-[var(--color-success)] font-medium">₹{profit.toLocaleString("en-IN", { maximumFractionDigits: 0 })}</div>
                                </div>
                              </div>
                            </div>
                          </>
                        )}

                        {/* IV / DTE info */}
                        <div className="text-[11px] text-[var(--color-text-muted)]">
                          LTP ₹{s.ltp.toFixed(2)} · IV {s.iv_pct.toFixed(1)}% · OI {s.oi.toLocaleString()} · R:R {s.reward_risk}×
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}

              {/* TAB 3 — Option Chain */}
              {tab === "chain" && (
                <div className="space-y-3">
                  <div className="flex items-center gap-3 text-xs text-[var(--color-text-muted)]">
                    <span>Spot: ₹{data.spot.toLocaleString("en-IN")}</span>
                    <span>PCR OI: {(data.pcr.pcr_oi ?? 0).toFixed(2)}</span>
                    <span>Max Pain: ₹{data.max_pain.toLocaleString("en-IN")}</span>
                  </div>
                  <div className="overflow-x-auto rounded border border-[var(--color-border)]">
                    <table className="w-full text-xs">
                      <thead className="bg-[var(--color-surface-2)] text-[10px] uppercase tracking-wider text-[var(--color-text-muted)]">
                        <tr>
                          <th className="px-3 py-2 text-right text-[var(--color-success)]">CE OI</th>
                          <th className="px-3 py-2 text-right text-[var(--color-success)]">CE IV%</th>
                          <th className="px-3 py-2 text-right text-[var(--color-success)]">CE LTP</th>
                          <th className="px-3 py-2 text-center font-bold text-white">STRIKE</th>
                          <th className="px-3 py-2 text-left text-[var(--color-danger)]">PE LTP</th>
                          <th className="px-3 py-2 text-left text-[var(--color-danger)]">PE IV%</th>
                          <th className="px-3 py-2 text-left text-[var(--color-danger)]">PE OI</th>
                        </tr>
                      </thead>
                      <tbody>
                        {data.option_chain_summary.map((row, i) => {
                          const isAtm = Math.abs(row.strike - data.spot) / data.spot < 0.01;
                          return (
                            <tr
                              key={i}
                              className={cn(
                                "border-t border-[var(--color-border)]",
                                isAtm ? "bg-[color-mix(in_oklab,var(--color-primary)_8%,transparent)]" : "hover:bg-[var(--color-surface-2)]/40",
                              )}
                            >
                              <td className="px-3 py-1.5 tabular-nums text-right text-[var(--color-text-muted)]">
                                {(row.ce_oi / 1000).toFixed(0)}K
                              </td>
                              <td className="px-3 py-1.5 tabular-nums text-right text-[var(--color-text)]">
                                {row.ce_iv.toFixed(1)}
                              </td>
                              <td className="px-3 py-1.5 tabular-nums text-right font-medium text-[var(--color-success)]">
                                {row.ce_ltp.toFixed(2)}
                              </td>
                              <td className={cn("px-3 py-1.5 text-center font-bold", isAtm ? "text-white" : "text-[var(--color-text-muted)]")}>
                                {row.strike.toLocaleString("en-IN")}
                              </td>
                              <td className="px-3 py-1.5 tabular-nums font-medium text-[var(--color-danger)]">
                                {row.pe_ltp.toFixed(2)}
                              </td>
                              <td className="px-3 py-1.5 tabular-nums text-[var(--color-text)]">
                                {row.pe_iv.toFixed(1)}
                              </td>
                              <td className="px-3 py-1.5 tabular-nums text-[var(--color-text-muted)]">
                                {(row.pe_oi / 1000).toFixed(0)}K
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* TAB 4 — Score Card */}
              {tab === "score" && (() => {
                const best = data.ce_setup.score >= data.pe_setup.score ? data.ce_setup : data.pe_setup;
                const bd   = best.score_breakdown;
                return (
                  <div className="space-y-4">
                    <div className="flex items-center gap-4">
                      <ScoreGauge score={best.score} />
                      <div>
                        <div className="text-sm font-semibold text-white">
                          {best.signal_icon} {best.signal_label}
                        </div>
                        <div className="text-xs text-[var(--color-text-muted)] mt-0.5">
                          {best.option_type} {best.strike}
                        </div>
                      </div>
                    </div>

                    <div className="space-y-2">
                      <ScoreBar label="Trend (MTF)"    value={bd.trend}           max={25} />
                      <ScoreBar label="Price Action"   value={bd.price_action}    max={25} />
                      <ScoreBar label="S/R Zone"       value={bd.sr_zone}         max={20} />
                      <ScoreBar label="Volume"         value={bd.volume}          max={15} />
                      <ScoreBar label="Options Quality" value={bd.options_quality} max={15} />
                      <ScoreBar label="MTF Bonus"      value={bd.mtf_bonus}       max={10} />
                    </div>

                    <div className="rounded bg-[var(--color-surface-2)] p-3 space-y-1">
                      <div className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)] mb-1.5">
                        Scoring Reasons
                      </div>
                      {best.reasons.map((r, i) => (
                        <div key={i} className="text-[11px] text-[var(--color-text)] flex items-start gap-1.5">
                          <CheckCircle className="size-3 shrink-0 mt-0.5 text-[var(--color-success)]" />
                          {r}
                        </div>
                      ))}
                    </div>

                    <div className="rounded border border-amber-500/20 bg-amber-500/5 p-3 text-[11px] text-amber-400 flex gap-2">
                      <AlertTriangle className="size-3.5 shrink-0 mt-0.5" />
                      Max loss / lot: ₹{best.max_loss.toLocaleString("en-IN")} · Capital protection is priority.
                      Cut losses fast, let winners run.
                    </div>

                    <div className="text-[10px] text-[var(--color-text-muted)] text-center">
                      Strategy framework: Madras Trader (Tamil options educator) · ATM/1-ITM buying only
                    </div>
                  </div>
                );
              })()}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export default function OptionsScannerPage() {
  // ── State ────────────────────────────────────────────────────────────────
  const [universe,     setUniverse]     = useState("nifty_50");
  const [signalFilter, setSignalFilter] = useState("all");
  const [minScore,     setMinScore]     = useState(70);
  const [minDte,       setMinDte]       = useState(7);
  const [maxIvPct,     setMaxIvPct]     = useState(60);
  const [maxResults,   setMaxResults]   = useState(30);

  const [scanning,     setScanning]     = useState(false);
  const [results,      setResults]      = useState<ScanResult[]>([]);
  const [scanMeta,     setScanMeta]     = useState<{ count: number; scanned: number } | null>(null);
  const [scanError,    setScanError]    = useState("");
  const [hasScanned,   setHasScanned]   = useState(false);
  const [lastScanTime, setLastScanTime] = useState<Date | null>(null);

  const [marketCtx,    setMarketCtx]    = useState<MarketContext | null>(null);
  const [ctxLoading,   setCtxLoading]   = useState(false);

  const [expandedRow,  setExpandedRow]  = useState<string | null>(null);
  const [deepDiveSym,  setDeepDiveSym]  = useState<string | null>(null);
  const [deepDiveData, setDeepDiveData] = useState<DeepDiveData | null>(null);
  const [ddLoading,    setDdLoading]    = useState(false);

  const autoScanRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const [autoScan,   setAutoScan]       = useState(false);

  // ── Market context ────────────────────────────────────────────────────────
  const loadMarketContext = useCallback(async () => {
    setCtxLoading(true);
    try {
      const res = await fetch("/api/options-scanner/market-context");
      if (res.ok) setMarketCtx(await res.json());
    } catch { /* silent */ }
    finally { setCtxLoading(false); }
  }, []);

  useEffect(() => { loadMarketContext(); }, [loadMarketContext]);

  // ── Auto-scan ─────────────────────────────────────────────────────────────
  useEffect(() => {
    if (autoScan) {
      autoScanRef.current = setInterval(() => {
        const now = new Date();
        const h = now.getHours(), m = now.getMinutes();
        const inMarketHours = (h > 9 || (h === 9 && m >= 15)) && (h < 15 || (h === 15 && m <= 30));
        if (inMarketHours) handleScan();
      }, 15 * 60 * 1000);
    } else {
      if (autoScanRef.current) clearInterval(autoScanRef.current);
    }
    return () => { if (autoScanRef.current) clearInterval(autoScanRef.current); };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoScan, universe, signalFilter, minScore, minDte, maxIvPct]);

  // ── Scan ──────────────────────────────────────────────────────────────────
  const handleScan = useCallback(async () => {
    setScanError("");
    setScanning(true);
    setResults([]);
    setHasScanned(false);
    try {
      const qs = new URLSearchParams({
        universe:      universe,
        signal_filter: signalFilter,
        min_score:     String(minScore),
        min_dte:       String(minDte),
        max_iv_pct:    String(maxIvPct),
        max_results:   String(maxResults),
      });
      const res = await fetch(`/api/options-scanner/scan?${qs}`);
      if (!res.ok) throw new Error(`Server ${res.status}`);
      const data = await res.json();
      setResults(Array.isArray(data.results) ? data.results : []);
      setScanMeta({ count: data.count ?? 0, scanned: data.scanned ?? 0 });
      setLastScanTime(new Date());
    } catch (err) {
      setScanError(err instanceof Error ? err.message : String(err));
    } finally {
      setScanning(false);
      setHasScanned(true);
    }
  }, [universe, signalFilter, minScore, minDte, maxIvPct, maxResults]);

  // ── Deep Dive ─────────────────────────────────────────────────────────────
  const openDeepDive = useCallback(async (result: ScanResult) => {
    setDeepDiveSym(result.symbol);
    setDeepDiveData(null);
    setDdLoading(true);
    try {
      const res = await fetch(`/api/options-scanner/deep-dive?symbol=${result.symbol}`);
      if (res.ok) setDeepDiveData(await res.json());
    } catch { /* silent */ }
    finally { setDdLoading(false); }
  }, []);

  // ── CSV Export ────────────────────────────────────────────────────────────
  const exportCsv = useCallback(() => {
    const hdr = "Rank,Symbol,Spot,Signal,Strike,Type,Expiry,DTE,LTP,IV%,Score,Entry,Target,SL,R:R,MaxLoss,TrendAligned,VolumeConf\n";
    const rows = results.map((r, i) =>
      [i+1, r.symbol, r.spot, r.signal, r.strike, r.option_type,
       r.expiry, r.dte, r.ltp, r.iv_pct.toFixed(1), r.score,
       r.entry_price, r.target_price, r.stop_loss, r.reward_risk,
       r.max_loss, r.trend_aligned, r.volume_conf].join(","),
    ).join("\n");
    const blob = new Blob([hdr + rows], { type: "text/csv" });
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement("a");
    a.href     = url;
    a.download = `options-scan-${Date.now()}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }, [results]);

  // ── Derived ───────────────────────────────────────────────────────────────
  const top3    = results.slice(0, 3);
  const allRows = results.slice(3);

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <div className="space-y-6 max-w-[1400px] mx-auto">

      {/* Deep Dive Modal */}
      {deepDiveSym && (
        <DeepDiveModal
          symbol={deepDiveSym}
          data={deepDiveData}
          loading={ddLoading}
          onClose={() => { setDeepDiveSym(null); setDeepDiveData(null); }}
        />
      )}

      {/* Header */}
      <header>
        <h1 className="text-xl font-semibold text-white">Options Buying Scanner</h1>
        <p className="text-xs text-[var(--color-text-muted)] mt-0.5">
          Elite framework · ATM/1-ITM only · Score ≥ 70 · DTE ≥ 7 · IV &lt; 60% · R:R ≥ 2×
        </p>
      </header>

      {/* Market Context */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <span className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)]">Market Context</span>
          <button
            onClick={loadMarketContext}
            disabled={ctxLoading}
            className="flex items-center gap-1 text-[10px] text-[var(--color-text-muted)] hover:text-white transition-colors disabled:opacity-50"
          >
            <RefreshCw className={cn("size-3", ctxLoading && "animate-spin")} />
            Refresh
          </button>
        </div>
        <MarketContextBar ctx={marketCtx} />
      </div>

      {/* Scan Controls */}
      <Card>
        <CardHeader><CardTitle>Scan Controls</CardTitle></CardHeader>
        <CardContent className="p-4 space-y-5">
          {/* Universe + Signal */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <label className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)]">Universe</label>
              <div className="flex flex-wrap gap-1.5">
                {UNIVERSE_OPTIONS.map((opt) => (
                  <button
                    key={opt.value}
                    onClick={() => setUniverse(opt.value)}
                    disabled={scanning}
                    className={cn(
                      "rounded-full px-3 py-1 text-xs font-medium transition-colors border",
                      universe === opt.value
                        ? "bg-[var(--color-primary)] border-[var(--color-primary)] text-white"
                        : "border-[var(--color-border)] text-[var(--color-text-muted)] hover:border-[var(--color-primary)] hover:text-white",
                      scanning && "opacity-50 cursor-not-allowed",
                    )}
                  >
                    {opt.label}
                  </button>
                ))}
              </div>
            </div>
            <div className="space-y-1.5">
              <label className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)]">Signal Filter</label>
              <div className="flex gap-1.5">
                {SIGNAL_OPTIONS.map((opt) => (
                  <button
                    key={opt.value}
                    onClick={() => setSignalFilter(opt.value)}
                    disabled={scanning}
                    className={cn(
                      "rounded-full px-3 py-1 text-xs font-medium transition-colors border",
                      signalFilter === opt.value
                        ? "bg-[var(--color-primary)] border-[var(--color-primary)] text-white"
                        : "border-[var(--color-border)] text-[var(--color-text-muted)] hover:border-[var(--color-primary)] hover:text-white",
                      scanning && "opacity-50 cursor-not-allowed",
                    )}
                  >
                    {opt.label}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Sliders */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-xs">
            {[
              { label: "Min Score",    value: minScore,   set: setMinScore,   min: 40, max: 95, step: 5  },
              { label: "Min DTE",      value: minDte,     set: setMinDte,     min: 5,  max: 30, step: 1  },
              { label: "Max IV%ile",   value: maxIvPct,   set: setMaxIvPct,   min: 40, max: 80, step: 5  },
              { label: "Max Results",  value: maxResults, set: setMaxResults, min: 10, max: 100, step: 10 },
            ].map(({ label, value, set, min, max, step }) => (
              <div key={label} className="space-y-1.5">
                <div className="flex items-center justify-between">
                  <span className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)]">{label}</span>
                  <span className="font-semibold text-white">{value}</span>
                </div>
                <input
                  type="range" min={min} max={max} step={step} value={value}
                  onChange={(e) => set(Number(e.target.value))}
                  disabled={scanning}
                  className="w-full accent-[var(--color-primary)] disabled:opacity-50"
                />
              </div>
            ))}
          </div>

          {/* Actions */}
          <div className="flex flex-wrap items-center gap-3 pt-1">
            <button
              onClick={handleScan}
              disabled={scanning}
              className="flex items-center gap-2 rounded bg-[var(--color-primary)] px-5 py-2 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed transition"
            >
              {scanning ? <Spinner /> : <Target className="size-4" />}
              {scanning ? "Scanning…" : "Scan Now"}
            </button>

            <label className="flex items-center gap-2 text-xs text-[var(--color-text-muted)] cursor-pointer select-none">
              <div
                onClick={() => setAutoScan(!autoScan)}
                className={cn(
                  "relative inline-flex h-5 w-9 rounded-full transition-colors",
                  autoScan ? "bg-[var(--color-primary)]" : "bg-[var(--color-border)]",
                )}
              >
                <span className={cn(
                  "absolute top-0.5 left-0.5 size-4 rounded-full bg-white shadow transition-transform",
                  autoScan && "translate-x-4",
                )} />
              </div>
              Auto-scan (15 min · market hours)
            </label>

            {results.length > 0 && (
              <button
                onClick={exportCsv}
                className="ml-auto flex items-center gap-1.5 rounded border border-[var(--color-border)] px-3 py-1.5 text-xs font-medium text-[var(--color-text)] hover:bg-[var(--color-surface-2)] transition-colors"
              >
                <Download className="size-3.5" />
                Export CSV
              </button>
            )}
          </div>

          {/* Error */}
          {scanError && (
            <div className="text-xs text-[var(--color-danger)] bg-[color-mix(in_oklab,var(--color-danger)_8%,transparent)] border border-[color-mix(in_oklab,var(--color-danger)_20%,transparent)] rounded px-3 py-2">
              {scanError}
            </div>
          )}

          {/* Scan info */}
          {scanning && (
            <p className="text-xs text-[var(--color-text-muted)] animate-pulse">
              Fetching MTF data via yfinance + NSE option chains… this may take 60–120 seconds.
            </p>
          )}
        </CardContent>
      </Card>

      {/* Scan summary */}
      {hasScanned && !scanning && scanMeta && (
        <div className="flex flex-wrap items-center gap-3">
          <Badge variant="info">
            {scanMeta.count} setup{scanMeta.count !== 1 ? "s" : ""} found
          </Badge>
          <span className="text-xs text-[var(--color-text-muted)]">
            Scanned {scanMeta.scanned} symbols
          </span>
          {lastScanTime && (
            <span className="text-xs text-[var(--color-text-muted)] flex items-center gap-1">
              <Clock className="size-3" />
              {lastScanTime.toLocaleTimeString("en-IN")}
            </span>
          )}
        </div>
      )}

      {/* Top 3 Featured Picks */}
      {top3.length > 0 && (
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            <h2 className="text-sm font-semibold text-white">Featured Picks</h2>
            <span className="text-[10px] text-[var(--color-text-muted)] bg-[var(--color-surface-2)] rounded-full px-2 py-0.5">
              Top {top3.length}
            </span>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            {top3.map((r, i) => (
              <FeaturedCard
                key={`${r.symbol}-${r.option_type}`}
                rank={i + 1}
                result={r}
                onDeepDive={openDeepDive}
                onAddWatchlist={() => {}}
              />
            ))}
          </div>
        </div>
      )}

      {/* Results Table */}
      {results.length > 0 && (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle>All Setups</CardTitle>
              <div className="flex items-center gap-3 text-[10px] text-[var(--color-text-muted)]">
                <span className="flex items-center gap-1"><span className="size-2 rounded-full bg-[#22c55e] inline-block"/>≥85</span>
                <span className="flex items-center gap-1"><span className="size-2 rounded-full bg-[#4ade80] inline-block"/>70–84</span>
                <span className="flex items-center gap-1"><span className="size-2 rounded-full bg-[#f5c542] inline-block"/>60–69</span>
              </div>
            </div>
          </CardHeader>
          <CardContent className="p-0 overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="border-b border-[var(--color-border)] bg-[var(--color-surface-2)]">
                <tr className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)]">
                  <th className="px-3 py-2.5 text-right w-8">#</th>
                  <th className="px-3 py-2.5 text-left">Symbol</th>
                  <th className="px-3 py-2.5 text-right">Spot</th>
                  <th className="px-3 py-2.5 text-left">Signal</th>
                  <th className="px-3 py-2.5 text-right">Strike</th>
                  <th className="px-3 py-2.5 text-right">LTP</th>
                  <th className="px-3 py-2.5 text-right">IV%</th>
                  <th className="px-3 py-2.5 text-right">DTE</th>
                  <th className="px-3 py-2.5 text-right">Score</th>
                  <th className="px-3 py-2.5 text-right">Entry</th>
                  <th className="px-3 py-2.5 text-right">Target</th>
                  <th className="px-3 py-2.5 text-right">SL</th>
                  <th className="px-3 py-2.5 text-right">R:R</th>
                  <th className="px-3 py-2.5 text-right text-[var(--color-danger)]">MaxLoss/Lot</th>
                  <th className="px-3 py-2.5 text-center">Actions</th>
                </tr>
              </thead>
              <tbody>
                {results.map((row, i) => {
                  const rowKey   = `${row.symbol}-${row.option_type}`;
                  const expanded = expandedRow === rowKey;
                  const isCe     = row.option_type === "CE";

                  return (
                    <>
                      <tr
                        key={rowKey}
                        className={cn(
                          "border-b border-[var(--color-border)] cursor-pointer transition-colors",
                          scoreRowBg(row.score),
                          expanded ? "bg-[var(--color-surface-2)]" : "hover:bg-[var(--color-surface-2)]/50",
                        )}
                        onClick={() => setExpandedRow(expanded ? null : rowKey)}
                      >
                        <td className="px-3 py-2 text-right text-xs text-[var(--color-text-muted)]">{i + 1}</td>
                        <td className="px-3 py-2 font-semibold text-white">{row.symbol}</td>
                        <td className="px-3 py-2 text-right tabular-nums text-xs text-[var(--color-text-muted)]">
                          {row.spot.toLocaleString("en-IN")}
                        </td>
                        <td className="px-3 py-2">
                          <Badge variant={signalBadgeVariant(row.signal)} className="whitespace-nowrap">
                            {row.signal_icon} {isCe ? "CE" : "PE"}
                          </Badge>
                        </td>
                        <td className="px-3 py-2 text-right tabular-nums text-xs font-medium" style={{ color: isCe ? "var(--color-success)" : "var(--color-danger)" }}>
                          {row.strike.toLocaleString("en-IN")}
                        </td>
                        <td className="px-3 py-2 text-right tabular-nums text-xs text-[var(--color-text)]">
                          ₹{row.ltp.toFixed(2)}
                        </td>
                        <td className="px-3 py-2 text-right tabular-nums text-xs text-[var(--color-text-muted)]">
                          {row.iv_pct.toFixed(1)}%
                        </td>
                        <td className="px-3 py-2 text-right tabular-nums text-xs text-[var(--color-text-muted)]">
                          {row.dte}d
                        </td>
                        <td className="px-3 py-2 text-right">
                          <span className="text-sm font-bold tabular-nums" style={{ color: scoreColor(row.score) }}>
                            {row.score}
                          </span>
                        </td>
                        <td className="px-3 py-2 text-right tabular-nums text-xs text-[var(--color-text)]">
                          ₹{row.entry_price.toFixed(2)}
                        </td>
                        <td className="px-3 py-2 text-right tabular-nums text-xs text-[var(--color-success)]">
                          ₹{row.target_price.toFixed(2)}
                        </td>
                        <td className="px-3 py-2 text-right tabular-nums text-xs text-[var(--color-danger)]">
                          ₹{row.stop_loss.toFixed(2)}
                        </td>
                        <td className="px-3 py-2 text-right tabular-nums text-xs text-[var(--color-text-muted)]">
                          {row.reward_risk}×
                        </td>
                        <td className="px-3 py-2 text-right tabular-nums text-xs font-semibold text-[var(--color-danger)]">
                          ₹{row.max_loss.toLocaleString("en-IN", { maximumFractionDigits: 0 })}
                        </td>
                        <td className="px-3 py-2">
                          <div className="flex items-center gap-1 justify-center">
                            <button
                              onClick={(e) => { e.stopPropagation(); openDeepDive(row); }}
                              className="rounded border border-[var(--color-border)] px-2 py-0.5 text-[10px] text-[var(--color-text-muted)] hover:bg-[var(--color-surface)] hover:text-white transition-colors"
                            >
                              Deep Dive
                            </button>
                            {expanded
                              ? <ChevronUp className="size-3.5 text-[var(--color-text-muted)]" />
                              : <ChevronDown className="size-3.5 text-[var(--color-text-muted)]" />
                            }
                          </div>
                        </td>
                      </tr>

                      {/* Expanded row */}
                      {expanded && (
                        <tr key={`${rowKey}-exp`} className="border-b border-[var(--color-border)] bg-[var(--color-surface-2)]">
                          <td colSpan={15} className="px-4 py-3">
                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                              {/* Score breakdown */}
                              <div className="space-y-1.5">
                                <div className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)] mb-2">Score Breakdown</div>
                                <ScoreBar label="Trend"          value={row.score_breakdown.trend}           max={25} />
                                <ScoreBar label="Price Action"   value={row.score_breakdown.price_action}    max={25} />
                                <ScoreBar label="S/R Zone"       value={row.score_breakdown.sr_zone}         max={20} />
                                <ScoreBar label="Volume"         value={row.score_breakdown.volume}          max={15} />
                                <ScoreBar label="Options Quality" value={row.score_breakdown.options_quality} max={15} />
                                <ScoreBar label="MTF Bonus"      value={row.score_breakdown.mtf_bonus}       max={10} />
                              </div>

                              {/* Reasons + entry zone */}
                              <div className="space-y-2">
                                <div className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)]">Key Reasons</div>
                                <div className="space-y-0.5">
                                  {row.reasons.slice(0, 5).map((r, ri) => (
                                    <div key={ri} className="text-[11px] text-[var(--color-text)] flex items-start gap-1.5">
                                      <Info className="size-3 shrink-0 mt-0.5 text-[var(--color-primary)]" />
                                      {r}
                                    </div>
                                  ))}
                                </div>
                                <div className="text-[10px] text-[var(--color-text-muted)] mt-2 font-mono">
                                  {row.entry_zone}
                                </div>
                                <div className="text-[10px] text-[var(--color-text-muted)]">
                                  S/R: {row.sr_zone} · Vol: {row.volume_conf ? "✓ Confirmed" : "Not confirmed"}
                                  · OI: {row.oi.toLocaleString()} · DTE: {row.dte}d
                                </div>
                              </div>
                            </div>
                          </td>
                        </tr>
                      )}
                    </>
                  );
                })}
              </tbody>
            </table>
          </CardContent>
        </Card>
      )}

      {/* Empty state */}
      {hasScanned && !scanning && results.length === 0 && !scanError && (
        <div className="py-16 text-center text-sm text-[var(--color-text-muted)]">
          No qualifying setups found. Try lowering the Min Score or changing the Universe.
        </div>
      )}

      {/* Initial state */}
      {!hasScanned && !scanning && !scanError && (
        <div className="py-14 text-center space-y-2">
          <Target className="size-10 mx-auto text-[var(--color-text-muted)] opacity-40" />
          <p className="text-sm text-[var(--color-text-muted)]">
            Configure filters above and click <span className="text-white font-medium">Scan Now</span>
          </p>
          <p className="text-xs text-[var(--color-text-muted)] max-w-sm mx-auto">
            Each scan fetches 4-timeframe OHLCV data + NSE option chains.
            First scan may take 60–120 seconds.
          </p>
        </div>
      )}

      {/* Footer credit */}
      <div className="rounded border border-[var(--color-border)] bg-[var(--color-surface-2)] px-4 py-3 text-[11px] text-[var(--color-text-muted)]">
        <strong className="text-[var(--color-text)]">Strategy Framework:</strong>{" "}
        Madras Trader (Tamil options education, YouTube) — Top-down MTF analysis, PDH/PDL breakouts,
        ATM/1-ITM option buying, IV Percentile filter, 2.5× target / 35% SL.
        This scanner is for educational purposes. Options trading involves significant risk.
        Always trade with defined risk and follow capital protection rules.
      </div>
    </div>
  );
}
