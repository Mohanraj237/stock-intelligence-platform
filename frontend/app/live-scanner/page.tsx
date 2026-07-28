"use client";

import { useState, useCallback, useEffect, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { HelpTip } from "@/components/ui/tooltip";
import {
  TrendingUp, TrendingDown, Minus, Zap, RefreshCw,
  ChevronDown, ChevronRight, AlertTriangle,
  Activity, Clock, Info, CheckCircle2,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type {
  SetupCard, ScanResponse, ScanParams, OptionPlan, BacktestInfo, ScanSummary,
} from "@/lib/scanner-types";

// ─────────────────────────────────────────────────────────────────────────────
// API — SSE streaming (matches equity scanner behaviour)
// ─────────────────────────────────────────────────────────────────────────────

async function checkHealth(): Promise<boolean> {
  try {
    const res = await fetch("/api/live-scanner/health", { signal: AbortSignal.timeout(3000) });
    return res.ok;
  } catch {
    return false;
  }
}

interface ScanProgressState {
  done:        number;  // all symbols processed (including those with 0 setups)
  total:       number;
  currentSym:  string;
  found:       number;  // setups found for the current symbol
  setupsSoFar: number;  // cumulative setups
  enriching:   boolean;
}

async function streamScan(
  params: ScanParams,
  callbacks: {
    onProgress: (p: ScanProgressState) => void;
    onResult:   (r: ScanResponse) => void;
    onDone:     () => void;
    onError:    (msg: string) => void;
    signal?:    AbortSignal;
  },
): Promise<void> {
  const qs = new URLSearchParams({
    universe:  params.universe,
    threshold: String(params.threshold),
  });
  if (params.timeframes)    qs.set("timeframes", params.timeframes);
  if (params.pattern_names) qs.set("pattern_names", params.pattern_names);
  // Call FastAPI DIRECTLY — Next.js dev-server proxy buffers SSE responses
  // and only flushes at end, making the progress bar appear frozen.
  // Direct call (same as faGet in fno-api.ts) bypasses that buffer entirely.
  const FASTAPI = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";
  try {
    const res = await fetch(`${FASTAPI}/api/live-scanner/scan/stream?${qs}`, {
      signal: callbacks.signal,
    });
    if (!res.ok) {
      callbacks.onError(`HTTP ${res.status}`);
      return;
    }
    const reader  = res.body!.getReader();
    const decoder = new TextDecoder();
    let buffer    = "";
    let progress: ScanProgressState = { done: 0, total: 0, currentSym: "", found: 0, setupsSoFar: 0, enriching: false };

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";
      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;
        const raw = line.slice(6).trim();
        if (raw === "[DONE]") { callbacks.onDone(); return; }
        try {
          const msg = JSON.parse(raw);
          if (msg.type === "start") {
            progress = { done: 0, total: msg.total, currentSym: "", found: 0, setupsSoFar: 0, enriching: false };
            callbacks.onProgress(progress);
          } else if (msg.type === "progress") {
            progress = { ...progress, done: msg.done, total: msg.total, currentSym: msg.symbol, found: msg.found, setupsSoFar: msg.setups_so_far };
            callbacks.onProgress(progress);
          } else if (msg.type === "enriching") {
            progress = { ...progress, enriching: true, setupsSoFar: msg.setups };
            callbacks.onProgress(progress);
          } else if (msg.type === "result") {
            callbacks.onResult(msg as ScanResponse);
          }
        } catch { /* ignore parse errors */ }
      }
    }
    callbacks.onDone();
  } catch (err: any) {
    if (err?.name === "AbortError") return;
    callbacks.onError(err?.message ?? "Stream failed");
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────────────────

const fmt = (n: number, d = 0) =>
  n.toLocaleString("en-IN", { minimumFractionDigits: d, maximumFractionDigits: d });

const TF_COLOR: Record<string, string> = {
  "5m":  "bg-blue-500/20 text-blue-300 border-blue-500/30",
  "15m": "bg-purple-500/20 text-purple-300 border-purple-500/30",
  "30m": "bg-cyan-500/20 text-cyan-300 border-cyan-500/30",
  "1h":  "bg-orange-500/20 text-orange-300 border-orange-500/30",
  "4h":  "bg-amber-500/20 text-amber-300 border-amber-500/30",
  "1d":  "bg-teal-500/20 text-teal-300 border-teal-500/30",
  "1wk": "bg-indigo-500/20 text-indigo-300 border-indigo-500/30",
  "1mo": "bg-rose-500/20 text-rose-300 border-rose-500/30",
};

const TF_LABEL: Record<string, string> = {
  "5m": "5 min", "15m": "15 min", "30m": "30 min", "1h": "1 hr",
  "4h": "4 hr", "1d": "Daily", "1wk": "Weekly", "1mo": "Monthly",
};

const ALL_TFS = ["5m", "15m", "30m", "1h", "4h", "1d", "1wk", "1mo"] as const;

// Pattern families — colours + display labels (keys match backend family strings)
const FAMILY_META: Record<string, { label: string; active: string; muted: string }> = {
  candlestick:  { label: "Candlestick",   active: "text-yellow-300 border-yellow-500/50 bg-yellow-500/15", muted: "text-yellow-400/60" },
  price_action: { label: "Price Action",  active: "text-blue-300   border-blue-500/50   bg-blue-500/15",   muted: "text-blue-400/60"   },
  volume:       { label: "Volume",        active: "text-orange-300 border-orange-500/50 bg-orange-500/15", muted: "text-orange-400/60" },
  chart:        { label: "Chart Pattern", active: "text-purple-300 border-purple-500/50 bg-purple-500/15", muted: "text-purple-400/60" },
  harmonic:     { label: "Harmonic",      active: "text-pink-300   border-pink-500/50   bg-pink-500/15",   muted: "text-pink-400/60"   },
};

function TfBadge({ tf }: { tf: string }) {
  return (
    <span className={cn("inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-bold border", TF_COLOR[tf] ?? "bg-white/10 text-white/60 border-white/20")}>
      {TF_LABEL[tf] ?? tf}
    </span>
  );
}

function DirBadge({ dir }: { dir: string }) {
  if (dir === "bullish")
    return <span className="inline-flex items-center gap-0.5 text-emerald-400 text-[11px] font-semibold"><TrendingUp className="size-3" /> Bull</span>;
  if (dir === "bearish")
    return <span className="inline-flex items-center gap-0.5 text-red-400 text-[11px] font-semibold"><TrendingDown className="size-3" /> Bear</span>;
  return <span className="inline-flex items-center gap-0.5 text-yellow-400 text-[11px] font-semibold"><Minus className="size-3" /> Range</span>;
}

function ScorePill({ score }: { score: number }) {
  const cls =
    score >= 80 ? "bg-emerald-500/20 text-emerald-300 border-emerald-500/40" :
    score >= 65 ? "bg-yellow-500/20 text-yellow-300 border-yellow-500/40" :
                  "bg-white/10 text-white/50 border-white/20";
  return (
    <HelpTip tip="Confluence Score (0–100): Trend/Structure (30) + Momentum (25) + Volume (15) + Candle Trigger (25) + Structural Bonus (5). Only setups ≥65 are shown.">
      <span className={cn("inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-bold border", cls)}>
        {score}
      </span>
    </HelpTip>
  );
}

const BREAKOUT_STATE_CLS: Record<string, string> = {
  FRESH_BREAKOUT:      "bg-teal-500/20 border-teal-500/40 text-teal-300",
  CONFIRMED_BREAKOUT:  "bg-emerald-500/20 border-emerald-500/40 text-emerald-300",
  VERGE_BREAKOUT:      "bg-yellow-500/20 border-yellow-500/40 text-yellow-300",
  EXTENDED:            "bg-slate-500/20 border-slate-500/30 text-slate-400",
  FRESH_BREAKDOWN:     "bg-red-500/20 border-red-500/40 text-red-300",
  CONFIRMED_BREAKDOWN: "bg-rose-700/20 border-rose-700/40 text-rose-300",
  VERGE_BREAKDOWN:     "bg-yellow-500/20 border-yellow-500/40 text-yellow-300",
};

function BreakoutBadge({ state, label }: { state?: string; label?: string }) {
  if (!state || !label) return null;
  const cls = BREAKOUT_STATE_CLS[state];
  if (!cls) return null;
  return (
    <span className={cn("inline-flex items-center px-2 py-0.5 rounded text-[10px] font-semibold border", cls)}>
      {label}
    </span>
  );
}

function ActionPill({ plan }: { plan: OptionPlan }) {
  const isBuy = plan.action === "BUY";
  return (
    <span className={cn(
      "inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-bold border",
      isBuy
        ? "bg-blue-500/20 border-blue-500/40 text-blue-300"
        : "bg-orange-500/20 border-orange-500/40 text-orange-300",
    )}>
      {plan.action} {plan.option_type} {fmt(plan.strike)}
    </span>
  );
}

function BacktestTag({ bt }: { bt: BacktestInfo }) {
  if (bt.hit_rate === null)
    return <span className="text-[10px] text-white/30">low sample</span>;
  const pct = Math.round(bt.hit_rate * 100);
  return (
    <span className={cn("text-[10px] font-medium", pct >= 55 ? "text-emerald-400" : "text-white/40")}>
      {pct}% ({bt.sample_size})
    </span>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Summary strip (like equity dashboard indices row)
// ─────────────────────────────────────────────────────────────────────────────

function SummaryStrip({ summary, scanAt }: { summary: ScanSummary; scanAt: string }) {
  const chips = [
    { label: "Scanned",   value: summary.total_symbols,  sub: "symbols",       color: "text-white" },
    { label: "Setups",    value: summary.total_setups,   sub: "found",         color: "text-yellow-300" },
    { label: "Bullish",   value: summary.bullish,        sub: "↑",             color: "text-emerald-400" },
    { label: "Bearish",   value: summary.bearish,        sub: "↓",             color: "text-red-400" },
    { label: "Strong 80+", value: summary.strong_80plus, sub: "high-conf",    color: "text-emerald-300" },
  ];

  const tfChips = Object.entries(summary.by_timeframe).filter(([, v]) => v > 0);

  return (
    <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4 space-y-3">
      {/* KPI row */}
      <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
        {chips.map((c) => (
          <div key={c.label} className="flex flex-col gap-0.5 p-3 rounded-lg bg-[var(--color-surface-2)]">
            <span className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)]">{c.label}</span>
            <span className={cn("text-2xl font-bold", c.color)}>{c.value}</span>
            <span className="text-[10px] text-[var(--color-text-muted)]">{c.sub}</span>
          </div>
        ))}
      </div>

      {/* TF breakdown + scan time */}
      <div className="flex items-center flex-wrap gap-2 text-[12px]">
        <span className="text-[var(--color-text-muted)]">By timeframe:</span>
        {tfChips.length === 0
          ? <span className="text-white/30">—</span>
          : tfChips.map(([tf, count]) => (
            <span key={tf} className="flex items-center gap-1">
              <TfBadge tf={tf} />
              <span className="text-white/70">{count}</span>
            </span>
          ))
        }
        <span className="ml-auto text-[var(--color-text-muted)]">Scanned at {scanAt}</span>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Grouping helper
// ─────────────────────────────────────────────────────────────────────────────

interface SymbolGroup {
  symbol:    string;
  best:      SetupCard;    // highest-score card
  cards:     SetupCard[];  // all TFs, sorted best → worst
}

function groupBySymbol(cards: SetupCard[]): SymbolGroup[] {
  const map = new Map<string, SetupCard[]>();
  for (const c of cards) {
    const arr = map.get(c.symbol) ?? [];
    arr.push(c);
    map.set(c.symbol, arr);
  }
  return Array.from(map.entries()).map(([symbol, arr]) => {
    const sorted = [...arr].sort((a, b) => b.confluence_score - a.confluence_score);
    return { symbol, best: sorted[0], cards: sorted };
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// Per-TF expanded section: chart + plan + score breakdown
// ─────────────────────────────────────────────────────────────────────────────

import { CandleChart }       from "@/components/scanner/CandleChart";
import { PaperTradeModal }   from "@/components/scanner/PaperTradeModal";

function TfSection({ card }: { card: SetupCard }) {
  const { plan, score_breakdown: sb } = card;
  const [showPT, setShowPT] = useState(false);
  return (
    <div className="rounded-xl border border-white/10 bg-[var(--color-surface)] overflow-hidden">
      {/* TF header bar */}
      <div className="flex items-center gap-3 px-4 py-2.5 bg-white/5 border-b border-white/10">
        <TfBadge tf={card.timeframe} />
        <DirBadge dir={card.direction} />
        {card.pattern !== "None" && (
          <span className="text-yellow-300/80 text-[12px] font-medium">{card.pattern}</span>
        )}
        <ScorePill score={card.confluence_score} />
        <BreakoutBadge state={card.breakout_state} label={card.breakout_label} />
        {card.backtest && <BacktestTag bt={card.backtest} />}
        {plan && (
          <span className="ml-auto">
            <ActionPill plan={plan} />
          </span>
        )}
      </div>

      {/* ── CHART — full width ──────────────────────────────────────────────── */}
      <div className="px-3 pt-3 pb-1 border-b border-white/10">
        <p className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)] mb-2">
          {card.symbol} · {TF_LABEL[card.timeframe] ?? card.timeframe} chart
          {card.pattern !== "None" && (
            <span className="ml-2 text-yellow-400/80">▲ {card.pattern} highlighted</span>
          )}
        </p>
        <CandleChart
          symbol={card.symbol}
          interval={card.timeframe}
          pattern={card.pattern}
          direction={card.direction}
          height={360}
          bars={120}
        />
        {/* Reason tags */}
        <div className="flex flex-wrap gap-1 mt-2 pb-1">
          {card.reasons.map((r) => (
            <span key={r} className="px-1.5 py-0.5 rounded text-[10px] bg-white/5 border border-white/10 text-white/50">{r}</span>
          ))}
        </div>
      </div>

      {/* ── SCORE + PLAN — side by side below the chart ────────────────────── */}
      <div className="grid sm:grid-cols-2 gap-0 divide-x divide-white/10">

        {/* Score breakdown */}
        <div className="p-3">
          <p className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)] mb-2.5">Score breakdown</p>
          {[
            { label: "Trend",      val: sb.trend,                  max: 30, color: "bg-blue-500"   },
            { label: "Momentum",   val: sb.momentum,               max: 25, color: "bg-purple-500" },
            { label: "Volume",     val: sb.volume,                 max: 15, color: "bg-orange-500" },
            { label: "Candle",     val: sb.candle,                 max: 25, color: "bg-pink-500"   },
            { label: "Structural", val: sb.structural ?? 0,        max: 5,  color: "bg-green-500"  },
          ].map((r) => (
            <div key={r.label} className="flex items-center gap-2 text-[11px] mb-1.5">
              <span className="w-20 text-[var(--color-text-muted)] shrink-0">{r.label}</span>
              <div className="flex-1 h-1.5 rounded-full bg-white/10 overflow-hidden">
                <div className={cn("h-full rounded-full", r.color)} style={{ width: `${Math.round(r.val / r.max * 100)}%` }} />
              </div>
              <span className="w-10 text-right text-white/50">{r.val}/{r.max}</span>
            </div>
          ))}
        </div>

        {/* Option plan */}
        <div className="p-3 space-y-2.5">
          {plan ? (
            <>
              <div className="grid grid-cols-3 gap-1.5 text-[11px]">
                {[
                  { label: "Entry", val: fmt(plan.entry_spot, 0), sub: `Prem ₹${fmt(plan.entry_premium, 0)}`, cls: "text-white"         },
                  { label: "Stop",  val: fmt(plan.sl_spot, 0),    sub: `Prem ₹${fmt(plan.sl_premium, 0)}`,   cls: "text-red-400"       },
                  { label: "T1",    val: fmt(plan.t1_spot, 0),    sub: `Prem ₹${fmt(plan.t1_premium, 0)}`,   cls: "text-emerald-400"   },
                ].map((item) => (
                  <div key={item.label} className="p-2 rounded bg-white/5 border border-white/10 text-center">
                    <div className="text-[var(--color-text-muted)] text-[10px] mb-0.5">{item.label}</div>
                    <div className={cn("font-bold text-sm", item.cls)}>₹{item.val}</div>
                    <div className="text-[10px] text-[var(--color-text-muted)]">{item.sub}</div>
                  </div>
                ))}
              </div>

              <div className="text-[11px] text-white/40 px-0.5">
                T2 ₹{fmt(plan.t2_spot, 0)}
                {" · "}R:R <span className="text-white/70 font-medium">{plan.rr.toFixed(1)}</span>
                {" · "}Risk ₹{fmt(plan.raw_risk_pts, 0)}/unit
                {" · "}Lot {plan.lot_size}
              </div>

              <div className="flex items-start gap-1.5 text-[11px] text-white/40">
                <Clock className="size-3.5 mt-0.5 text-blue-400 shrink-0" />
                <span className="leading-relaxed">{plan.exit_rule}</span>
              </div>

              {plan.iv_note && (
                <div className="flex gap-1.5 text-[11px] text-yellow-300/60">
                  <AlertTriangle className="size-3.5 mt-0.5 shrink-0" />
                  <span>{plan.iv_note}</span>
                </div>
              )}

              <div className="flex items-center justify-between gap-3 pt-1 border-t border-white/10">
                <div className="text-[11px] text-[var(--color-text-muted)] flex flex-wrap gap-x-3 gap-y-0.5">
                  <span>Lot: <span className="text-white font-medium">{plan.lot_size.toLocaleString("en-IN")}</span></span>
                  <span>1 lot cost: <span className="text-white font-medium">₹{fmt(plan.entry_premium * plan.lot_size, 0)}</span></span>
                  <span>Max risk/lot: <span className="text-red-400 font-medium">₹{fmt((plan.entry_premium - plan.sl_premium) * plan.lot_size, 0)}</span></span>
                </div>
                <button
                  onClick={() => setShowPT(true)}
                  className="shrink-0 flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[var(--color-primary)]/20 border border-[var(--color-primary)]/40 text-[var(--color-primary)] text-[11px] font-semibold hover:bg-[var(--color-primary)]/30 transition-colors"
                >
                  + Paper Trade
                </button>
              </div>
            </>
          ) : (
            <div className="flex items-center gap-2 text-[11px] text-white/25 p-2 rounded bg-white/5 border border-white/10">
              <Info className="size-3.5 shrink-0" />
              Option plan unavailable
            </div>
          )}
        </div>
      </div>

      {/* Paper trade modal */}
      {showPT && plan && (
        <PaperTradeModal
          setup={{
            symbol:          card.symbol,
            option_type:     plan.option_type,
            strike:          plan.strike,
            expiry:          plan.expiry,
            action:          plan.action,
            entry_premium:   plan.entry_premium,
            sl_premium:      plan.sl_premium,
            t1_premium:      plan.t1_premium,
            t2_premium:      plan.t2_premium,
            lot_size:        plan.lot_size,
            rr:              plan.rr,
            exit_rule:       plan.exit_rule,
            direction:       card.direction,
            timeframe:       card.timeframe,
            confluence_score: card.confluence_score,
          }}
          onClose={() => setShowPT(false)}
        />
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Grouped table row — one row per symbol, all TFs collapsed inside
// ─────────────────────────────────────────────────────────────────────────────

function GroupRow({ group, idx }: { group: SymbolGroup; idx: number }) {
  const [open, setOpen] = useState(false);
  const { best } = group;
  const plan = best.plan;

  return (
    <>
      <tr
        onClick={() => setOpen((v) => !v)}
        className={cn(
          "cursor-pointer transition-colors border-b border-white/5",
          open ? "bg-[var(--color-surface-2)]" : "hover:bg-white/5",
        )}
      >
        <td className="px-3 py-3 w-6">
          {open
            ? <ChevronDown className="size-3.5 text-white/40" />
            : <ChevronRight className="size-3.5 text-white/30" />}
        </td>
        <td className="px-2 py-3 text-[11px] text-white/30 w-8">{idx + 1}</td>

        {/* Symbol + all TF badges */}
        <td className="px-3 py-3">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-semibold text-white text-[13px]">{group.symbol}</span>
            {group.cards.map((c) => (
              <TfBadge key={c.timeframe} tf={c.timeframe} />
            ))}
          </div>
        </td>

        <td className="px-2 py-3"><DirBadge dir={best.direction} /></td>

        {/* Pattern — show all unique patterns */}
        <td className="px-3 py-3 text-[12px]">
          {Array.from(new Set(group.cards.map((c) => c.pattern).filter((p) => p !== "None"))).length > 0 ? (
            <span className="text-yellow-300/80 font-medium">
              {Array.from(new Set(group.cards.map((c) => c.pattern).filter((p) => p !== "None"))).join(" · ")}
            </span>
          ) : <span className="text-white/20">—</span>}
        </td>

        <td className="px-2 py-3">
          <div className="flex items-center gap-1.5 flex-wrap">
            <ScorePill score={best.confluence_score} />
            <BreakoutBadge state={best.breakout_state} label={best.breakout_label} />
          </div>
        </td>

        <td className="px-2 py-3">
          {plan ? <ActionPill plan={plan} /> : <span className="text-white/20 text-[11px]">—</span>}
        </td>

        <td className="px-3 py-3 text-[11px] text-right font-mono">
          {plan ? (
            <div className="flex flex-col items-end gap-0.5">
              <span className="text-white">₹{fmt(plan.entry_spot, 0)}</span>
              <span className="text-red-400">SL {fmt(plan.sl_spot, 0)}</span>
            </div>
          ) : <span className="text-white/50">₹{fmt(best.trigger_price, 0)}</span>}
        </td>

        <td className="px-3 py-3 text-[11px] text-right font-mono">
          {plan ? (
            <div className="flex flex-col items-end gap-0.5">
              <span className="text-emerald-400">T1 {fmt(plan.t1_spot, 0)}</span>
              <span className="text-white/50">R:R {plan.rr.toFixed(1)}</span>
            </div>
          ) : <span className="text-white/20">—</span>}
        </td>

        <td className="px-3 py-3 text-right">
          {best.backtest ? <BacktestTag bt={best.backtest} /> : <span className="text-[10px] text-white/20">—</span>}
        </td>
      </tr>

      {/* Expanded: one TfSection per timeframe */}
      {open && (
        <tr>
          <td colSpan={10} className="px-4 pb-5 pt-3 bg-[var(--color-surface-2)]/40">
            <div className="space-y-4">
              {group.cards.map((c) => (
                <TfSection key={c.timeframe} card={c} />
              ))}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Controls
// ─────────────────────────────────────────────────────────────────────────────

const UNIVERSES = [
  { value: "indices", label: "Indices — NIFTY · BANKNIFTY · FINNIFTY · SENSEX" },
  { value: "stocks",  label: "F&O Stocks — all NSE F&O eligible equities" },
];

function Sel({ value, options, onChange, wide }: {
  value: string;
  options: { value: string; label: string }[];
  onChange: (v: string) => void;
  wide?: boolean;
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className={cn(
        "bg-[var(--color-surface-2)] border border-[var(--color-border)] text-white text-[13px] rounded-lg px-4 py-2.5 focus:outline-none focus:ring-1 focus:ring-[var(--color-primary)]",
        wide ? "w-72" : "w-44",
      )}
    >
      {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Scan progress panel (shown while scanning — like equity scanner)
// ─────────────────────────────────────────────────────────────────────────────

// ─────────────────────────────────────────────────────────────────────────────
// Real progress panel (driven by SSE events — same as equity scanner)
// ─────────────────────────────────────────────────────────────────────────────

function ScanProgress({
  progress, onCancel,
}: {
  progress: ScanProgressState;
  onCancel: () => void;
}) {
  const [elapsed, setElapsed] = useState(0);
  const [log,     setLog]     = useState<string[]>([]);
  const startRef = useRef(Date.now());

  // Accumulate per-symbol activity log
  useEffect(() => {
    if (!progress.currentSym) return;
    const found = progress.setupsSoFar;
    const entry = `${progress.done}/${progress.total}  ${progress.currentSym.padEnd(14)}  ${
      progress.found > 0 ? `✓ ${progress.found} setup${progress.found > 1 ? "s" : ""}` : "—"
    }`;
    setLog((prev) => [...prev.slice(-7), entry]);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [progress.currentSym]);

  useEffect(() => {
    const id = setInterval(() =>
      setElapsed(Math.floor((Date.now() - startRef.current) / 1000)), 1000);
    return () => clearInterval(id);
  }, []);

  const pct = progress.enriching
    ? 94
    : progress.total > 0
    ? Math.min(88, Math.round((progress.done / progress.total) * 88))
    : 2;

  return (
    <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5 space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <RefreshCw className="size-4 text-[var(--color-primary)] animate-spin" />
          <span className="font-semibold text-white">
            {progress.enriching ? "Building option plans & backtests…" : "Scanning all timeframes…"}
          </span>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-[12px] text-[var(--color-text-muted)]">{elapsed}s</span>
          <button
            onClick={onCancel}
            className="text-[11px] text-[var(--color-text-muted)] hover:text-red-400 border border-white/10 hover:border-red-400/40 px-2 py-0.5 rounded transition-colors"
          >
            Cancel
          </button>
        </div>
      </div>

      {/* Progress bar */}
      <div className="space-y-1.5">
        <div className="flex justify-between text-[12px]">
          <span className="text-[var(--color-text-muted)]">
            {progress.enriching
              ? `Building plans for ${progress.setupsSoFar} setups…`
              : progress.total > 0
              ? <><span className="text-white font-semibold">{progress.done}</span> / {progress.total} symbols scanned</>
              : "Connecting to backend…"}
          </span>
          {progress.setupsSoFar > 0 && !progress.enriching && (
            <span className="text-yellow-400 font-medium">
              {progress.setupsSoFar} setup{progress.setupsSoFar !== 1 ? "s" : ""} found so far
            </span>
          )}
        </div>
        <div className="h-2 rounded-full bg-white/10 overflow-hidden">
          <div
            className="h-full rounded-full bg-[var(--color-primary)] transition-all duration-500 ease-out"
            style={{ width: `${pct}%` }}
          />
        </div>
        <div className="flex justify-between text-[10px] text-[var(--color-text-muted)]">
          <span>5 min · 15 min · 30 min · 1 hr · 4 hr · Daily · Weekly · Monthly</span>
          <span>{pct}%</span>
        </div>
      </div>

      {/* Live scan log — shows last 8 processed symbols */}
      {log.length > 0 && (
        <div className="rounded-lg bg-black/30 border border-white/10 p-3 font-mono text-[11px] space-y-0.5">
          {log.map((entry, i) => (
            <div
              key={i}
              className={cn(
                i === log.length - 1 ? "text-white" : "text-white/30",
              )}
            >
              {entry}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Page
// ─────────────────────────────────────────────────────────────────────────────

export default function LiveScannerPage() {
  const [params, setParams] = useState<ScanParams>({ universe: "stocks", threshold: 65 });
  const [loading,    setLoading]    = useState(false);
  const [progress,   setProgress]   = useState<ScanProgressState>({ done: 0, total: 0, currentSym: "", found: 0, setupsSoFar: 0, enriching: false });
  const [result,     setResult]     = useState<ScanResponse | null>(null);
  const [error,      setError]      = useState<string | null>(null);
  const [scanAt,     setScanAt]     = useState<string | null>(null);
  const [backendOk,  setBackendOk]  = useState<boolean | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  // Post-scan display filter (direction can't be known until after scoring)
  const [filterDir,         setFilterDir]         = useState<string>("all");

  // Pre-scan scan configuration — sent with the scan request itself
  const [selectedTimeframes,   setSelectedTimeframes]   = useState<Set<string>>(new Set(ALL_TFS));
  const [selectedPatternNames, setSelectedPatternNames] = useState<Set<string>>(new Set());
  const [patternsOpen,      setPatternsOpen]      = useState(false);
  const [expandedFamilies,  setExpandedFamilies]  = useState<Set<string>>(new Set());

  const patternQuery = useQuery<Record<string, { name: string; direction: string; tier: number }[]>>({
    queryKey: ["live-scanner-patterns"],
    queryFn:  () => fetch("/api/live-scanner/patterns").then((r) => r.json()),
    staleTime: Infinity,
  });
  const patternGroups = patternQuery.data ?? {};

  // Poll health every 10s to show backend status
  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      if (cancelled) return;
      const ok = await checkHealth();
      if (!cancelled) setBackendOk(ok);
      if (!cancelled) setTimeout(poll, 10_000);
    };
    poll();
    return () => { cancelled = true; };
  }, []);

  const cancel = useCallback(() => {
    abortRef.current?.abort();
    setLoading(false);
  }, []);

  const scan = useCallback(async () => {
    setLoading(true); setError(null);
    setProgress({ done: 0, total: 0, currentSym: "", found: 0, setupsSoFar: 0, enriching: false });

    const healthy = await checkHealth();
    setBackendOk(healthy);
    if (!healthy) {
      setError("Backend not running. Start it with: python -m uvicorn backend.main:app --port 8000 --reload");
      setLoading(false);
      return;
    }

    const ctl = new AbortController();
    abortRef.current = ctl;

    const scanParams: ScanParams = {
      ...params,
      timeframes: selectedTimeframes.size < ALL_TFS.length
        ? Array.from(selectedTimeframes).join(",")
        : undefined,
      pattern_names: selectedPatternNames.size > 0
        ? Array.from(selectedPatternNames).join(",")
        : undefined,
    };

    await streamScan(scanParams, {
      onProgress: (p) => setProgress(p),
      onResult:   (data) => {
        setResult(data);
        setBackendOk(true);
        setScanAt(new Date().toLocaleTimeString("en-IN", { hour12: false }));
        setFilterDir("all");
      },
      onDone:  () => setLoading(false),
      onError: (msg) => {
        setError(msg);
        if (msg.includes("500") || msg.includes("fetch")) setBackendOk(false);
        setLoading(false);
      },
      signal: ctl.signal,
    });
  }, [params, selectedTimeframes, selectedPatternNames]);

  const upd = (k: keyof ScanParams) => (v: string | number) =>
    setParams((p) => ({ ...p, [k]: v }));

  // Direction is the only remaining post-scan display filter — timeframe and
  // pattern selection are now scan-time configuration (see scanParams above),
  // so results are already scoped/scored to them by the time they arrive here.
  const visible = (result?.setups ?? []).filter((c) => {
    if (filterDir !== "all" && c.direction !== filterDir) return false;
    return true;
  });

  return (
    <div className="p-6 max-w-[1400px] mx-auto space-y-5">

      {/* ── Header ─────────────────────────────────────────────────────── */}
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <div className="flex items-center gap-2">
            <Zap className="size-5 text-yellow-400" />
            <h1 className="text-xl font-bold text-white">F&O Live Scanner</h1>
            {/* Backend health indicator */}
            <span className={cn(
              "flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[10px] font-medium border",
              backendOk === null
                ? "bg-white/5 border-white/10 text-white/30"
                : backendOk
                ? "bg-emerald-500/15 border-emerald-500/30 text-emerald-400"
                : "bg-red-500/15 border-red-500/30 text-red-400",
            )}>
              <span className={cn(
                "size-1.5 rounded-full",
                backendOk === null ? "bg-white/30" :
                backendOk ? "bg-emerald-400 animate-pulse" : "bg-red-400",
              )} />
              {backendOk === null ? "checking…" : backendOk ? "Backend online" : "Backend offline"}
            </span>
          </div>
          <p className="text-[12px] text-[var(--color-text-muted)] mt-0.5">
            Scans 5 min · 15 min · 30 min · 1 hr · 4 hr · Daily · Weekly · Monthly simultaneously — surfaces actionable option setups.
          </p>
        </div>
        {scanAt && (
          <span className="text-[11px] text-[var(--color-text-muted)]">Last scan: {scanAt}</span>
        )}
      </div>

      {/* ── Controls ───────────────────────────────────────────────────── */}
      <div className="rounded-xl bg-[var(--color-surface)] border border-[var(--color-border)] p-5 space-y-5">
        {/* Primary controls row */}
        <div className="flex flex-wrap items-end gap-5">
          <div className="flex flex-col gap-2 flex-1 min-w-[220px]">
            <label className="text-[11px] uppercase tracking-wider text-[var(--color-text-muted)]">Universe</label>
            <Sel value={params.universe} options={UNIVERSES} onChange={upd("universe")} wide />
            <p className="text-[11px] text-[var(--color-text-muted)]">
              {params.universe === "indices" && "NIFTY · BANKNIFTY · FINNIFTY · SENSEX — intraday focus, ~5s"}
              {params.universe === "stocks"  && "All NSE F&O eligible equities from NSE — positional + intraday, ~30-65s"}
            </p>
          </div>

          <div className="flex flex-col gap-2">
            <label className="text-[11px] uppercase tracking-wider text-[var(--color-text-muted)]">
              Min confluence score
            </label>
            <div className="flex items-center gap-3">
              <input
                type="range" min={40} max={90} step={5} value={params.threshold}
                onChange={(e) => upd("threshold")(Number(e.target.value))}
                className="w-40 accent-[var(--color-primary)]"
              />
              <span className="text-xl font-bold text-white w-8">{params.threshold}</span>
            </div>
            <p className="text-[11px] text-[var(--color-text-muted)]">
              {params.threshold >= 80 ? "Strong signals only" :
               params.threshold >= 65 ? "Recommended — balanced quality" :
               "Relaxed — shows more, lower quality"}
            </p>
          </div>

          <button
            onClick={scan}
            disabled={loading}
            className={cn(
              "flex items-center gap-2 px-8 py-3 rounded-lg font-semibold text-[14px] transition-all self-end",
              loading
                ? "bg-[var(--color-primary)]/50 cursor-not-allowed text-white/50"
                : "bg-[var(--color-primary)] hover:opacity-90 text-white shadow-lg",
            )}
          >
            <RefreshCw className={cn("size-4", loading && "animate-spin")} />
            {loading ? "Scanning…" : "Run Scan"}
          </button>
        </div>

        {/* Timeframes — pre-scan selection; unselected TFs are never fetched */}
        <div className="pt-3 border-t border-[var(--color-border)]">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[11px] uppercase tracking-wider text-[var(--color-text-muted)] shrink-0">
              Timeframes
            </span>
            <span className="text-[11px] text-[var(--color-text-muted)]">
              {selectedTimeframes.size === ALL_TFS.length
                ? "— all 8 (no filter)"
                : `${selectedTimeframes.size} selected`}
            </span>
            <button
              onClick={() => setSelectedTimeframes(new Set(ALL_TFS))}
              className="text-[10px] text-[var(--color-text-muted)] hover:text-white underline underline-offset-2"
            >
              All
            </button>
            <button
              onClick={() => setSelectedTimeframes(new Set())}
              className="text-[10px] text-[var(--color-text-muted)] hover:text-white underline underline-offset-2"
            >
              None
            </button>
            <div className="flex flex-wrap gap-1.5 ml-2">
              {ALL_TFS.map((tf) => {
                const active = selectedTimeframes.has(tf);
                return (
                  <button
                    key={tf}
                    onClick={() => {
                      setSelectedTimeframes((prev) => {
                        const next = new Set(prev);
                        if (next.has(tf)) next.delete(tf); else next.add(tf);
                        return next;
                      });
                    }}
                    className={cn(
                      "px-2.5 py-0.5 rounded-full text-[11px] font-medium border transition-all",
                      active
                        ? TF_COLOR[tf] ?? "bg-white/10 text-white border-white/30"
                        : "border-white/10 text-white/35 bg-transparent hover:text-white/55 hover:border-white/20",
                    )}
                  >
                    {TF_LABEL[tf]}
                  </button>
                );
              })}
            </div>
          </div>
          {selectedTimeframes.size === 0 && (
            <p className="text-[11px] text-yellow-400/70 mt-2 flex items-center gap-1">
              <AlertTriangle className="size-3 shrink-0" /> Select at least one timeframe to scan.
            </p>
          )}
        </div>

        {/* Filter row — only shown after scan completes (direction can't be known pre-scan) */}
        {result && !loading && (
          <div className="flex flex-wrap items-end gap-4 pt-3 border-t border-[var(--color-border)]">
            <span className="text-[11px] text-[var(--color-text-muted)] self-center">Filter results:</span>
            <div className="flex flex-col gap-1">
              <label className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)]">Direction</label>
              <Sel
                value={filterDir}
                options={[
                  { value: "all",     label: "All directions" },
                  { value: "bullish", label: "↑ Bullish only" },
                  { value: "bearish", label: "↓ Bearish only" },
                  { value: "range",   label: "→ Range only" },
                ]}
                onChange={setFilterDir}
              />
            </div>
            <span className="text-[12px] text-[var(--color-text-muted)] self-end ml-auto">
              Showing <span className="text-white font-medium">{groupBySymbol(visible).length}</span> symbols
              {" · "}<span className="text-white font-medium">{visible.length}</span> setups
              {visible.length < result.summary.total_setups && (
                <> of <span className="text-white font-medium">{result.summary.total_setups}</span></>
              )}
            </span>
          </div>
        )}

        {/* Pattern selector — collapsible, two-level: section + per-family. Pre-scan:
            selected patterns are sent with the scan and shape each setup's score
            (Candle Trigger / Structural bonus), not just a post-scan display filter. */}
        <div className="pt-3 border-t border-[var(--color-border)]">
            <div
              role="button"
              tabIndex={0}
              onClick={() => setPatternsOpen((v) => !v)}
              onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setPatternsOpen((v) => !v); } }}
              className="flex items-center gap-2 w-full text-left group cursor-pointer"
            >
              <ChevronDown className={cn(
                "size-3.5 text-white/40 transition-transform duration-150 shrink-0",
                !patternsOpen && "-rotate-90",
              )} />
              <span className="text-[11px] uppercase tracking-wider text-[var(--color-text-muted)] group-hover:text-white/70 transition-colors">
                Patterns
              </span>
              {selectedPatternNames.size > 0 ? (
                <span className="text-[11px] text-[var(--color-primary)] font-medium">
                  {selectedPatternNames.size} selected
                </span>
              ) : (
                <span className="text-[11px] text-[var(--color-text-muted)]">— all patterns (no filter)</span>
              )}
              {selectedPatternNames.size > 0 && (
                <button
                  onClick={(e) => { e.stopPropagation(); setSelectedPatternNames(new Set()); }}
                  className="ml-auto text-[10px] text-[var(--color-text-muted)] hover:text-white underline underline-offset-2"
                >
                  Clear all
                </button>
              )}
            </div>

            {patternsOpen && (
              <div className="mt-3 space-y-2">
                {patternQuery.isLoading && (
                  <p className="text-[11px] text-[var(--color-text-muted)]">Loading patterns…</p>
                )}

                {Object.entries(patternGroups).map(([family, patterns]) => {
                  const meta     = FAMILY_META[family] ?? { label: family, active: "text-white border-white/30 bg-white/10", muted: "text-white/60" };
                  const famPats  = patterns.map((p) => p.name);
                  const allSel   = famPats.every((n) => selectedPatternNames.has(n));
                  const famOpen  = expandedFamilies.has(family);
                  const selCount = famPats.filter((n) => selectedPatternNames.has(n)).length;

                  const toggleFamily = () =>
                    setExpandedFamilies((prev) => {
                      const next = new Set(prev);
                      if (next.has(family)) next.delete(family); else next.add(family);
                      return next;
                    });

                  const toggleAll = (e: React.MouseEvent) => {
                    e.stopPropagation();
                    setSelectedPatternNames((prev) => {
                      const next = new Set(prev);
                      if (allSel) famPats.forEach((n) => next.delete(n));
                      else        famPats.forEach((n) => next.add(n));
                      return next;
                    });
                  };

                  return (
                    <div key={family} className="rounded-lg border border-white/6 bg-white/2 overflow-hidden">
                      <div
                        role="button"
                        tabIndex={0}
                        onClick={toggleFamily}
                        onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggleFamily(); } }}
                        className="flex items-center gap-2 w-full px-3 py-2 text-left hover:bg-white/5 transition-colors cursor-pointer"
                      >
                        <ChevronDown className={cn(
                          "size-3 text-white/30 transition-transform duration-150 shrink-0",
                          !famOpen && "-rotate-90",
                        )} />
                        <span className={cn("text-[10px] font-semibold uppercase tracking-wider", meta.muted)}>
                          {meta.label}
                        </span>
                        <span className="text-[9px] text-white/20">({patterns.length})</span>
                        {selCount > 0 && (
                          <span className={cn("text-[9px] font-medium ml-1", meta.muted)}>
                            {selCount} selected
                          </span>
                        )}
                        {famOpen && (
                          <button
                            onClick={toggleAll}
                            className="ml-auto text-[9px] text-[var(--color-text-muted)] hover:text-white underline underline-offset-2"
                          >
                            {allSel ? "Deselect all" : "Select all"}
                          </button>
                        )}
                      </div>

                      {famOpen && (
                        <div className="flex flex-wrap gap-1.5 px-3 pb-3 pt-1">
                          {patterns.map((p) => {
                            const active = selectedPatternNames.has(p.name);
                            return (
                              <button
                                key={p.name}
                                onClick={() => {
                                  setSelectedPatternNames((prev) => {
                                    const next = new Set(prev);
                                    if (next.has(p.name)) next.delete(p.name);
                                    else next.add(p.name);
                                    return next;
                                  });
                                }}
                                className={cn(
                                  "px-2.5 py-0.5 rounded-full text-[11px] font-medium border transition-all",
                                  active
                                    ? meta.active
                                    : "border-white/10 text-white/35 bg-transparent hover:text-white/55 hover:border-white/20",
                                )}
                              >
                                {p.name}
                              </button>
                            );
                          })}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
      </div>

      {/* ── Error ──────────────────────────────────────────────────────── */}
      {error && !loading && (
        <div className="flex items-start gap-3 p-4 rounded-xl bg-red-500/10 border border-red-500/30 text-red-300 text-[13px]">
          <AlertTriangle className="size-4 mt-0.5 shrink-0" />
          <div className="flex-1 space-y-1">
            <p className="font-semibold">
              {backendOk === false ? "Backend not running" : "Scan error"}
            </p>
            <p className="text-[12px] opacity-80">{error}</p>
            {backendOk === false && (
              <div className="mt-2 p-2 rounded bg-black/20 text-[11px] opacity-70 font-mono">
                python -m uvicorn backend.main:app --port 8000 --reload
              </div>
            )}
            <button
              onClick={scan}
              className="mt-1 inline-flex items-center gap-1.5 text-[11px] underline underline-offset-2 opacity-70 hover:opacity-100"
            >
              <RefreshCw className="size-3" /> Retry scan
            </button>
          </div>
        </div>
      )}

      {/* ── Scan progress (real SSE-driven) ─────────────────────────────── */}
      {loading && <ScanProgress progress={progress} onCancel={cancel} />}

      {/* ── Results ────────────────────────────────────────────────────── */}
      {!loading && result && (
        <>
          {/* Summary strip */}
          <SummaryStrip summary={result.summary} scanAt={scanAt ?? ""} />

          {/* Table */}
          <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] overflow-hidden">
            {visible.length === 0 ? (
              <div className="text-center py-14 text-[var(--color-text-muted)]">
                <Activity className="size-10 mx-auto mb-3 opacity-20" />
                <p className="font-medium text-white/50">No setups match the current filters</p>
                <p className="text-[12px] mt-1">
                  Try lowering the min score or choosing a different direction / timeframe filter.
                </p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-[13px]">
                  <thead>
                    <tr className="border-b border-white/10 text-[10px] uppercase tracking-wider text-[var(--color-text-muted)]">
                      <th className="px-3 py-2 w-6"></th>
                      <th className="px-2 py-2 w-8">#</th>
                      <th className="px-3 py-2">Symbol · Timeframes</th>
                      <th className="px-2 py-2">Direction</th>
                      <th className="px-3 py-2">Pattern(s)</th>
                      <th className="px-2 py-2">Score</th>
                      <th className="px-2 py-2">Option Play</th>
                      <th className="px-3 py-2 text-right">Entry / SL</th>
                      <th className="px-3 py-2 text-right">T1 / R:R</th>
                      <th className="px-3 py-2 text-right">Backtest</th>
                    </tr>
                  </thead>
                  <tbody>
                    {groupBySymbol(visible).map((group, idx) => (
                      <GroupRow key={group.symbol} group={group} idx={idx} />
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* Disclaimer */}
          <p className="text-[11px] text-[var(--color-text-muted)] border-t border-[var(--color-border)] pt-3">
            {result.disclaimer}
          </p>
        </>
      )}

      {/* ── Empty state ─────────────────────────────────────────────────── */}
      {!loading && !result && !error && (
        <div className="text-center py-20 text-[var(--color-text-muted)]">
          <Zap className="size-12 mx-auto mb-4 opacity-20" />
          <p className="font-medium text-white/50">Choose a universe and hit Run Scan</p>
          <p className="text-[12px] mt-1 max-w-md mx-auto">
            The scanner checks 5 min, 15 min, 1 hr, and daily charts simultaneously.
            Each result shows the timeframe, pattern, confluence score, and a ready-to-use option plan.
          </p>
        </div>
      )}
    </div>
  );
}
