"use client";

import { useState, useEffect } from "react";
import {
  X, TrendingUp, TrendingDown, CheckCircle2, AlertTriangle,
  Clock, ExternalLink, Info,
} from "lucide-react";
import { cn } from "@/lib/utils";
import {
  getMarketInfo, nearestWeeklyExpiry, nearestMonthlyExpiry,
  type MarketInfo,
} from "@/lib/market-hours";
import { getLotSize, INDEX_SYMBOLS } from "@/lib/fno-types";

interface TradeSetup {
  symbol:          string;
  option_type:     "CE" | "PE";
  strike:          number;
  expiry:          string;
  action:          "BUY" | "SELL";
  entry_premium:   number;
  sl_premium:      number;
  t1_premium:      number;
  t2_premium:      number;
  lot_size:        number;
  rr:              number;
  exit_rule:       string;
  direction:       "bullish" | "bearish" | "range";
  timeframe:       string;
  confluence_score: number;
}

interface Props {
  setup:   TradeSetup;
  onClose: () => void;
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

async function submitPaperTrade(body: Record<string, unknown>) {
  const res = await fetch(`${API_BASE}/api/fno/paper-trades`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err?.detail ?? `HTTP ${res.status}`);
  }
  return res.json();
}

function fmt(n: number, d = 0) {
  return n.toLocaleString("en-IN", { minimumFractionDigits: d, maximumFractionDigits: d });
}

// ── Expiry date helpers ───────────────────────────────────────────────────────

const _MONTH_MAP: Record<string, string> = {
  Jan: "01", Feb: "02", Mar: "03", Apr: "04", May: "05", Jun: "06",
  Jul: "07", Aug: "08", Sep: "09", Oct: "10", Nov: "11", Dec: "12",
};
const _MONTH_NAMES = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];

function expiryToISO(expiry: string): string {
  const [d, m, y] = expiry.split("-");
  const mm = _MONTH_MAP[m];
  if (!mm || !y || !d) return "";
  return `${y}-${mm}-${d.padStart(2, "0")}`;
}

function isoToExpiry(iso: string): string {
  const [y, m, d] = iso.split("-");
  const name = _MONTH_NAMES[parseInt(m, 10) - 1];
  if (!name || !y || !d) return "";
  return `${d}-${name}-${y}`;
}

// ── Market status badge ───────────────────────────────────────────────────────

function MarketBadge({ info }: { info: MarketInfo }) {
  return (
    <div className={cn(
      "flex items-center gap-2 rounded-lg px-3 py-2 text-[12px]",
      info.status === "open"    && "bg-emerald-500/10 border border-emerald-500/25",
      info.status === "preopen" && "bg-amber-500/10 border border-amber-500/25",
      (info.status === "closed" || info.status === "weekend") && "bg-slate-500/10 border border-slate-500/25",
    )}>
      <span className={cn("size-2 rounded-full animate-pulse shrink-0", info.dotColor)} />
      <span className={cn("font-semibold", info.labelColor)}>{info.label}</span>
      <span className="text-[var(--color-text-muted)]">{info.sessionNote}</span>
    </div>
  );
}

// ── Expiry chips ──────────────────────────────────────────────────────────────

function ExpiryChips({
  selected,
  onChange,
  isIndex,
}: {
  selected:  string;
  onChange:  (v: string) => void;
  isIndex:   boolean;
}) {
  const weekly  = nearestWeeklyExpiry();
  const monthly = nearestMonthlyExpiry();
  const options = isIndex
    ? [{ label: "Weekly", value: weekly }, { label: "Monthly", value: monthly }]
    : [{ label: "Monthly", value: monthly }];

  return (
    <div className="flex flex-wrap gap-1.5 items-center">
      {options.map((o) => (
        <button
          key={o.value}
          onClick={() => onChange(o.value)}
          className={cn(
            "px-2.5 py-1 rounded-full text-[11px] font-medium border transition-colors",
            selected === o.value
              ? "bg-[var(--color-primary)] border-[var(--color-primary)] text-white"
              : "border-[var(--color-border)] text-[var(--color-text-muted)] hover:border-[var(--color-primary)]/60 hover:text-white",
          )}
        >
          {o.label} · {o.value}
        </button>
      ))}
      {/* Date picker — synced with chip selection */}
      <input
        type="date"
        value={expiryToISO(selected)}
        onChange={(e) => e.target.value && onChange(isoToExpiry(e.target.value))}
        className="h-[26px] px-2 rounded-full text-[11px] border border-[var(--color-border)] bg-[var(--color-surface-2)] text-white focus:outline-none focus:border-[var(--color-primary)] [color-scheme:dark]"
      />
    </div>
  );
}

