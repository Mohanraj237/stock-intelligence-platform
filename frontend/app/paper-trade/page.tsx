"use client";

import { useState, useMemo } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  getOpenTrades,
  getClosedTrades,
  getPortfolioSummary,
  getEquityCurve,
  addPaperTrade,
  closePaperTrade,
  resetPortfolio,
  getFnoSymbols,
  refreshPaperTradePrices,
  updatePaperTradeLtp,
} from "@/lib/fno-api";
import type { PaperTrade, PortfolioSummary, PriceRefreshResult } from "@/lib/fno-types";
import { getLotSize, INDEX_SYMBOLS } from "@/lib/fno-types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn, formatINR, formatPct } from "@/lib/utils";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ReferenceLine,
  BarChart,
  Bar,
  Cell,
} from "recharts";
import { FlaskConical, Trash2, RefreshCw, X, Target, ShieldAlert } from "lucide-react";
import { getMarketInfo } from "@/lib/market-hours";

// ── Exit Price Dialog (P2-8) ──────────────────────────────────────────────────

interface ExitDialogState {
  tradeId: string;
  tradeDesc: string;  // human-readable label for the dialog title
  suggestedPrice: number;
}

function ExitDialog({
  state,
  onConfirm,
  onCancel,
}: {
  state: ExitDialogState;
  onConfirm: (tradeId: string, exitPrice: number) => void;
  onCancel: () => void;
}) {
  const [price, setPrice] = useState(state.suggestedPrice.toString());
  const parsed = parseFloat(price);
  const valid  = !isNaN(parsed) && parsed > 0;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="w-80 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6 shadow-2xl space-y-4">
        <div className="flex items-start justify-between gap-2">
          <div>
            <h3 className="text-sm font-semibold text-white">Close Position</h3>
            <p className="text-[11px] text-[var(--color-text-muted)] mt-0.5">{state.tradeDesc}</p>
          </div>
          <button onClick={onCancel} className="text-[var(--color-text-muted)] hover:text-white transition-colors">
            <X className="size-4" />
          </button>
        </div>

        <div>
          <label className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)] block mb-1">
            Exit Price (₹)
            {state.suggestedPrice > 0 && state.suggestedPrice !== parsed && (
              <span className="ml-2 normal-case text-[var(--color-text-muted)]">
                suggested: ₹{state.suggestedPrice.toFixed(2)}
              </span>
            )}
          </label>
          <input
            type="number"
            step="0.05"
            min="0.05"
            value={price}
            onChange={(e) => setPrice(e.target.value)}
            autoFocus
            className="h-9 w-full px-3 rounded border border-[var(--color-border)] bg-[var(--color-surface-2)] text-sm text-white tnum focus:outline-none focus:border-[var(--color-primary)]"
          />
          {price && !valid && (
            <p className="mt-1 text-[11px] text-[var(--color-danger)]">Enter a valid price greater than 0</p>
          )}
        </div>

        <div className="flex gap-2 pt-1">
          <button
            onClick={() => valid && onConfirm(state.tradeId, parsed)}
            disabled={!valid}
            className={cn(
              "flex-1 py-2 rounded text-sm font-medium transition-colors",
              valid
                ? "bg-[var(--color-danger)] hover:bg-[var(--color-danger)]/90 text-white"
                : "bg-[var(--color-surface-2)] text-[var(--color-text-muted)] cursor-not-allowed",
            )}
          >
            Confirm Close
          </button>
          <button
            onClick={onCancel}
            className="flex-1 py-2 rounded text-sm font-medium border border-[var(--color-border)] text-[var(--color-text-muted)] hover:text-white transition-colors"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function pnlClass(n: number) {
  return n > 0 ? "up" : n < 0 ? "down" : "text-[var(--color-text-muted)]";
}

// ── Portfolio Header ──────────────────────────────────────────────────────────

