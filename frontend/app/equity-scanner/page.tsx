"use client";

import { useState, useCallback, useEffect, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { HelpTip } from "@/components/ui/tooltip";
import {
  TrendingUp, TrendingDown, Minus, RefreshCw, RefreshCcw,
  ChevronDown, ChevronRight, AlertTriangle,
  Activity, Clock, Info, BarChart2, Database,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useRegion } from "@/lib/region";
import { api } from "@/lib/api";
import type {
  EquitySetupCard, EquityScanResponse, EquityScanParams,
  EquityPlan, BacktestInfo, EquityScanSummary, ScanProgressState,
  PatternGroups, PatternMode,
} from "@/lib/equity-scanner-types";
import { CandleChart } from "@/components/scanner/CandleChart";
import { PatternPicker } from "@/components/scanner/PatternPicker";
import { WeightSlider } from "@/components/scanner/WeightSlider";
import {
  MultiSelectFilter, cardMatchesPatterns, patternOptionsFromCards,
  cardMatchesTimeframe, timeframeOptionsFromCards, displayPatternFor,
} from "@/components/scanner/MultiSelectFilter";
import { ScanQualityBanner } from "@/components/scanner/ScanQualityBanner";

// ─────────────────────────────────────────────────────────────────────────────
// Universe definitions — separated by market, grouped by category
// ─────────────────────────────────────────────────────────────────────────────

interface UniverseOption { value: string; label: string; desc: string; }
interface UniverseGroup  { group: string; options: UniverseOption[]; }

const INDIA_UNIVERSE_GROUPS: UniverseGroup[] = [
  {
    group: "Indices",
    options: [
      { value: "india_indices",  label: "NSE / BSE Indices",   desc: "NIFTY · BANKNIFTY · SENSEX · FINNIFTY · MIDCPNIFTY · BANKEX" },
    ],
  },
  {
    group: "Broad Market",
    options: [
      { value: "india_nifty50",     label: "Nifty 50",           desc: "50 large-cap blue-chips — ~60s"          },
      { value: "india_nifty100",    label: "Nifty 100",          desc: "Nifty 50 + Next 50 — ~2 min"             },
      { value: "india_nifty200",    label: "Nifty 200",          desc: "Top 200 NSE stocks — ~4 min"             },
      { value: "india_nifty500",    label: "Nifty 500",          desc: "Top 500 NSE stocks — ~10 min"            },
      { value: "india_midcap150",   label: "Nifty Midcap 150",   desc: "150 midcap stocks — ~3 min"              },
      { value: "india_smallcap250", label: "Nifty Smallcap 250", desc: "250 smallcap stocks — ~5 min"            },
    ],
  },
  {
    group: "Sectors",
    options: [
      { value: "india_bank",     label: "Nifty Bank",     desc: "14 banking stocks — HDFC · ICICI · SBIN · AXIS"   },
      { value: "india_it",       label: "Nifty IT",       desc: "10 IT stocks — TCS · INFY · HCLTECH · WIPRO"      },
      { value: "india_pharma",   label: "Nifty Pharma",   desc: "20 pharma stocks — SUNPHARMA · DRREDDY · CIPLA"   },
      { value: "india_auto",     label: "Nifty Auto",     desc: "15 auto stocks — MARUTI · TATAMOTORS · M&M"       },
      { value: "india_fmcg",     label: "Nifty FMCG",    desc: "15 FMCG stocks — HINDUNILVR · ITC · NESTLEIND"    },
      { value: "india_metal",    label: "Nifty Metal",    desc: "19 metal stocks — TATASTEEL · JSWSTEEL · VEDL"    },
      { value: "india_energy",   label: "Nifty Energy",   desc: "40 energy stocks — RELIANCE · ONGC · NTPC"        },
      { value: "india_infra",    label: "Nifty Infra",    desc: "30 infra stocks — LT · POWERGRID · NTPC"          },
      { value: "india_realty",   label: "Nifty Realty",   desc: "10 realty stocks — DLF · LODHA · GODREJPROP"      },
      { value: "india_psu_bank", label: "Nifty PSU Bank", desc: "12 PSU bank stocks — SBIN · PNB · BANKBARODA"     },
      { value: "india_media",    label: "Nifty Media",    desc: "10 media stocks — ZEEL · SUNTV · PVRINOX"         },
    ],
  },
  {
    group: "All Market",
    options: [
      { value: "all_nse", label: "All NSE Stocks", desc: "511 stocks from merged NIFTY files · click Refresh to load all ~1800 from NSE · 20+ min" },
    ],
  },
];

const US_UNIVERSE_GROUPS: UniverseGroup[] = [
  {
    group: "Indices",
    options: [
      { value: "us_indices", label: "US Major Indices", desc: "S&P 500 · NASDAQ 100 · Dow Jones · Russell 2000" },
    ],
  },
  {
    group: "Broad Market",
    options: [
      { value: "us_top30",     label: "US Top 30",    desc: "AAPL · MSFT · NVDA · GOOGL and 26 more — ~35s" },
      { value: "us_dow30",     label: "Dow Jones 30", desc: "30 DJIA stocks — ~35s"                          },
      { value: "us_nasdaq100", label: "NASDAQ 100",   desc: "101 NASDAQ large-caps — ~2 min"                 },
      { value: "us_sp100",     label: "S&P 100",      desc: "Top 100 S&P 500 by weight — ~2 min"             },
      { value: "us_sp500",     label: "S&P 500",      desc: "503 S&P 500 stocks — ~10 min"                   },
    ],
  },
  {
    group: "Sectors",
    options: [
      { value: "us_technology",      label: "Technology",       desc: "30 tech stocks — AAPL · MSFT · NVDA · GOOGL"  },
      { value: "us_financials",      label: "Financials",       desc: "30 financial stocks — JPM · BAC · GS · MS"     },
      { value: "us_healthcare",      label: "Healthcare",       desc: "30 healthcare stocks — UNH · LLY · JNJ · ABBV" },
      { value: "us_energy",          label: "Energy",           desc: "20 energy stocks — XOM · CVX · COP · SLB"      },
      { value: "us_consumer_disc",   label: "Consumer Discret.",desc: "20 stocks — AMZN · TSLA · HD · NKE"            },
      { value: "us_communication",   label: "Communication",    desc: "20 stocks — META · GOOGL · NFLX · DIS"         },
      { value: "us_industrials",     label: "Industrials",      desc: "20 stocks — CAT · HON · GE · BA"               },
      { value: "us_consumer_staples",label: "Consumer Staples", desc: "20 stocks — WMT · PG · KO · COST"              },
    ],
  },
  {
    group: "All Market",
    options: [
      { value: "all_us", label: "All US Listed (536)", desc: "S&P 500 + NASDAQ 100 + all US sectors, deduplicated — ~12 min" },
    ],
  },
];

// Flat lookup for selectedUniverse desc and default-universe resolution
const INDIA_UNIVERSES = INDIA_UNIVERSE_GROUPS.flatMap((g) => g.options);
const US_UNIVERSES    = US_UNIVERSE_GROUPS.flatMap((g) => g.options);

// Universes that need a Refresh from live source before the first scan
const REFRESH_UNIVERSES = new Set(["all_nse", "all_us"]);

// ─────────────────────────────────────────────────────────────────────────────
// Timeframe display (equity uses positional TFs)
// ─────────────────────────────────────────────────────────────────────────────

const TF_COLOR: Record<string, string> = {
  "1d":  "bg-teal-500/20 text-teal-300 border-teal-500/30",
  "1wk": "bg-blue-500/20 text-blue-300 border-blue-500/30",
  "1mo": "bg-purple-500/20 text-purple-300 border-purple-500/30",
};
const TF_LABEL: Record<string, string> = {
  "1d": "Daily", "1wk": "Weekly", "1mo": "Monthly",
};
const ALL_TFS = ["1d", "1wk", "1mo"] as const;

// ─────────────────────────────────────────────────────────────────────────────
// API — SSE streaming (direct to FastAPI)
// ─────────────────────────────────────────────────────────────────────────────

async function refreshUniverse(key: string): Promise<{ count: number; preview: string[] } | null> {
  try {
    const FASTAPI = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";
    const res = await fetch(`${FASTAPI}/api/equity-scanner/refresh-universe/${key}`, { method: "POST" });
    if (!res.ok) return null;
    return await res.json();
  } catch { return null; }
}

async function fetchUniverseCount(key: string): Promise<number> {
  try {
    const FASTAPI = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";
    const res = await fetch(`${FASTAPI}/api/equity-scanner/universe-count/${key}`, { signal: AbortSignal.timeout(5000) });
    if (!res.ok) return 0;
    const d = await res.json();
    return d.count ?? 0;
  } catch { return 0; }
}

async function checkHealth(): Promise<boolean> {
  try {
    const res = await fetch("/api/equity-scanner/health", { signal: AbortSignal.timeout(3000) });
    return res.ok;
  } catch { return false; }
}

async function streamScan(
  params: EquityScanParams,
  callbacks: {
    onProgress: (p: ScanProgressState) => void;
    onResult:   (r: EquityScanResponse) => void;
    onDone:     () => void;
    onError:    (msg: string) => void;
    signal?:    AbortSignal;
  },
): Promise<void> {
  const qs = new URLSearchParams({
    universe:  params.universe,
    threshold: String(params.threshold),
  });
  if (params.pattern_names)      qs.set("pattern_names",     params.pattern_names);
  if (params.pattern_mode)       qs.set("pattern_mode",      params.pattern_mode);
  if (params.min_pattern_conf)   qs.set("min_pattern_conf",  String(params.min_pattern_conf));
  if (params.timeframes)         qs.set("timeframes",        params.timeframes);
  const FASTAPI = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";
  try {
    const res = await fetch(`${FASTAPI}/api/equity-scanner/scan/stream?${qs}`, {
      signal: callbacks.signal,
    });
    if (!res.ok) {
      // The backend rejects invalid input with a named field instead of
      // silently scanning something else — surface its message, not "HTTP 400".
      let msg = `HTTP ${res.status}`;
      try {
        const body = await res.json();
        if (body?.error) msg = body.error;
      } catch { /* non-JSON error body */ }
      callbacks.onError(msg);
      return;
    }

    const reader  = res.body!.getReader();
    const decoder = new TextDecoder();
    let buffer    = "";
    let progress: ScanProgressState = {
      done: 0, total: 0, currentSym: "", found: 0, setupsSoFar: 0, enriching: false,
    };

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
            callbacks.onResult(msg as EquityScanResponse);
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
// UI atoms
// ─────────────────────────────────────────────────────────────────────────────

function TfBadge({ tf }: { tf: string }) {
  return (
    <span className={cn("inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-bold border",
      TF_COLOR[tf] ?? "bg-white/10 text-white/60 border-white/20")}>
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

const SCORE_TIP =
  "Confluence Score (0–100): Trend/Structure (30) + Momentum (25) + Volume (15) + " +
  "Candle Trigger (25) + Structural Bonus (5). All five are reachable, so 100 is a " +
  "real ceiling. For instruments with no volume (indices) the Volume category is " +
  "excluded and the remaining 85 points are rescaled to 100, so the same threshold " +
  "means the same thing for an index as for a stock.";

function ScorePill({ score, volumeAvailable }: { score: number; volumeAvailable?: boolean }) {
  const cls =
    score >= 80 ? "bg-emerald-500/20 text-emerald-300 border-emerald-500/40" :
    score >= 65 ? "bg-yellow-500/20 text-yellow-300 border-yellow-500/40" :
                  "bg-white/10 text-white/50 border-white/20";
  return (
    <span className="inline-flex items-center gap-1">
      <HelpTip tip={SCORE_TIP}>
        <span className={cn("inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-bold border", cls)}>
          {score}
        </span>
      </HelpTip>
      {volumeAvailable === false && (
        <HelpTip tip="No volume data for this instrument. The Volume category is excluded and the remaining categories are rescaled to 100 — not given free neutral points.">
          <span className="px-1.5 py-0.5 rounded text-[9px] font-semibold border border-white/15 text-white/40">
            no vol
          </span>
        </HelpTip>
      )}
    </span>
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

function TradePill({ plan }: { plan: EquityPlan }) {
  const c = plan.currency;
  const isBuy = plan.action === "BUY";
  return (
    <span className={cn(
      "inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-bold border",
      isBuy
        ? "bg-emerald-500/20 border-emerald-500/40 text-emerald-300"
        : "bg-red-500/20 border-red-500/40 text-red-300",
    )}>
      {plan.action} {c}{Number(plan.entry_price).toLocaleString()}
    </span>
  );
}

/**
 * Hit rate, or a stated reason — never a blank. The number is measured on the
 * card's own timeframe, so it says which one and over how many bars.
 */
function BacktestTag({ bt }: { bt: BacktestInfo | null }) {
  if (!bt) return <span className="text-[10px] text-white/20">—</span>;
  if (bt.hit_rate === null) {
    return (
      <HelpTip tip={bt.reason ?? bt.note ?? "No hit rate available."}>
        <span className="text-[10px] text-white/30 underline decoration-dotted underline-offset-2">
          no hit rate
        </span>
      </HelpTip>
    );
  }
  const pct = Math.round(bt.hit_rate * 100);
  const tip =
    `${bt.sample_size} prior ${bt.detector ?? "pattern"} occurrence(s) on ` +
    `${bt.timeframe ?? "this"} bars` +
    (bt.window_bars ? ` over a ${bt.window_bars}-bar window` : "") +
    ". A win is T1 (1.5 × risk) touched within 5 bars before the stop.";
  return (
    <HelpTip tip={tip}>
      <span className={cn("text-[10px] font-medium", pct >= 55 ? "text-emerald-400" : "text-white/40")}>
        {pct}% ({bt.sample_size})
        {bt.timeframe && <span className="text-white/25"> {bt.timeframe}</span>}
      </span>
    </HelpTip>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Summary strip
// ─────────────────────────────────────────────────────────────────────────────

function SummaryStrip({ summary, scanAt }: { summary: EquityScanSummary; scanAt: string }) {
  const chips = [
    { label: "Scanned",    value: summary.total_symbols, sub: "symbols",   color: "text-white"       },
    { label: "Setups",     value: summary.total_setups,  sub: "found",     color: "text-yellow-300"  },
    { label: "Bullish",    value: summary.bullish,       sub: "↑",         color: "text-emerald-400" },
    { label: "Bearish",    value: summary.bearish,       sub: "↓",         color: "text-red-400"     },
    { label: "Strong 80+", value: summary.strong_80plus, sub: "high-conf", color: "text-emerald-300" },
  ];
  const tfChips = Object.entries(summary.by_timeframe).filter(([, v]) => v > 0);

  return (
    <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4 space-y-3">
      <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
        {chips.map((c) => (
          <div key={c.label} className="flex flex-col gap-0.5 p-3 rounded-lg bg-[var(--color-surface-2)]">
            <span className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)]">{c.label}</span>
            <span className={cn("text-2xl font-bold", c.color)}>{c.value}</span>
            <span className="text-[10px] text-[var(--color-text-muted)]">{c.sub}</span>
          </div>
        ))}
      </div>
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
// Symbol grouping
// ─────────────────────────────────────────────────────────────────────────────

interface SymbolGroup { symbol: string; best: EquitySetupCard; cards: EquitySetupCard[]; }

function groupBySymbol(cards: EquitySetupCard[]): SymbolGroup[] {
  const map = new Map<string, EquitySetupCard[]>();
  for (const c of cards) { const a = map.get(c.symbol) ?? []; a.push(c); map.set(c.symbol, a); }
  return Array.from(map.entries()).map(([symbol, arr]) => {
    const sorted = [...arr].sort((a, b) => b.confluence_score - a.confluence_score);
    return { symbol, best: sorted[0], cards: sorted };
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// Expanded per-TF section: chart + score breakdown + trade plan
// ─────────────────────────────────────────────────────────────────────────────

function TfSection({ card }: { card: EquitySetupCard }) {
  const { plan, score_breakdown: sb } = card;
  const currency = plan?.currency ?? "₹";

  return (
    <div className="rounded-xl border border-white/10 bg-[var(--color-surface)] overflow-hidden">
      {/* Header */}
      <div className="flex items-center gap-3 px-4 py-2.5 bg-white/5 border-b border-white/10">
        <TfBadge tf={card.timeframe} />
        <DirBadge dir={card.direction} />
        {card.pattern !== "None" && (
          <span className="text-yellow-300/80 text-[12px] font-medium">{card.pattern}</span>
        )}
        <ScorePill score={card.confluence_score} volumeAvailable={card.volume_available} />
        <BreakoutBadge state={card.breakout_state} label={card.breakout_label} />
        <BacktestTag bt={card.backtest} />
        {plan && <span className="ml-auto"><TradePill plan={plan} /></span>}
      </div>

      {/* Chart */}
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
        <div className="flex flex-wrap gap-1 mt-2 pb-1">
          {card.reasons.map((r) => (
            <span key={r} className="px-1.5 py-0.5 rounded text-[10px] bg-white/5 border border-white/10 text-white/50">{r}</span>
          ))}
        </div>
      </div>

      {/* Score + Plan */}
      <div className="grid sm:grid-cols-2 gap-0 divide-x divide-white/10">
        {/* Score breakdown */}
        <div className="p-3">
          <p className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)] mb-2.5">Score breakdown</p>
          {[
            { label: "Trend",      val: sb.trend,           max: 30, color: "bg-blue-500"   },
            { label: "Momentum",   val: sb.momentum,        max: 25, color: "bg-purple-500" },
            { label: "Volume",     val: sb.volume,          max: 15, color: "bg-orange-500" },
            { label: "Candle",     val: sb.candle,          max: 25, color: "bg-pink-500"   },
            { label: "Structural", val: sb.structural ?? 0, max: 5,  color: "bg-green-500"  },
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

        {/* Trade plan */}
        <div className="p-3 space-y-2.5">
          {plan ? (
            <>
              <div className="grid grid-cols-3 gap-1.5 text-[11px]">
                {[
                  { label: "Entry", val: plan.entry_price, cls: "text-white"       },
                  { label: "Stop",  val: plan.sl_price,    cls: "text-red-400"     },
                  { label: "T1",    val: plan.t1_price,    cls: "text-emerald-400" },
                ].map((item) => (
                  <div key={item.label} className="p-2 rounded bg-white/5 border border-white/10 text-center">
                    <div className="text-[var(--color-text-muted)] text-[10px] mb-0.5">{item.label}</div>
                    <div className={cn("font-bold text-sm", item.cls)}>
                      {currency}{Number(item.val).toLocaleString()}
                    </div>
                  </div>
                ))}
              </div>
              <div className="text-[11px] text-white/40 px-0.5 flex flex-wrap items-center gap-x-1.5">
                <span>T2 {currency}{Number(plan.t2_price).toLocaleString()}</span>
                <span>·</span>
                <HelpTip tip={plan.rr_basis || "Fixed design parameter, not a measured property of this setup."}>
                  <span className="underline decoration-dotted underline-offset-2">
                    R:R <span className="text-white/70 font-medium">{plan.rr.toFixed(2)}</span>
                    <span className="text-white/25"> (fixed)</span>
                  </span>
                </HelpTip>
                <span>·</span>
                <span>Risk {currency}{Number(plan.risk_per_share).toLocaleString()} / share</span>
              </div>
              <div className="flex items-start gap-1.5 text-[11px] text-white/40">
                <Clock className="size-3.5 mt-0.5 text-blue-400 shrink-0" />
                <span className="leading-relaxed">{plan.exit_rule}</span>
              </div>
            </>
          ) : (
            <div className="flex items-center gap-2 text-[11px] text-white/25 p-2 rounded bg-white/5 border border-white/10">
              <Info className="size-3.5 shrink-0" />
              Trade plan unavailable (range setup or insufficient ATR data)
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Grouped table row
// ─────────────────────────────────────────────────────────────────────────────

function GroupRow({ group, idx }: { group: SymbolGroup; idx: number }) {
  const [open, setOpen] = useState(false);
  const { best } = group;
  const plan     = best.plan;
  const currency = plan?.currency ?? "₹";

  return (
    <>
      <tr
        onClick={() => setOpen((v) => !v)}
        className={cn("cursor-pointer transition-colors border-b border-white/5",
          open ? "bg-[var(--color-surface-2)]" : "hover:bg-white/5")}
      >
        <td className="px-3 py-3 w-6">
          {open ? <ChevronDown className="size-3.5 text-white/40" /> : <ChevronRight className="size-3.5 text-white/30" />}
        </td>
        <td className="px-2 py-3 text-[11px] text-white/30 w-8">{idx + 1}</td>

        {/* Symbol + TF badges */}
        <td className="px-3 py-3">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-semibold text-white text-[13px]">{group.symbol}</span>
            {group.cards.map((c) => <TfBadge key={c.timeframe} tf={c.timeframe} />)}
          </div>
        </td>

        <td className="px-2 py-3"><DirBadge dir={best.direction} /></td>

        {/* Patterns */}
        <td className="px-3 py-3 text-[12px]">
          {(() => {
            const pats = Array.from(new Set(group.cards.map((c) => c.pattern).filter((p) => p !== "None")));
            return pats.length > 0
              ? <span className="text-yellow-300/80 font-medium">{pats.join(" · ")}</span>
              : <span className="text-white/20">—</span>;
          })()}
        </td>

        <td className="px-2 py-3">
          <div className="flex items-center gap-1.5 flex-wrap">
            <ScorePill score={best.confluence_score} volumeAvailable={best.volume_available} />
            <BreakoutBadge state={best.breakout_state} label={best.breakout_label} />
          </div>
        </td>

        {/* Trade action */}
        <td className="px-2 py-3">
          {plan ? <TradePill plan={plan} /> : <span className="text-white/20 text-[11px]">—</span>}
        </td>

        {/* Entry / SL */}
        <td className="px-3 py-3 text-[11px] text-right font-mono">
          {plan ? (
            <div className="flex flex-col items-end gap-0.5">
              <span className="text-white">{currency}{Number(plan.entry_price).toLocaleString()}</span>
              <span className="text-red-400">SL {currency}{Number(plan.sl_price).toLocaleString()}</span>
            </div>
          ) : (
            <span className="text-white/50">{currency}{Number(best.trigger_price).toLocaleString()}</span>
          )}
        </td>

        {/* T1 / R:R */}
        <td className="px-3 py-3 text-[11px] text-right font-mono">
          {plan ? (
            <div className="flex flex-col items-end gap-0.5">
              <span className="text-emerald-400">T1 {currency}{Number(plan.t1_price).toLocaleString()}</span>
              <span className="text-white/50">R:R {plan.rr.toFixed(1)}</span>
            </div>
          ) : <span className="text-white/20">—</span>}
        </td>

        {/* Backtest */}
        <td className="px-3 py-3 text-right">
          <BacktestTag bt={best.backtest} />
        </td>
      </tr>

      {open && (
        <tr>
          <td colSpan={10} className="px-4 pb-5 pt-3 bg-[var(--color-surface-2)]/40">
            <div className="space-y-4">
              {group.cards.map((c) => <TfSection key={c.timeframe} card={c} />)}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Controls helper
// ─────────────────────────────────────────────────────────────────────────────

function Sel({ value, options, groups, onChange, wide }: {
  value: string;
  options?: { value: string; label: string }[];
  groups?: UniverseGroup[];
  onChange: (v: string) => void;
  wide?: boolean;
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className={cn(
        "bg-[var(--color-surface-2)] border border-[var(--color-border)] text-white text-[13px] rounded-lg px-4 py-2.5 focus:outline-none focus:ring-1 focus:ring-[var(--color-primary)]",
        wide ? "w-80" : "w-44",
      )}
    >
      {groups
        ? groups.map((g) => (
            <optgroup key={g.group} label={`── ${g.group} ──`}>
              {g.options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </optgroup>
          ))
        : options?.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)
      }
    </select>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Scan progress panel
// ─────────────────────────────────────────────────────────────────────────────

function ScanProgress({ progress, onCancel }: { progress: ScanProgressState; onCancel: () => void }) {
  const [elapsed, setElapsed] = useState(0);
  const [log,     setLog]     = useState<string[]>([]);
  const startRef = useRef(Date.now());

  useEffect(() => {
    if (!progress.currentSym) return;
    const entry = `${String(progress.done).padStart(3)}/${progress.total}  ${progress.currentSym.padEnd(12)}  ${
      progress.found > 0 ? `✓ ${progress.found} setup${progress.found > 1 ? "s" : ""}` : "—"
    }`;
    setLog((prev) => [...prev.slice(-7), entry]);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [progress.currentSym]);

  useEffect(() => {
    const id = setInterval(() => setElapsed(Math.floor((Date.now() - startRef.current) / 1000)), 1000);
    return () => clearInterval(id);
  }, []);

  const pct = progress.enriching
    ? 96
    : progress.total > 0
    ? Math.min(95, Math.round((progress.done / progress.total) * 95))
    : 2;

  const phaseLabel = progress.enriching
    ? "Building trade plans & backtests…"
    : "Scanning Daily · Weekly · Monthly…";

  return (
    <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5 space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <RefreshCw className="size-4 text-[var(--color-primary)] animate-spin" />
          <span className="font-semibold text-white">{phaseLabel}</span>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-[12px] text-[var(--color-text-muted)]">{elapsed}s</span>
          <button onClick={onCancel}
            className="text-[11px] text-[var(--color-text-muted)] hover:text-red-400 border border-white/10 hover:border-red-400/40 px-2 py-0.5 rounded transition-colors">
            Cancel
          </button>
        </div>
      </div>

      <div className="space-y-1.5">
        <div className="flex justify-between text-[12px]">
          <span className="text-[var(--color-text-muted)]">
            {progress.enriching
              ? `Building plans for ${progress.setupsSoFar} setups…`
              : progress.total > 0
              ? <><span className="text-white font-semibold">{progress.done}</span> / {progress.total} symbols scored</>
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
          <span>{progress.enriching ? "Phase 2/2 · Enrichment" : "Phase 1/2 · Pattern scoring"}</span>
          <span>{pct}%</span>
        </div>
      </div>

      {log.length > 0 && (
        <div className="rounded-lg bg-black/30 border border-white/10 p-3 font-mono text-[11px] space-y-0.5">
          {log.map((entry, i) => (
            <div key={i} className={cn(i === log.length - 1 ? "text-white" : "text-white/30")}>{entry}</div>
          ))}
        </div>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Page
// ─────────────────────────────────────────────────────────────────────────────

export default function EquityScannerPage() {
  const { region, isUS, currencySymbol } = useRegion();

  // Available universes depend on market region
  const universes = isUS ? US_UNIVERSES : INDIA_UNIVERSES;
  const defaultUniverse = isUS ? "us_indices" : "india_indices";

  const [params,      setParams]      = useState<EquityScanParams>({ universe: defaultUniverse, threshold: 65 });
  const [loading,     setLoading]     = useState(false);
  const [progress,    setProgress]    = useState<ScanProgressState>({ done: 0, total: 0, currentSym: "", found: 0, setupsSoFar: 0, enriching: false });
  const [result,      setResult]      = useState<EquityScanResponse | null>(null);
  const [error,       setError]       = useState<string | null>(null);
  const [scanAt,      setScanAt]      = useState<string | null>(null);
  const [backendOk,   setBackendOk]   = useState<boolean | null>(null);
  const [refreshing,  setRefreshing]  = useState(false);
  const [univCount,   setUnivCount]   = useState<Record<string, number>>({});
  const abortRef = useRef<AbortController | null>(null);

  // Post-scan display filters (none can be known until after scoring)
  const [filterDir,      setFilterDir]      = useState("all");
  const [filterPatterns, setFilterPatterns] = useState<Set<string>>(new Set());
  const [filterTfs,      setFilterTfs]      = useState<Set<string>>(new Set());

  // Pre-scan scan configuration — sent with the scan request itself
  const [selectedTimeframes,    setSelectedTimeframes]    = useState<Set<string>>(new Set(ALL_TFS));
  const [selectedPatternIds,    setSelectedPatternIds]    = useState<Set<string>>(new Set());
  const [patternMode,           setPatternMode]           = useState<PatternMode>("filter");

  // Deselecting every timeframe used to scan all three. The backend now rejects
  // it with a 400; the button is disabled so it never gets that far.
  const noTimeframes = selectedTimeframes.size === 0;

  const FASTAPI = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";
  const patternQuery = useQuery<PatternGroups>({
    queryKey: ["equity-patterns"],
    queryFn:  () => fetch(`${FASTAPI}/api/equity-scanner/patterns`).then((r) => r.json()),
    staleTime: Infinity,
  });
  const patternGroups = patternQuery.data ?? {};

  // The Settings → Scoring page configures a persistent default threshold.
  // Seed the slider from it once on load — the slider then remains a
  // per-scan override that does not itself persist.
  const scoringConfigQuery = useQuery({
    queryKey: ["scoring-config"], queryFn: api.scoringConfig, staleTime: 60_000,
  });
  const seededThresholdRef = useRef(false);
  useEffect(() => {
    if (!seededThresholdRef.current && scoringConfigQuery.data) {
      seededThresholdRef.current = true;
      setParams((p) => ({ ...p, threshold: scoringConfigQuery.data!.default_threshold }));
    }
  }, [scoringConfigQuery.data]);

  // When market region switches, reset to default universe for that market
  useEffect(() => {
    abortRef.current?.abort();
    setLoading(false);
    setResult(null);
    setError(null);
    setParams({ universe: defaultUniverse, threshold: scoringConfigQuery.data?.default_threshold ?? 65 });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [region]);

  // Health poll
  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      if (cancelled) return;
      setBackendOk(await checkHealth());
      if (!cancelled) setTimeout(poll, 10_000);
    };
    poll();
    return () => { cancelled = true; };
  }, []);

  const cancel = useCallback(() => { abortRef.current?.abort(); setLoading(false); }, []);

  const scan = useCallback(async () => {
    if (noTimeframes) {
      setError("Select at least one timeframe to scan.");
      return;
    }
    setLoading(true); setError(null);
    setProgress({ done: 0, total: 0, currentSym: "", found: 0, setupsSoFar: 0, enriching: false });

    const healthy = await checkHealth();
    setBackendOk(healthy);
    if (!healthy) {
      setError("Backend not running. Start it with: python -m uvicorn backend.main:app --port 8000 --reload");
      setLoading(false); return;
    }

    const ctl = new AbortController();
    abortRef.current = ctl;

    const scanParams: EquityScanParams = {
      ...params,
      pattern_names: selectedPatternIds.size > 0 ? Array.from(selectedPatternIds).join(",") : undefined,
      pattern_mode:  selectedPatternIds.size > 0 ? patternMode : undefined,
      timeframes: selectedTimeframes.size < ALL_TFS.length ? Array.from(selectedTimeframes).join(",") : undefined,
    };

    await streamScan(scanParams, {
      onProgress: (p) => setProgress(p),
      onResult:   (data) => {
        setResult(data); setBackendOk(true);
        setScanAt(new Date().toLocaleTimeString("en-IN", { hour12: false }));
        setFilterDir("all");
        setFilterPatterns(new Set());
        setFilterTfs(new Set());
      },
      onDone:  () => setLoading(false),
      onError: (msg) => {
        setError(msg);
        if (msg.includes("500") || msg.includes("fetch")) setBackendOk(false);
        setLoading(false);
      },
      signal: ctl.signal,
    });
  }, [params, selectedPatternIds, patternMode, selectedTimeframes, noTimeframes]);

  const upd = (k: keyof EquityScanParams) => (v: string | number) =>
    setParams((p) => ({ ...p, [k]: v }));

  // Direction and timeframe/pattern selection above are scan-time
  // configuration (see scanParams above) — results are already scoped/scored
  // to them by the time they arrive here. The filters below are purely
  // client-side display filters over the already-loaded result set.
  const visible = (result?.setups ?? [])
    .filter((c) => {
      if (filterDir !== "all" && c.direction !== filterDir) return false;
      if (!cardMatchesPatterns(c, filterPatterns)) return false;
      if (!cardMatchesTimeframe(c, filterTfs)) return false;
      return true;
    })
    // A card can survive the Patterns filter via a non-headline pattern —
    // rewrite the displayed pattern so the row always shows one you selected.
    .map((c) => ({ ...c, pattern: displayPatternFor(c, filterPatterns) }));

  // Options come from the loaded results, so the list only ever offers
  // patterns (or timeframes) that are actually present in this scan.
  const patternFilterOptions = patternOptionsFromCards(result?.setups ?? []);
  const tfFilterOptions = timeframeOptionsFromCards(
    result?.setups ?? [], (tf) => TF_LABEL[tf] ?? tf,
  );

  const selectedUniverse = universes.find((u) => u.value === params.universe);

  return (
    <div className="p-6 max-w-[1400px] mx-auto space-y-5">

      {/* Header */}
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <div className="flex items-center gap-2 flex-wrap">
            <BarChart2 className="size-5 text-blue-400" />
            <h1 className="text-xl font-bold text-white">Equity Live Scanner</h1>

            {/* Market badge */}
            <span className={cn(
              "px-2 py-0.5 rounded-full text-[10px] font-bold border",
              isUS
                ? "bg-blue-500/15 border-blue-500/30 text-blue-300"
                : "bg-orange-500/15 border-orange-500/30 text-orange-300",
            )}>
              {isUS ? "🇺🇸 US Market" : "🇮🇳 India Market"}
            </span>

            {/* Backend health */}
            <span className={cn(
              "flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[10px] font-medium border",
              backendOk === null ? "bg-white/5 border-white/10 text-white/30"
              : backendOk ? "bg-emerald-500/15 border-emerald-500/30 text-emerald-400"
              : "bg-red-500/15 border-red-500/30 text-red-400",
            )}>
              <span className={cn("size-1.5 rounded-full",
                backendOk === null ? "bg-white/30" : backendOk ? "bg-emerald-400 animate-pulse" : "bg-red-400")} />
              {backendOk === null ? "checking…" : backendOk ? "Backend online" : "Backend offline"}
            </span>
          </div>
          <p className="text-[12px] text-[var(--color-text-muted)] mt-0.5">
            Scans Daily · Weekly · Monthly — surfaces high-confluence stock setups with ATR-based trade plans.
            Switch market region in the sidebar to scan US markets.
          </p>
        </div>
        {scanAt && <span className="text-[11px] text-[var(--color-text-muted)]">Last scan: {scanAt}</span>}
      </div>

      {/* Controls */}
      <div className="rounded-xl bg-[var(--color-surface)] border border-[var(--color-border)] p-5 space-y-5">
        <div className="flex flex-wrap items-end gap-5">
          {/* Universe — options change based on region */}
          <div className="flex flex-col gap-2 flex-1 min-w-[260px]">
            <label className="text-[11px] uppercase tracking-wider text-[var(--color-text-muted)]">
              Universe ({isUS ? "US" : "India"})
            </label>
            <div className="flex items-center gap-2">
              <Sel
                value={params.universe}
                groups={isUS ? US_UNIVERSE_GROUPS : INDIA_UNIVERSE_GROUPS}
                onChange={async (v) => {
                  upd("universe")(v);
                  // Fetch live count for large universes
                  if (REFRESH_UNIVERSES.has(v) && !(univCount[v] > 0)) {
                    const n = await fetchUniverseCount(v);
                    if (n > 0) setUnivCount((c) => ({ ...c, [v]: n }));
                  }
                }}
                wide
              />
              {/* Refresh button — only for all_nse / all_us */}
              {REFRESH_UNIVERSES.has(params.universe) && (
                <button
                  disabled={refreshing || loading}
                  onClick={async () => {
                    setRefreshing(true);
                    const res = await refreshUniverse(params.universe);
                    if (res) setUnivCount((c) => ({ ...c, [params.universe]: res.count }));
                    setRefreshing(false);
                  }}
                  title="Refresh universe from live source (nselib for India)"
                  className={cn(
                    "flex items-center gap-1.5 px-3 py-2.5 rounded-lg border text-[12px] font-medium transition-colors shrink-0",
                    refreshing
                      ? "border-blue-500/30 text-blue-400 bg-blue-500/10 cursor-not-allowed"
                      : "border-[var(--color-border)] text-[var(--color-text-muted)] hover:border-blue-500/50 hover:text-blue-300 hover:bg-blue-500/5",
                  )}
                >
                  {refreshing
                    ? <><RefreshCcw className="size-3.5 animate-spin" /> Fetching…</>
                    : <><Database className="size-3.5" /> Refresh</>
                  }
                </button>
              )}
            </div>
            {selectedUniverse && (
              <p className="text-[11px] text-[var(--color-text-muted)]">
                {selectedUniverse.desc}
                {univCount[params.universe] > 0 && (
                  <span className="ml-2 text-emerald-400 font-medium">
                    · {univCount[params.universe].toLocaleString()} symbols loaded
                  </span>
                )}
              </p>
            )}
            {REFRESH_UNIVERSES.has(params.universe) && !(univCount[params.universe] > 0) && (
              <p className="text-[11px] text-yellow-400/70 flex items-center gap-1">
                <AlertTriangle className="size-3 shrink-0" />
                Click Refresh to populate from {params.universe === "all_nse" ? "NSE (nselib)" : "all US JSON files"} before scanning.
              </p>
            )}
          </div>

          {/* Min score */}
          <WeightSlider
            label="Min confluence score"
            value={params.threshold} min={40} max={90} step={5}
            onChange={upd("threshold")}
            helperText={(v) => v >= 80 ? "Strong signals only" :
              v >= 65 ? "Recommended — balanced quality" :
              "Relaxed — shows more, lower quality"}
          />

          <button
            onClick={scan} disabled={loading || noTimeframes}
            title={noTimeframes ? "Select at least one timeframe to scan." : undefined}
            className={cn(
              "flex items-center gap-2 px-8 py-3 rounded-lg font-semibold text-[14px] transition-all self-end",
              loading || noTimeframes
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
                ? "— all 3 (no filter)"
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

        <PatternPicker
          groups={patternGroups}
          loading={patternQuery.isLoading}
          selected={selectedPatternIds}
          onChange={setSelectedPatternIds}
          mode={patternMode}
          onModeChange={setPatternMode}
        />

        {/* Post-scan filter — direction can't be known pre-scan */}
        {result && !loading && (
          <div className="flex flex-wrap items-end gap-4 pt-3 border-t border-[var(--color-border)]">
            <span className="text-[11px] text-[var(--color-text-muted)] self-center">Filter:</span>
            <div className="flex flex-col gap-1">
              <label className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)]">Direction</label>
              <Sel value={filterDir} onChange={setFilterDir} options={[
                { value: "all",     label: "All directions" },
                { value: "bullish", label: "↑ Bullish only" },
                { value: "bearish", label: "↓ Bearish only" },
                { value: "range",   label: "→ Range only"   },
              ]} />
            </div>

            <MultiSelectFilter
              label="Patterns"
              allLabel="All patterns"
              searchPlaceholder="Search patterns…"
              options={patternFilterOptions}
              selected={filterPatterns}
              onChange={setFilterPatterns}
            />

            <MultiSelectFilter
              label="Timeframe"
              allLabel="All timeframes"
              searchPlaceholder="Search timeframes…"
              width="w-40"
              options={tfFilterOptions}
              selected={filterTfs}
              onChange={setFilterTfs}
            />
            <span className="text-[12px] text-[var(--color-text-muted)] self-end ml-auto">
              Showing <span className="text-white font-medium">{groupBySymbol(visible).length}</span> symbols
              {" · "}<span className="text-white font-medium">{visible.length}</span> setups
              {visible.length < result.summary.total_setups && (
                <> of <span className="text-white font-medium">{result.summary.total_setups}</span></>
              )}
            </span>
          </div>
        )}
      </div>

      {/* Error */}
      {error && !loading && (
        <div className="flex items-start gap-3 p-4 rounded-xl bg-red-500/10 border border-red-500/30 text-red-300 text-[13px]">
          <AlertTriangle className="size-4 mt-0.5 shrink-0" />
          <div className="flex-1 space-y-1">
            <p className="font-semibold">{backendOk === false ? "Backend not running" : "Scan error"}</p>
            <p className="text-[12px] opacity-80">{error}</p>
            {backendOk === false && (
              <div className="mt-2 p-2 rounded bg-black/20 text-[11px] opacity-70 font-mono">
                python -m uvicorn backend.main:app --port 8000 --reload
              </div>
            )}
            <button onClick={scan} className="mt-1 inline-flex items-center gap-1.5 text-[11px] underline underline-offset-2 opacity-70 hover:opacity-100">
              <RefreshCw className="size-3" /> Retry
            </button>
          </div>
        </div>
      )}

      {/* Progress */}
      {loading && <ScanProgress progress={progress} onCancel={cancel} />}

      {/* Results */}
      {!loading && result && (
        <>
          {/* Coverage warning — "no setups" vs "half the universe failed to load" */}
          <ScanQualityBanner summary={result.summary} totalSymbols={result.summary.total_symbols} />

          <SummaryStrip summary={result.summary} scanAt={scanAt ?? ""} />

          <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] overflow-hidden">
            {visible.length === 0 ? (
              <div className="text-center py-14 text-[var(--color-text-muted)]">
                <Activity className="size-10 mx-auto mb-3 opacity-20" />
                <p className="font-medium text-white/50">No setups match the current filters</p>
                <p className="text-[12px] mt-1">Try lowering the min score or choosing a different filter.</p>
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
                      <th className="px-2 py-2">Trade</th>
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

          <p className="text-[11px] text-[var(--color-text-muted)] border-t border-[var(--color-border)] pt-3">
            {result.disclaimer}
          </p>
        </>
      )}

      {/* Empty state */}
      {!loading && !result && !error && (
        <div className="text-center py-20 text-[var(--color-text-muted)]">
          <BarChart2 className="size-12 mx-auto mb-4 opacity-20" />
          <p className="font-medium text-white/50">Choose a universe and hit Run Scan</p>
          <p className="text-[12px] mt-1 max-w-md mx-auto">
            Scans Daily, Weekly, and Monthly charts for {isUS ? "US" : "India"} equities.
            Each result includes pattern, confluence score, and an ATR-based trade plan.
            Use the sidebar region toggle to switch between 🇮🇳 India and 🇺🇸 US markets.
          </p>
        </div>
      )}
    </div>
  );
}