// ── Cost breakdown row ────────────────────────────────────────────────────────

function CostRow({ label, value, sub, cls = "" }: { label: string; value: string; sub?: string; cls?: string }) {
  return (
    <div className="flex items-center justify-between py-1.5 border-b border-white/5 last:border-0">
      <span className="text-[12px] text-[var(--color-text-muted)]">{label}</span>
      <div className="text-right">
        <span className={cn("text-[13px] font-semibold", cls)}>{value}</span>
        {sub && <div className="text-[10px] text-[var(--color-text-muted)]">{sub}</div>}
      </div>
    </div>
  );
}

// ── Main modal ────────────────────────────────────────────────────────────────

export function PaperTradeModal({ setup, onClose }: Props) {
  const [mkt, setMkt]   = useState<MarketInfo>(getMarketInfo());
  const [lots, setLots] = useState(1);

  // Lot size — editable so users can correct it when NSE revises it each expiry cycle
  const defaultLot  = getLotSize(setup.symbol);
  const [lotSize, setLotSize] = useState(defaultLot > 1 ? defaultLot : setup.lot_size);
  const isIndex     = INDEX_SYMBOLS.includes(setup.symbol.toUpperCase());

  // Auto-set expiry based on market / symbol type
  const [expiry, setExpiry] = useState(
    setup.expiry || (isIndex ? nearestWeeklyExpiry() : nearestMonthlyExpiry()),
  );
  const [entryPremium, setEntryPremium] = useState(setup.entry_premium);
  const [status, setStatus] = useState<"idle" | "loading" | "ok" | "error">("idle");
  const [errMsg, setErrMsg] = useState("");

  // Refresh market status every 30 s
  useEffect(() => {
    const id = setInterval(() => setMkt(getMarketInfo()), 30_000);
    return () => clearInterval(id);
  }, []);

  // Costs
  const lotCost    = entryPremium * lotSize;
  const totalCost  = lotCost * lots;
  const slLoss     = (entryPremium - setup.sl_premium) * lotSize * lots;
  const t1Gain     = (setup.t1_premium - entryPremium) * lotSize * lots;
  const t2Gain     = (setup.t2_premium - entryPremium) * lotSize * lots;

  async function submit() {
    setStatus("loading");
    try {
      await submitPaperTrade({
        symbol:          setup.symbol,
        instrument_type: setup.option_type,
        strike:          setup.strike,
        expiry:          expiry,
        action:          setup.action,
        lots,
        lot_size:        lotSize,
        entry_price:     entryPremium,
        target_price:    setup.t1_premium,
        stop_loss:       setup.sl_premium,
        source:          "SCANNER",
        strategy_name:   `${setup.symbol} ${setup.option_type} ${setup.timeframe} | Score ${setup.confluence_score}`,
      });
      setStatus("ok");
    } catch (e: unknown) {
      setStatus("error");
      setErrMsg(e instanceof Error ? e.message : "Failed to add trade");
    }
  }

  const isBull = setup.option_type === "CE";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
      <div className="w-full max-w-md rounded-2xl bg-[var(--color-surface)] border border-[var(--color-border)] shadow-2xl overflow-hidden">

        {/* ── Header ─────────────────────────────────────────────────────── */}
        <div className={cn(
          "flex items-center justify-between px-5 py-4 border-b border-[var(--color-border)]",
          isBull ? "bg-emerald-500/8" : "bg-red-500/8",
        )}>
          <div className="flex items-center gap-3">
            {isBull
              ? <TrendingUp  className="size-5 text-emerald-400 shrink-0" />
              : <TrendingDown className="size-5 text-red-400    shrink-0" />}
            <div>
              <p className="font-bold text-white text-[15px] leading-tight">
                {setup.action} {setup.symbol} {setup.option_type} {fmt(setup.strike)}
              </p>
              <p className="text-[11px] text-[var(--color-text-muted)] mt-0.5">
                {setup.timeframe} chart · Score {setup.confluence_score}/100 · R:R {setup.rr.toFixed(1)}
              </p>
            </div>
          </div>
          <button onClick={onClose} className="text-[var(--color-text-muted)] hover:text-white transition-colors">
            <X className="size-5" />
          </button>
        </div>

        <div className="p-4 space-y-4 max-h-[80vh] overflow-y-auto">

          {/* ── Market status ─────────────────────────────────────────────── */}
          <MarketBadge info={mkt} />

          {/* ── Success state ─────────────────────────────────────────────── */}
          {status === "ok" && (
            <div className="rounded-xl bg-emerald-500/10 border border-emerald-500/30 p-4 space-y-3">
              <div className="flex items-center gap-2 text-emerald-400 font-semibold text-[14px]">
                <CheckCircle2 className="size-5" />
                Trade added to paper portfolio!
              </div>
              <div className="text-[12px] text-[var(--color-text-muted)] space-y-1">
                <div>{setup.action} {lots}× {setup.symbol} {setup.option_type} {fmt(setup.strike)} @ ₹{fmt(entryPremium, 1)}</div>
                <div>Total deployed: ₹{fmt(totalCost, 0)} · Expiry: {expiry}</div>
              </div>
              <div className="flex gap-2 pt-1">
                <a
                  href="/paper-trade"
                  target="_blank"
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-500/20 border border-emerald-500/40 text-emerald-300 text-[12px] font-medium hover:bg-emerald-500/30 transition-colors"
                >
                  View in Paper Trade <ExternalLink className="size-3" />
                </a>
                <button
                  onClick={onClose}
                  className="flex-1 py-1.5 rounded-lg border border-[var(--color-border)] text-[var(--color-text-muted)] text-[12px] hover:text-white transition-colors"
                >
                  Close
                </button>
              </div>
            </div>
          )}

          {status !== "ok" && (
            <>
              {/* ── Spot levels ───────────────────────────────────────────── */}
              <div className="grid grid-cols-4 gap-1.5 text-center text-[11px]">
                {[
                  { label: "Entry Spot", val: `₹${fmt(setup.strike, 0)}`,      cls: "text-white"       },
                  { label: "Stop Loss",  val: `₹${fmt(setup.strike - (setup.entry_premium - setup.sl_premium) / 0.5, 0)}`, cls: "text-red-400"   },
                  { label: "Target 1",  val: `₹${fmt(setup.strike + (setup.t1_premium - setup.entry_premium) / 0.5, 0)}`, cls: "text-emerald-400" },
                  { label: "Target 2",  val: `₹${fmt(setup.strike + (setup.t2_premium - setup.entry_premium) / 0.5, 0)}`, cls: "text-emerald-300" },
                ].map((item) => (
                  <div key={item.label} className="rounded-lg bg-white/5 border border-white/8 p-1.5">
                    <div className="text-[var(--color-text-muted)] text-[9px] uppercase mb-0.5">{item.label}</div>
                    <div className={cn("font-bold text-[13px]", item.cls)}>{item.val}</div>
                  </div>
                ))}
              </div>

              {/* ── Expiry ────────────────────────────────────────────────── */}
              <div className="space-y-1.5">
                <div className="flex items-center gap-1.5 text-[11px] text-[var(--color-text-muted)]">
                  <Clock className="size-3.5" />
                  <span className="uppercase tracking-wider">Expiry</span>
                </div>
                <ExpiryChips selected={expiry} onChange={setExpiry} isIndex={isIndex} />
              </div>

              {/* ── Lots + Lot Size + Premium ─────────────────────────────── */}
              <div className="grid grid-cols-3 gap-3">
                <label className="flex flex-col gap-1.5">
                  <span className="text-[11px] text-[var(--color-text-muted)] uppercase tracking-wider">Lots</span>
                  <input
                    type="number" min={1} max={100} value={lots}
                    onChange={(e) => setLots(Math.max(1, Number(e.target.value)))}
                    className="bg-[var(--color-surface-2)] border border-[var(--color-border)] text-white rounded-lg px-3 py-2 text-[13px] focus:outline-none focus:ring-1 focus:ring-[var(--color-primary)]"
                  />
                </label>
                <label className="flex flex-col gap-1.5">
                  <span className="text-[11px] text-[var(--color-text-muted)] uppercase tracking-wider">Lot Size</span>
                  <input
                    type="number" min={1} value={lotSize}
                    onChange={(e) => setLotSize(Math.max(1, Number(e.target.value)))}
                    className="bg-[var(--color-surface-2)] border border-[var(--color-border)] text-white rounded-lg px-3 py-2 text-[13px] focus:outline-none focus:ring-1 focus:ring-[var(--color-primary)]"
                  />
                </label>
                <label className="flex flex-col gap-1.5">
                  <span className="text-[11px] text-[var(--color-text-muted)] uppercase tracking-wider">Entry Premium (₹)</span>
                  <input
                    type="number" step={0.5} value={entryPremium}
                    onChange={(e) => setEntryPremium(Number(e.target.value))}
                    className="bg-[var(--color-surface-2)] border border-[var(--color-border)] text-white rounded-lg px-3 py-2 text-[13px] focus:outline-none focus:ring-1 focus:ring-[var(--color-primary)]"
                  />
                </label>
              </div>

              {/* ── Cost breakdown ────────────────────────────────────────── */}
              <div className="rounded-xl bg-white/4 border border-white/8 px-4 py-3">
                <p className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)] mb-2">
                  Cost &amp; Risk — {lots} lot{lots > 1 ? "s" : ""} · Lot size {fmt(lotSize, 0)}
                </p>
                <CostRow
                  label="To buy"
                  value={`₹${fmt(totalCost, 0)}`}
                  sub={`₹${fmt(entryPremium, 1)} prem × ${fmt(lotSize, 0)} × ${lots} lot${lots > 1 ? "s" : ""}`}
                  cls="text-white"
                />
                <CostRow
                  label="Max loss (SL hit)"
                  value={`− ₹${fmt(slLoss, 0)}`}
                  sub={`₹${fmt(slLoss / lots, 0)} per lot`}
                  cls="text-red-400"
                />
                <CostRow
                  label="T1 gain"
                  value={`+ ₹${fmt(t1Gain, 0)}`}
                  sub={`R:R ${setup.rr.toFixed(1)}  ·  ₹${fmt(t1Gain / lots, 0)} per lot`}
                  cls="text-emerald-400"
                />
                <CostRow
                  label="T2 gain"
                  value={`+ ₹${fmt(t2Gain, 0)}`}
                  sub={`₹${fmt(t2Gain / lots, 0)} per lot`}
                  cls="text-emerald-300"
                />
              </div>

              {/* ── Exit rule ─────────────────────────────────────────────── */}
              <div className="flex items-start gap-2 text-[11px] text-[var(--color-text-muted)] bg-white/4 border border-white/8 rounded-lg px-3 py-2.5">
                <Info className="size-3.5 mt-0.5 shrink-0 text-blue-400" />
                <span className="leading-relaxed">{setup.exit_rule}</span>
              </div>

              {/* ── Error ─────────────────────────────────────────────────── */}
              {status === "error" && (
                <div className="flex items-center gap-2 text-red-400 text-[12px] bg-red-500/10 border border-red-500/25 rounded-lg px-3 py-2">
                  <AlertTriangle className="size-4 shrink-0" />
                  {errMsg}
                </div>
              )}

              {/* ── Actions ───────────────────────────────────────────────── */}
              <div className="flex gap-2 pt-1">
                <button
                  onClick={onClose}
                  className="px-4 py-2.5 rounded-xl border border-[var(--color-border)] text-[var(--color-text-muted)] text-[13px] hover:text-white hover:border-white/30 transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={submit}
                  disabled={status === "loading"}
                  className={cn(
                    "flex-1 py-2.5 rounded-xl font-semibold text-[13px] transition-all",
                    isBull
                      ? "bg-emerald-500 hover:bg-emerald-400 text-white"
                      : "bg-red-500    hover:bg-red-400    text-white",
                    "disabled:opacity-50 disabled:cursor-not-allowed",
                  )}
                >
                  {status === "loading"
                    ? "Adding…"
                    : `Add ${lots} lot${lots > 1 ? "s" : ""} — ₹${fmt(totalCost, 0)}`}
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