function PortfolioHeader({ data, loading }: { data?: PortfolioSummary; loading: boolean }) {
  if (loading || !data) {
    return (
      <div className="space-y-3">
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          {[0, 1, 2, 3].map((i) => (
            <Card key={i}>
              <CardContent className="p-4 space-y-2">
                <Skeleton className="h-3 w-24" />
                <Skeleton className="h-7 w-32" />
                <Skeleton className="h-3 w-20" />
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    );
  }

  const currentValue  = data.current_value ?? (data.deployed_capital + data.open_pnl);
  const openPnlPct    = data.deployed_capital > 0
    ? (data.open_pnl / data.deployed_capital) * 100
    : 0;
  const deployedPct   = data.initial_capital > 0
    ? (data.deployed_capital / data.initial_capital) * 100
    : 0;

  return (
    <div className="space-y-3">
      {/* ── 4 main metric cards ── */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">

        {/* Cash */}
        <Card>
          <CardContent className="p-4">
            <div className="text-[11px] uppercase tracking-wider text-[var(--color-text-muted)] mb-1">Available Cash</div>
            <div className="text-2xl font-bold tnum text-white">{formatINR(data.available_capital)}</div>
            <div className="mt-1 text-[11px] text-[var(--color-text-muted)]">
              of {formatINR(data.initial_capital)} initial
            </div>
            {/* utilisation bar */}
            <div className="mt-2 h-1 rounded-full bg-[var(--color-surface-2)]">
              <div
                className="h-full rounded-full bg-[var(--color-primary)] transition-all"
                style={{ width: `${Math.min(100, Math.max(2, 100 - deployedPct))}%` }}
              />
            </div>
          </CardContent>
        </Card>

        {/* Invested */}
        <Card>
          <CardContent className="p-4">
            <div className="text-[11px] uppercase tracking-wider text-[var(--color-text-muted)] mb-1">Total Invested</div>
            <div className="text-2xl font-bold tnum text-white">{formatINR(data.deployed_capital)}</div>
            <div className="mt-1 text-[11px] text-[var(--color-text-muted)]">
              {data.open_trades_count} open position{data.open_trades_count !== 1 ? "s" : ""}
            </div>
            {/* deployed pct bar */}
            <div className="mt-2 h-1 rounded-full bg-[var(--color-surface-2)]">
              <div
                className="h-full rounded-full bg-amber-400 transition-all"
                style={{ width: `${Math.min(100, Math.max(2, deployedPct))}%` }}
              />
            </div>
          </CardContent>
        </Card>

        {/* Current Value */}
        <Card>
          <CardContent className="p-4">
            <div className="text-[11px] uppercase tracking-wider text-[var(--color-text-muted)] mb-1">Current Value</div>
            <div className="text-2xl font-bold tnum text-white">{formatINR(currentValue)}</div>
            <div className={cn("mt-1 text-[11px]", pnlClass(data.open_pnl))}>
              {data.open_pnl >= 0 ? "+" : ""}{formatINR(data.open_pnl)}
              {" "}({openPnlPct >= 0 ? "+" : ""}{openPnlPct.toFixed(2)}%)
            </div>
            <div className="mt-1 text-[10px] text-[var(--color-text-muted)]">Unrealised P&amp;L</div>
          </CardContent>
        </Card>

        {/* Total P&L */}
        <Card>
          <CardContent className="p-4">
            <div className="text-[11px] uppercase tracking-wider text-[var(--color-text-muted)] mb-1">Total P&amp;L</div>
            <div className={cn("text-2xl font-bold tnum", pnlClass(data.total_pnl))}>
              {data.total_pnl >= 0 ? "+" : ""}{formatINR(data.total_pnl)}
            </div>
            <div className={cn("text-[11px]", pnlClass(data.total_pnl_pct))}>
              {data.total_pnl_pct >= 0 ? "+" : ""}{data.total_pnl_pct?.toFixed(2)}% on capital
            </div>
            <div className="mt-1.5 flex gap-3 text-[10px]">
              <span className={cn(pnlClass(data.open_pnl))}>
                Open {data.open_pnl >= 0 ? "+" : ""}{formatINR(data.open_pnl)}
              </span>
              <span className="text-[var(--color-text-muted)]">·</span>
              <span className={cn(pnlClass(data.closed_pnl ?? 0))}>
                Realised {(data.closed_pnl ?? 0) >= 0 ? "+" : ""}{formatINR(data.closed_pnl ?? 0)}
              </span>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* ── Stats strip ── */}
      <div className="flex flex-wrap items-center gap-x-5 gap-y-1.5 px-1 text-[11px]">
        <span className="text-[var(--color-text-muted)]">
          Win Rate:{" "}
          <span className={cn("font-semibold", data.win_rate >= 50 ? "up" : "text-white")}>
            {data.win_rate?.toFixed(1)}%
          </span>
        </span>
        <span className="text-[var(--color-text-muted)] hidden sm:inline">·</span>
        <span className="text-[var(--color-text-muted)]">
          Profit Factor:{" "}
          <span className={cn("font-semibold", (data.profit_factor ?? 0) >= 1.5 ? "up" : (data.profit_factor ?? 0) >= 1 ? "text-white" : "down")}>
            {data.profit_factor?.toFixed(2)}×
          </span>
        </span>
        <span className="text-[var(--color-text-muted)] hidden sm:inline">·</span>
        <span className="text-[var(--color-text-muted)]">
          {data.closed_trades_count} closed · {data.open_trades_count} open
        </span>
        <span className="text-[var(--color-text-muted)] hidden sm:inline">·</span>
        <span className="text-[var(--color-text-muted)]">
          Total Equity:{" "}
          <span className="font-semibold text-white">{formatINR(data.total_equity)}</span>
        </span>
      </div>
    </div>
  );
}

// ── Open Positions ────────────────────────────────────────────────────────────

function TradeRow({
  trade,
  onRequestClose,
  onUpdateLtp,
  closing,
}: {
  trade: PaperTrade;
  onRequestClose: (id: string, price: number, desc: string) => void;
  onUpdateLtp: (id: string, price: number) => void;
  closing: string | null;
}) {
  const [editingLtp, setEditingLtp] = useState(false);
  const [ltpInput, setLtpInput] = useState("");

  const pnl = trade.pnl_rs ?? 0;
  const isClosing = closing === trade.trade_id;
  const src = trade.price_source;
  // Derive label and colour from price_source; fall back to comparing prices for legacy trades
  const hasRealPrice = src === "live" || src === "cached" || src === "manual" || src === "synthetic"
    || (src === undefined && trade.current_price !== trade.entry_price);
  const srcLabel = src === "live" ? "live"
    : src === "cached" ? "last close"
    : src === "manual" ? "manual"
    : src === "synthetic" ? "estimated"
    : hasRealPrice ? "set"
    : "set price ✎";
  const srcColor = src === "live" ? "text-[var(--color-success)]"
    : src === "cached" ? "text-amber-400"
    : src === "manual" ? "text-[var(--color-primary)]"
    : src === "synthetic" ? "text-purple-400"
    : "text-[var(--color-text-muted)]";
  const desc = `${trade.action} ${trade.lots}× ${trade.symbol} ${trade.strike > 0 ? trade.strike + " " : ""}${trade.instrument_type}`;

  const startEditLtp = () => {
    setLtpInput(trade.current_price.toString());
    setEditingLtp(true);
  };
  const commitLtp = () => {
    const v = parseFloat(ltpInput);
    if (!isNaN(v) && v > 0) onUpdateLtp(trade.trade_id, v);
    setEditingLtp(false);
  };
  const onLtpKey = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") commitLtp();
    if (e.key === "Escape") setEditingLtp(false);
  };

  // Time since entry
  const entryDate = trade.entry_time ? new Date(trade.entry_time) : null;
  const minutesAgo = entryDate
    ? Math.round((Date.now() - entryDate.getTime()) / 60_000)
    : null;
  const timeLabel = minutesAgo === null ? ""
    : minutesAgo < 60 ? `${minutesAgo}m ago`
    : minutesAgo < 1440 ? `${Math.floor(minutesAgo / 60)}h ago`
    : `${Math.floor(minutesAgo / 1440)}d ago`;

  return (
    <tr className="border-b border-[var(--color-border)] hover:bg-[var(--color-surface-2)]/50 text-xs tnum group">
      {/* Symbol + instrument */}
      <td className="px-3 py-2.5">
        <div className="font-semibold text-white">{trade.symbol}</div>
        <div className="text-[var(--color-text-muted)]">
          {trade.strike > 0 ? `${trade.strike} ` : ""}{trade.instrument_type}
        </div>
        {timeLabel && <div className="text-[9px] text-[var(--color-text-muted)]/60">{timeLabel}</div>}
      </td>

      {/* Side */}
      <td className="px-3 py-2.5">
        <Badge variant={trade.action === "BUY" ? "success" : "danger"}>{trade.action}</Badge>
      </td>

      {/* Expiry */}
      <td className="px-3 py-2.5 text-[var(--color-text-muted)]">{trade.expiry || "—"}</td>

      {/* Qty */}
      <td className="px-3 py-2.5 text-right text-white">{trade.lots}×{trade.lot_size}</td>

      {/* Entry */}
      <td className="px-3 py-2.5 text-right text-white">{formatINR(trade.entry_price)}</td>

      {/* Invested (total premium paid) */}
      <td className="px-3 py-2.5 text-right">
        <div className="text-white">{formatINR(trade.margin_used)}</div>
        <div className="text-[9px] text-[var(--color-text-muted)]">
          {formatINR(trade.entry_price)} × {trade.lots * trade.lot_size}
        </div>
      </td>

      {/* LTP — click to edit manually */}
      <td className="px-3 py-2.5 text-right">
        {editingLtp ? (
          <input
            type="number"
            step="0.05"
            min="0.01"
            value={ltpInput}
            onChange={(e) => setLtpInput(e.target.value)}
            onBlur={commitLtp}
            onKeyDown={onLtpKey}
            autoFocus
            className="w-20 h-6 px-1.5 rounded border border-[var(--color-primary)] bg-[var(--color-surface-2)] text-right text-xs text-white focus:outline-none"
          />
        ) : (
          <button
            onClick={startEditLtp}
            title={hasRealPrice ? "Click to override price" : "No market price — click to enter manually"}
            className="group/ltp text-right"
          >
            <div className={cn("font-medium", hasRealPrice ? "text-white" : "text-[var(--color-text-muted)]")}>
              {formatINR(trade.current_price)}
            </div>
            <div className={cn("text-[9px] group-hover/ltp:text-[var(--color-primary)] transition-colors", srcColor)}>
              {srcLabel}
            </div>
          </button>
        )}
      </td>

      {/* P&L */}
      <td className={cn("px-3 py-2.5 text-right font-semibold", pnlClass(pnl))}>
        {pnl >= 0 ? "+" : ""}{formatINR(pnl)}
        <div className="text-[10px] font-normal">
          {trade.pnl_pct >= 0 ? "+" : ""}{trade.pnl_pct?.toFixed(1)}%
        </div>
      </td>

      {/* SL / Target */}
      <td className="px-3 py-2.5 text-right">
        <div className="up text-[11px]">T {formatINR(trade.target_price)}</div>
        <div className="down text-[11px]">SL {formatINR(trade.stop_loss)}</div>
      </td>

      {/* Source */}
      <td className="px-3 py-2.5">
        <Badge variant={trade.source === "AI" ? "info" : "default"}>{trade.source}</Badge>
      </td>

      {/* Exit actions — always visible on mobile, hover-reveal on desktop */}
      <td className="px-3 py-2.5">
        <div className="flex flex-col gap-1 items-end sm:opacity-60 sm:group-hover:opacity-100 transition-opacity">
          {/* Quick SL exit */}
          {trade.stop_loss > 0 && (
            <button
              onClick={() => onRequestClose(trade.trade_id, trade.stop_loss, desc)}
              disabled={isClosing}
              title="Close at Stop Loss"
              className="flex items-center gap-1 px-2 py-0.5 rounded text-[9px] bg-[var(--color-danger)]/15 text-[var(--color-danger)] border border-[var(--color-danger)]/25 hover:bg-[var(--color-danger)]/30 transition-colors disabled:opacity-40 whitespace-nowrap"
            >
              <ShieldAlert className="size-2.5" /> SL
            </button>
          )}
          {/* Quick T1 exit */}
          {trade.target_price > 0 && (
            <button
              onClick={() => onRequestClose(trade.trade_id, trade.target_price, desc)}
              disabled={isClosing}
              title="Close at Target 1"
              className="flex items-center gap-1 px-2 py-0.5 rounded text-[9px] bg-[var(--color-success)]/15 text-[var(--color-success)] border border-[var(--color-success)]/25 hover:bg-[var(--color-success)]/30 transition-colors disabled:opacity-40 whitespace-nowrap"
            >
              <Target className="size-2.5" /> T1
            </button>
          )}
          {/* Manual close */}
          <button
            onClick={() => onRequestClose(trade.trade_id, trade.current_price, desc)}
            disabled={isClosing}
            className="px-2 py-0.5 rounded text-[9px] bg-white/8 text-[var(--color-text-muted)] border border-white/15 hover:text-white hover:bg-white/12 transition-colors disabled:opacity-40 whitespace-nowrap"
          >
            {isClosing ? "…" : "Manual"}
          </button>
        </div>
      </td>
    </tr>
  );
}

// ── Expiry date helpers ───────────────────────────────────────────────────────

const MONTH_MAP: Record<string, string> = {
  Jan: "01", Feb: "02", Mar: "03", Apr: "04", May: "05", Jun: "06",
  Jul: "07", Aug: "08", Sep: "09", Oct: "10", Nov: "11", Dec: "12",
};
const MONTH_NAMES = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];

function expiryToISO(expiry: string): string {
  // "25-Jun-2025" → "2025-06-25"
  const [d, m, y] = expiry.split("-");
  const mm = MONTH_MAP[m];
  if (!mm || !y || !d) return "";
  return `${y}-${mm}-${d.padStart(2, "0")}`;
}

function isoToExpiry(iso: string): string {
  // "2025-06-25" → "25-Jun-2025"
  const [y, m, d] = iso.split("-");
  const name = MONTH_NAMES[parseInt(m, 10) - 1];
  if (!name || !y || !d) return "";
  return `${d}-${name}-${y}`;
}

function todayExpiry(): string {
  return isoToExpiry(new Date().toISOString().slice(0, 10));
}

// ── Trade Entry Form ──────────────────────────────────────────────────────────

function TradeEntryForm({ symbols }: { symbols: string[] }) {
  const qc = useQueryClient();
  const [form, setForm] = useState({
    symbol: "NIFTY",
    instrument_type: "CE",
    strike: "",
    expiry: todayExpiry(),
    action: "BUY",
    lots: "1",
    lot_size: String(getLotSize("NIFTY")),
    entry_price: "",
    target_price: "",
    stop_loss: "",
  });
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  const addMutation = useMutation({
    mutationFn: addPaperTrade,
    onSuccess: (res) => {
      setMsg({ ok: true, text: res.message });
      setForm((f) => ({ ...f, entry_price: "", target_price: "", stop_loss: "" }));
      qc.invalidateQueries({ queryKey: ["paper-trades"] });
      setTimeout(() => setMsg(null), 4000);
    },
    onError: (e) => {
      setMsg({ ok: false, text: String(e) });
      setTimeout(() => setMsg(null), 5000);
    },
  });

  const set = (k: string, v: string) => setForm((f) => {
    const next = { ...f, [k]: v };
    if (k === "symbol") next.lot_size = String(getLotSize(v));
    return next;
  });
  const lotSize = parseInt(form.lot_size) || getLotSize(form.symbol);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.entry_price || !form.lots) return;
    addMutation.mutate({
      symbol: form.symbol,
      instrument_type: form.instrument_type,
      strike: parseFloat(form.strike) || 0,
      expiry: form.expiry,
      action: form.action,
      lots: parseInt(form.lots) || 1,
      lot_size: lotSize,
      entry_price: parseFloat(form.entry_price) || 0,
      target_price: parseFloat(form.target_price) || 0,
      stop_loss: parseFloat(form.stop_loss) || 0,
      source: "MANUAL",
    });
  };

  const fieldCls = "h-8 px-2 w-full rounded border border-[var(--color-border)] bg-[var(--color-surface)] text-xs text-white focus:outline-none focus:border-[var(--color-primary)]";
  const labelCls = "text-[10px] uppercase tracking-wider text-[var(--color-text-muted)]";

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      {msg && (
        <div className={cn(
          "text-xs px-3 py-2 rounded border",
          msg.ok
            ? "border-[var(--color-success)]/40 bg-[var(--color-success)]/10 text-[var(--color-success)]"
            : "border-[var(--color-danger)]/40 bg-[var(--color-danger)]/10 text-[var(--color-danger)]",
        )}>
          {msg.text}
        </div>
      )}

      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
        <div>
          <div className={labelCls}>Symbol</div>
          <select value={form.symbol} onChange={(e) => set("symbol", e.target.value)} className={fieldCls}>
            {symbols.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>
        <div>
          <div className={labelCls}>Type</div>
          <select value={form.instrument_type} onChange={(e) => set("instrument_type", e.target.value)} className={fieldCls}>
            <option value="CE">CE (Call)</option>
            <option value="PE">PE (Put)</option>
            <option value="FUT">FUT (Futures)</option>
          </select>
        </div>
        <div>
          <div className={labelCls}>Action</div>
          <select value={form.action} onChange={(e) => set("action", e.target.value)} className={fieldCls}>
            <option value="BUY">BUY</option>
            <option value="SELL">SELL</option>
          </select>
        </div>
        <div>
          <div className={labelCls}>Strike</div>
          <input type="number" value={form.strike} onChange={(e) => set("strike", e.target.value)} placeholder="e.g. 24000" className={fieldCls} />
        </div>
        <div>
          <div className={labelCls}>Expiry</div>
          <input
            type="date"
            value={expiryToISO(form.expiry)}
            onChange={(e) => set("expiry", e.target.value ? isoToExpiry(e.target.value) : "")}
            className={cn(fieldCls, "[color-scheme:dark]")}
          />
        </div>
        <div>
          <div className={labelCls}>Lots</div>
          <input type="number" min="1" value={form.lots} onChange={(e) => set("lots", e.target.value)} className={fieldCls} />
        </div>
        <div>
          <div className={labelCls}>Lot Size</div>
          <input type="number" min="1" value={form.lot_size} onChange={(e) => set("lot_size", e.target.value)} className={fieldCls} />
        </div>
        <div>
          <div className={labelCls}>Entry Price (₹)</div>
          <input type="number" step="0.05" value={form.entry_price} onChange={(e) => set("entry_price", e.target.value)} placeholder="0.00" className={fieldCls} required />
        </div>
        <div>
          <div className={labelCls}>Target (₹)</div>
          <input type="number" step="0.05" value={form.target_price} onChange={(e) => set("target_price", e.target.value)} placeholder="0.00" className={fieldCls} />
        </div>
        <div>
          <div className={labelCls}>Stop Loss (₹)</div>
          <input type="number" step="0.05" value={form.stop_loss} onChange={(e) => set("stop_loss", e.target.value)} placeholder="0.00" className={fieldCls} />
        </div>
      </div>

      <div className="flex items-center justify-between">
        <div className="text-xs text-[var(--color-text-muted)]">
          {form.entry_price && form.lots
            ? `Est. margin: ${formatINR(parseFloat(form.entry_price) * lotSize * parseInt(form.lots || "1") * (form.action === "SELL" || form.instrument_type === "FUT" ? 1.5 : 1))}`
            : "Fill entry price and lots"}
        </div>
        <button
          type="submit"
          disabled={addMutation.isPending}
          className={cn(
            "px-5 py-2 rounded text-sm font-medium transition-colors",
            form.action === "BUY"
              ? "bg-[var(--color-success)] hover:bg-[var(--color-success)]/90 text-white"
              : "bg-[var(--color-danger)] hover:bg-[var(--color-danger)]/90 text-white",
            addMutation.isPending && "opacity-60 cursor-not-allowed",
          )}
        >
          {addMutation.isPending ? "Adding…" : `${form.action} ${form.lots}× ${form.symbol}`}
        </button>
      </div>
    </form>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function PaperTradePage() {
  const qc = useQueryClient();
  const [closingId,     setClosingId]     = useState<string | null>(null);
  const [exitDialog,    setExitDialog]    = useState<ExitDialogState | null>(null);
  const [confirmReset,  setConfirmReset]  = useState(false);
  const [refreshing,    setRefreshing]    = useState(false);
  const [refreshErrors, setRefreshErrors] = useState<PriceRefreshResult[]>([]);
  const [refreshMsg,    setRefreshMsg]    = useState<string | null>(null);
  const [mktInfo,       setMktInfo]       = useState(getMarketInfo());

  // Refresh market status every 60s
  useState(() => {
    const id = setInterval(() => setMktInfo(getMarketInfo()), 60_000);
    return () => clearInterval(id);
  });

  const portfolio = useQuery<PortfolioSummary>({
    queryKey: ["paper-trades", "portfolio"],
    queryFn: getPortfolioSummary,
    refetchInterval: 30_000,
  });

  const openTrades = useQuery<PaperTrade[]>({
    queryKey: ["paper-trades", "open"],
    queryFn: getOpenTrades,
    refetchInterval: 30_000,
  });

  const closedTrades = useQuery<PaperTrade[]>({
    queryKey: ["paper-trades", "closed"],
    queryFn: getClosedTrades,
    staleTime: 10_000,
  });

  const equityCurve = useQuery({
    queryKey: ["paper-trades", "equity-curve"],
    queryFn: getEquityCurve,
    staleTime: 10_000,
  });

  const symbolsQuery = useQuery<string[]>({
    queryKey: ["fno", "symbols"],
    queryFn: getFnoSymbols,
    staleTime: 10 * 60_000,
  });

  const allSymbols = useMemo(() => {
    const extra = (symbolsQuery.data ?? []).filter((s) => !INDEX_SYMBOLS.includes(s));
    return [...INDEX_SYMBOLS, ...extra.sort()];
  }, [symbolsQuery.data]);

  const closeMutation = useMutation({
    mutationFn: ({ id, price }: { id: string; price: number }) =>
      closePaperTrade(id, price),
    onSettled: () => {
      setClosingId(null);
      setExitDialog(null);
      qc.invalidateQueries({ queryKey: ["paper-trades"] });
    },
  });

  const ltpMutation = useMutation({
    mutationFn: ({ id, price }: { id: string; price: number }) =>
      updatePaperTradeLtp(id, price),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["paper-trades"] }),
  });

  const resetMutation = useMutation({
    mutationFn: () => resetPortfolio(),
    onSuccess: () => {
      setConfirmReset(false);
      qc.invalidateQueries({ queryKey: ["paper-trades"] });
    },
  });

  /** Open the exit-price dialog; pre-fill with the trade's current (live) price. */
  const handleRequestClose = (tradeId: string, currentPrice: number, desc: string) => {
    setExitDialog({ tradeId, tradeDesc: desc, suggestedPrice: currentPrice || 0 });
  };

  /** Called when user confirms the exit price in the dialog. */
  const handleConfirmClose = (tradeId: string, exitPrice: number) => {
    setClosingId(tradeId);
    closeMutation.mutate({ id: tradeId, price: exitPrice });
  };

  /** Fetch live/cached LTPs for all open positions; surface per-trade errors. */
  const handleRefreshPrices = async () => {
    setRefreshing(true);
    setRefreshErrors([]);
    setRefreshMsg(null);
    try {
      const results = await refreshPaperTradePrices();
      qc.invalidateQueries({ queryKey: ["paper-trades"] });
      const updated = results.filter((r) => r.price_source !== "none");
      const failed  = results.filter((r) => r.price_source === "none");
      setRefreshErrors(failed);
      if (updated.length > 0) {
        setRefreshMsg(`${updated.length} price${updated.length > 1 ? "s" : ""} updated (${updated.map(r => r.price_source).join(", ")})`);
      } else if (failed.length > 0) {
        setRefreshMsg(null); // errors shown in the table
      }
    } catch (err) {
      setRefreshMsg(`Refresh failed: ${String(err)}`);
    } finally {
      setRefreshing(false);
      setTimeout(() => { setRefreshMsg(null); setRefreshErrors([]); }, 12_000);
    }
  };

  const pnlHistogram = useMemo(() => {
    const closed = closedTrades.data ?? [];
    if (!closed.length) return [];
    const bins = new Map<string, number>();
    closed.forEach((t) => {
      const pnl = t.pnl_rs ?? 0;
      const bucket = pnl >= 0 ? "profit" : "loss";
      bins.set(bucket, (bins.get(bucket) ?? 0) + 1);
    });
    return [
      { name: "Profit", count: bins.get("profit") ?? 0, fill: "#1ec48a" },
      { name: "Loss", count: bins.get("loss") ?? 0, fill: "#ef5350" },
    ];
  }, [closedTrades.data]);

  return (
    <div className="space-y-5 max-w-[1400px] mx-auto">
      {/* Exit price dialog */}
      {exitDialog && (
        <ExitDialog
          state={exitDialog}
          onConfirm={handleConfirmClose}
          onCancel={() => setExitDialog(null)}
        />
      )}

      {/* Refresh result banner */}
      {(refreshMsg || refreshErrors.length > 0) && (
        <div className={cn(
          "rounded-lg border px-4 py-3 text-xs space-y-1",
          refreshErrors.length > 0 && !refreshMsg
            ? "border-amber-500/30 bg-amber-500/8 text-amber-300"
            : "border-[var(--color-success)]/30 bg-[var(--color-success)]/8 text-[var(--color-success)]",
        )}>
          {refreshMsg && <div>{refreshMsg}</div>}
          {refreshErrors.map((r) => (
            <div key={r.trade_id} className="text-amber-300">
              <span className="font-medium">{r.symbol}</span>: {r.error ?? "No market price available — click LTP to set manually."}
            </div>
          ))}
        </div>
      )}

      {/* Header */}
      <header className="flex items-end justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <FlaskConical className="size-5 text-[var(--color-primary)]" />
            <h1 className="text-xl font-semibold text-white">Paper Trade Terminal</h1>
          </div>
          <p className="text-xs text-[var(--color-text-muted)]">
            Virtual F&amp;O trading · no real money · ₹5L starting capital
          </p>
        </div>
        {/* Market status badge */}
        <div className={cn(
          "flex items-center gap-2 rounded-lg px-3 py-1.5 text-[11px] shrink-0",
          mktInfo.status === "open"    && "bg-emerald-500/10 border border-emerald-500/25",
          mktInfo.status === "preopen" && "bg-amber-500/10 border border-amber-500/25",
          (mktInfo.status === "closed" || mktInfo.status === "weekend") && "bg-slate-500/10 border border-slate-500/20",
        )}>
          <span className={cn(
            "size-2 rounded-full shrink-0",
            mktInfo.status === "open"    && "bg-emerald-400 animate-pulse",
            mktInfo.status === "preopen" && "bg-amber-400",
            (mktInfo.status === "closed" || mktInfo.status === "weekend") && "bg-slate-500",
          )} />
          <span className={cn("font-semibold", mktInfo.labelColor)}>{mktInfo.label}</span>
          <span className="text-[var(--color-text-muted)] hidden sm:block">{mktInfo.sessionNote}</span>
        </div>
        <div className="flex items-center gap-2">
          {openTrades.isFetching && (
            <span className="text-[10px] text-[var(--color-text-muted)] animate-pulse">refreshing…</span>
          )}
          {/* Live price refresh button (P1-5) */}
          <button
            onClick={handleRefreshPrices}
            disabled={refreshing || (openTrades.data ?? []).length === 0}
            title="Fetch live LTP from NSE for all open positions"
            className="flex items-center gap-1 px-3 py-1.5 rounded border border-[var(--color-border)] text-xs text-[var(--color-text-muted)] hover:text-white transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <RefreshCw className={cn("size-3.5", refreshing && "animate-spin")} />
            {refreshing ? "Refreshing…" : "Refresh Prices"}
          </button>
          {confirmReset ? (
            <div className="flex items-center gap-2">
              <span className="text-xs text-[var(--color-danger)]">Reset all trades?</span>
              <button
                onClick={() => resetMutation.mutate()}
                className="px-2 py-1 text-xs rounded bg-[var(--color-danger)] text-white"
              >
                Yes, reset
              </button>
              <button
                onClick={() => setConfirmReset(false)}
                className="px-2 py-1 text-xs rounded border border-[var(--color-border)] text-[var(--color-text-muted)]"
              >
                Cancel
              </button>
            </div>
          ) : (
            <button
              onClick={() => setConfirmReset(true)}
              className="flex items-center gap-1 px-3 py-1.5 rounded border border-[var(--color-border)] text-xs text-[var(--color-text-muted)] hover:text-white transition-colors"
            >
              <Trash2 className="size-3.5" /> Reset Portfolio
            </button>
          )}
        </div>
      </header>

      {/* Portfolio summary */}
      <PortfolioHeader data={portfolio.data} loading={portfolio.isLoading} />

      {/* Tabs */}
      <Tabs defaultValue="open">
        <TabsList>
          <TabsTrigger value="open">
            Open Positions ({openTrades.data?.length ?? 0})
          </TabsTrigger>
          <TabsTrigger value="entry">New Trade</TabsTrigger>
          <TabsTrigger value="history">
            History ({closedTrades.data?.length ?? 0})
          </TabsTrigger>
          <TabsTrigger value="analytics">Analytics</TabsTrigger>
        </TabsList>

        {/* ── Open Positions ── */}
        <TabsContent value="open">
          <Card>
            <CardContent className="p-0 overflow-x-auto">
              {openTrades.isLoading ? (
                <div className="p-4 space-y-2">
                  {[0, 1, 2].map((i) => <Skeleton key={i} className="h-10 w-full" />)}
                </div>
              ) : (
                <table className="w-full text-xs min-w-[920px]">
                  <thead className="border-b border-[var(--color-border)] bg-[var(--color-surface-2)]">
                    <tr className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)]">
                      <th className="text-left px-3 py-2.5">Symbol</th>
                      <th className="text-left px-3 py-2.5">Side</th>
                      <th className="text-left px-3 py-2.5">Expiry</th>
                      <th className="text-right px-3 py-2.5">Qty</th>
                      <th className="text-right px-3 py-2.5">Entry</th>
                      <th className="text-right px-3 py-2.5">Invested</th>
                      <th className="text-right px-3 py-2.5">LTP</th>
                      <th className="text-right px-3 py-2.5">P&amp;L</th>
                      <th className="text-right px-3 py-2.5">Tgt / SL</th>
                      <th className="text-left px-3 py-2.5">Source</th>
                      <th className="text-right px-3 py-2.5">Exit →</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(openTrades.data ?? []).map((t) => (
                      <TradeRow
                        key={t.trade_id}
                        trade={t}
                        onRequestClose={handleRequestClose}
                        onUpdateLtp={(id, price) => ltpMutation.mutate({ id, price })}
                        closing={closingId}
                      />
                    ))}
                    {(openTrades.data ?? []).length === 0 && (
                      <tr>
                        <td colSpan={11} className="px-4 py-10 text-center text-sm text-[var(--color-text-muted)]">
                          No open positions · use New Trade tab to add one
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* ── New Trade Entry ── */}
        <TabsContent value="entry">
          <Card>
            <CardHeader>
              <CardTitle>Add Paper Trade</CardTitle>
            </CardHeader>
            <CardContent>
              <TradeEntryForm symbols={allSymbols} />
            </CardContent>
          </Card>
        </TabsContent>

        {/* ── History ── */}
        <TabsContent value="history">
          <Card>
            <CardContent className="p-0 overflow-x-auto">
              {closedTrades.isLoading ? (
                <div className="p-4 space-y-2">
                  {[0, 1, 2].map((i) => <Skeleton key={i} className="h-10 w-full" />)}
                </div>
              ) : (
                <table className="w-full text-xs min-w-[800px]">
                  <thead className="border-b border-[var(--color-border)] bg-[var(--color-surface-2)]">
                    <tr className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)]">
                      <th className="text-left px-3 py-2.5">Symbol</th>
                      <th className="text-left px-3 py-2.5">Side</th>
                      <th className="text-right px-3 py-2.5">Entry</th>
                      <th className="text-right px-3 py-2.5">Exit</th>
                      <th className="text-right px-3 py-2.5">P&amp;L</th>
                      <th className="text-right px-3 py-2.5">P&amp;L%</th>
                      <th className="text-left px-3 py-2.5">Reason</th>
                      <th className="text-right px-3 py-2.5">Source</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(closedTrades.data ?? []).slice().reverse().map((t) => (
                      <tr
                        key={t.trade_id}
                        className="border-b border-[var(--color-border)] hover:bg-[var(--color-surface-2)]/50 tnum"
                      >
                        <td className="px-3 py-2.5">
                          <div className="font-medium text-white">{t.symbol}</div>
                          <div className="text-[var(--color-text-muted)]">{t.strike > 0 ? `${t.strike} ` : ""}{t.instrument_type}</div>
                        </td>
                        <td className="px-3 py-2.5">
                          <Badge variant={t.action === "BUY" ? "success" : "danger"}>{t.action}</Badge>
                        </td>
                        <td className="px-3 py-2.5 text-right text-white">{formatINR(t.entry_price)}</td>
                        <td className="px-3 py-2.5 text-right text-white">{formatINR(t.exit_price ?? 0)}</td>
                        <td className={cn("px-3 py-2.5 text-right font-medium", pnlClass(t.pnl_rs ?? 0))}>
                          {(t.pnl_rs ?? 0) >= 0 ? "+" : ""}{formatINR(t.pnl_rs ?? 0)}
                        </td>
                        <td className={cn("px-3 py-2.5 text-right font-medium", pnlClass(t.pnl_pct ?? 0))}>
                          {formatPct(t.pnl_pct ?? 0, { sign: true })}
                        </td>
                        <td className="px-3 py-2.5 text-[var(--color-text-muted)]">
                          {(t.exit_reason ?? "").replace(/_/g, " ")}
                        </td>
                        <td className="px-3 py-2.5 text-right">
                          <Badge variant={t.source === "AI" ? "info" : "default"}>{t.source}</Badge>
                        </td>
                      </tr>
                    ))}
                    {(closedTrades.data ?? []).length === 0 && (
                      <tr>
                        <td colSpan={8} className="px-4 py-10 text-center text-sm text-[var(--color-text-muted)]">
                          No closed trades yet
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* ── Analytics ── */}
        <TabsContent value="analytics">
          <div className="space-y-4">
            {/* Equity curve */}
            <Card>
              <CardHeader>
                <CardTitle>Equity Curve</CardTitle>
              </CardHeader>
              <CardContent>
                {equityCurve.isLoading ? (
                  <Skeleton className="h-56 w-full" />
                ) : (equityCurve.data ?? []).length < 2 ? (
                  <div className="h-56 flex items-center justify-center text-sm text-[var(--color-text-muted)]">
                    Close at least 2 trades to see the equity curve
                  </div>
                ) : (
                  <div style={{ width: "100%", height: 220 }}>
                    <ResponsiveContainer>
                      <LineChart data={equityCurve.data} margin={{ top: 8, right: 16, bottom: 0, left: 8 }}>
                        <XAxis dataKey="date" tick={{ fill: "#94a3b8", fontSize: 10 }} interval="preserveStartEnd" />
                        <YAxis
                          tick={{ fill: "#94a3b8", fontSize: 10 }}
                          tickFormatter={(v: number) => `₹${v >= 0 ? "" : ""}${Math.abs(v) >= 1000 ? `${(v / 1000).toFixed(0)}K` : v.toFixed(0)}`}
                          width={60}
                        />
                        <Tooltip
                          contentStyle={{ background: "#131822", border: "1px solid #232a3a", fontSize: 12, color: "#fff" }}
                          formatter={(v: number) => [formatINR(v), "Cumulative P&L"]}
                        />
                        <ReferenceLine y={0} stroke="#475569" strokeDasharray="3 3" />
                        <Line
                          type="monotone"
                          dataKey="cumulative_pnl"
                          stroke="var(--color-primary)"
                          strokeWidth={2}
                          dot={false}
                          activeDot={{ r: 4 }}
                        />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Win/Loss bar */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <Card>
                <CardHeader>
                  <CardTitle>Win / Loss Distribution</CardTitle>
                </CardHeader>
                <CardContent>
                  {pnlHistogram.length > 0 ? (
                    <div style={{ width: "100%", height: 160 }}>
                      <ResponsiveContainer>
                        <BarChart data={pnlHistogram} margin={{ top: 8, right: 8, bottom: 0, left: 8 }}>
                          <XAxis dataKey="name" tick={{ fill: "#94a3b8", fontSize: 11 }} />
                          <YAxis tick={{ fill: "#94a3b8", fontSize: 10 }} />
                          <Tooltip
                            contentStyle={{ background: "#131822", border: "1px solid #232a3a", fontSize: 12, color: "#fff" }}
                          />
                          <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                            {pnlHistogram.map((e, i) => (
                              <Cell key={i} fill={e.fill} />
                            ))}
                          </Bar>
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  ) : (
                    <div className="h-40 flex items-center justify-center text-sm text-[var(--color-text-muted)]">
                      No closed trades yet
                    </div>
                  )}
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle>Performance Summary</CardTitle>
                </CardHeader>
                <CardContent className="space-y-2 text-xs">
                  {portfolio.data ? (
                    <>
                      <div className="flex justify-between">
                        <span className="text-[var(--color-text-muted)]">Initial Capital</span>
                        <span className="text-white tnum">{formatINR(portfolio.data.initial_capital)}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-[var(--color-text-muted)]">Closed P&amp;L</span>
                        <span className={cn("tnum font-medium", pnlClass(portfolio.data.closed_pnl ?? 0))}>
                          {(portfolio.data.closed_pnl ?? 0) >= 0 ? "+" : ""}{formatINR(portfolio.data.closed_pnl ?? 0)}
                        </span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-[var(--color-text-muted)]">Open P&amp;L</span>
                        <span className={cn("tnum font-medium", pnlClass(portfolio.data.open_pnl ?? 0))}>
                          {(portfolio.data.open_pnl ?? 0) >= 0 ? "+" : ""}{formatINR(portfolio.data.open_pnl ?? 0)}
                        </span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-[var(--color-text-muted)]">Win Rate</span>
                        <span className="text-white tnum">{portfolio.data.win_rate?.toFixed(1)}%</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-[var(--color-text-muted)]">Profit Factor</span>
                        <span className={cn("tnum font-medium", (portfolio.data.profit_factor ?? 0) >= 1 ? "up" : "down")}>
                          {portfolio.data.profit_factor?.toFixed(2)}×
                        </span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-[var(--color-text-muted)]">Total Trades</span>
                        <span className="text-white tnum">{portfolio.data.closed_trades_count}</span>
                      </div>
                    </>
                  ) : (
                    <div className="text-[var(--color-text-muted)]">No data</div>
                  )}
                </CardContent>
              </Card>
            </div>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}
