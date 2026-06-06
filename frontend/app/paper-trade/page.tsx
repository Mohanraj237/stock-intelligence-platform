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
} from "@/lib/fno-api";
import type { PaperTrade, PortfolioSummary } from "@/lib/fno-types";
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
import { FlaskConical, Trash2 } from "lucide-react";

// ── Helpers ───────────────────────────────────────────────────────────────────

function pnlClass(n: number) {
  return n > 0 ? "up" : n < 0 ? "down" : "text-[var(--color-text-muted)]";
}

// ── Portfolio Header ──────────────────────────────────────────────────────────

function PortfolioHeader({ data, loading }: { data?: PortfolioSummary; loading: boolean }) {
  if (loading || !data) {
    return (
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        {[0, 1, 2, 3].map((i) => (
          <Card key={i}>
            <CardContent className="p-4 space-y-2">
              <Skeleton className="h-3 w-24" />
              <Skeleton className="h-7 w-32" />
            </CardContent>
          </Card>
        ))}
      </div>
    );
  }

  const capitalPct = data.initial_capital > 0
    ? (data.available_capital / data.initial_capital) * 100
    : 100;

  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
      <Card>
        <CardContent className="p-4">
          <div className="text-[11px] uppercase tracking-wider text-[var(--color-text-muted)] mb-1">Total Equity</div>
          <div className="text-2xl font-bold tnum text-white">{formatINR(data.total_equity ?? data.available_capital + data.deployed_capital)}</div>
          <div className="mt-1 text-[11px] text-[var(--color-text-muted)]">
            Avail: {formatINR(data.available_capital)} · Deployed: {formatINR(data.deployed_capital)}
          </div>
          <div className="mt-2 h-1.5 rounded-full bg-[var(--color-surface-2)]">
            <div
              className="h-full rounded-full bg-[var(--color-primary)] transition-all"
              style={{ width: `${Math.max(2, capitalPct)}%` }}
            />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="p-4">
          <div className="text-[11px] uppercase tracking-wider text-[var(--color-text-muted)] mb-1">Total P&amp;L</div>
          <div className={cn("text-2xl font-bold tnum", pnlClass(data.total_pnl))}>
            {data.total_pnl >= 0 ? "+" : ""}{formatINR(data.total_pnl)}
          </div>
          <div className={cn("text-[11px]", pnlClass(data.total_pnl_pct))}>
            {data.total_pnl_pct >= 0 ? "+" : ""}{data.total_pnl_pct?.toFixed(2)}%
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="p-4">
          <div className="text-[11px] uppercase tracking-wider text-[var(--color-text-muted)] mb-1">Win Rate</div>
          <div className="text-2xl font-bold tnum text-white">{data.win_rate?.toFixed(1)}%</div>
          <div className="text-[11px] text-[var(--color-text-muted)]">
            {data.closed_trades_count} closed · {data.open_trades_count} open
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="p-4">
          <div className="text-[11px] uppercase tracking-wider text-[var(--color-text-muted)] mb-1">Profit Factor</div>
          <div className={cn("text-2xl font-bold tnum", (data.profit_factor ?? 0) >= 1.5 ? "up" : "down")}>
            {data.profit_factor?.toFixed(2)}×
          </div>
          <div className="text-[11px] text-[var(--color-text-muted)]">
            Open P&amp;L: {formatINR(data.open_pnl)}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

// ── Open Positions ────────────────────────────────────────────────────────────

function TradeRow({
  trade,
  onClose,
  closing,
}: {
  trade: PaperTrade;
  onClose: (id: string) => void;
  closing: string | null;
}) {
  const pnl = trade.pnl_rs ?? 0;
  const isClosing = closing === trade.trade_id;

  return (
    <tr className="border-b border-[var(--color-border)] hover:bg-[var(--color-surface-2)]/50 text-xs tnum">
      <td className="px-3 py-2.5">
        <div className="font-medium text-white">{trade.symbol}</div>
        <div className="text-[var(--color-text-muted)]">
          {trade.strike > 0 ? `${trade.strike} ` : ""}{trade.instrument_type}
        </div>
      </td>
      <td className="px-3 py-2.5">
        <Badge variant={trade.action === "BUY" ? "success" : "danger"}>{trade.action}</Badge>
      </td>
      <td className="px-3 py-2.5 text-[var(--color-text-muted)]">{trade.expiry}</td>
      <td className="px-3 py-2.5 text-right text-white">{trade.lots}×{trade.lot_size}</td>
      <td className="px-3 py-2.5 text-right text-white">{formatINR(trade.entry_price)}</td>
      <td className="px-3 py-2.5 text-right text-white">{formatINR(trade.current_price)}</td>
      <td className={cn("px-3 py-2.5 text-right font-medium", pnlClass(pnl))}>
        {pnl >= 0 ? "+" : ""}{formatINR(pnl)}
        <div className="text-[10px]">{trade.pnl_pct >= 0 ? "+" : ""}{trade.pnl_pct?.toFixed(1)}%</div>
      </td>
      <td className="px-3 py-2.5 text-right text-[var(--color-text-muted)]">
        <div className="up">{formatINR(trade.target_price)}</div>
        <div className="down">{formatINR(trade.stop_loss)}</div>
      </td>
      <td className="px-3 py-2.5 text-right">
        <Badge variant={trade.source === "AI" ? "info" : "default"}>{trade.source}</Badge>
      </td>
      <td className="px-3 py-2.5 text-right">
        <button
          onClick={() => onClose(trade.trade_id)}
          disabled={isClosing}
          className="px-2 py-1 rounded text-[10px] bg-[var(--color-danger)]/20 text-[var(--color-danger)] border border-[var(--color-danger)]/30 hover:bg-[var(--color-danger)]/30 transition-colors disabled:opacity-50"
        >
          {isClosing ? "…" : "Close"}
        </button>
      </td>
    </tr>
  );
}

// ── Trade Entry Form ──────────────────────────────────────────────────────────

function TradeEntryForm({ symbols }: { symbols: string[] }) {
  const qc = useQueryClient();
  const [form, setForm] = useState({
    symbol: "NIFTY",
    instrument_type: "CE",
    strike: "",
    expiry: "",
    action: "BUY",
    lots: "1",
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

  const set = (k: string, v: string) => setForm((f) => ({ ...f, [k]: v }));
  const lotSize = getLotSize(form.symbol);

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
            {symbols.slice(0, 50).map((s) => <option key={s} value={s}>{s}</option>)}
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
          <input type="text" value={form.expiry} onChange={(e) => set("expiry", e.target.value)} placeholder="27-Mar-2025" className={fieldCls} />
        </div>
        <div>
          <div className={labelCls}>Lots · lot size: {lotSize}</div>
          <input type="number" min="1" value={form.lots} onChange={(e) => set("lots", e.target.value)} className={fieldCls} />
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
  const [closingId, setClosingId] = useState<string | null>(null);
  const [confirmReset, setConfirmReset] = useState(false);

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
      qc.invalidateQueries({ queryKey: ["paper-trades"] });
    },
  });

  const resetMutation = useMutation({
    mutationFn: () => resetPortfolio(),
    onSuccess: () => {
      setConfirmReset(false);
      qc.invalidateQueries({ queryKey: ["paper-trades"] });
    },
  });

  const handleClose = (tradeId: string) => {
    const trade = (openTrades.data ?? []).find((t) => t.trade_id === tradeId);
    if (!trade) return;
    setClosingId(tradeId);
    closeMutation.mutate({ id: tradeId, price: trade.current_price || trade.entry_price });
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
      {/* Header */}
      <header className="flex items-end justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <FlaskConical className="size-5 text-[var(--color-primary)]" />
            <h1 className="text-xl font-semibold text-white">Paper Trade Terminal</h1>
          </div>
          <p className="text-xs text-[var(--color-text-muted)]">
            Virtual F&amp;O trading · no real money · ₹5L starting capital · live P&amp;L refresh 30s
          </p>
        </div>
        <div className="flex items-center gap-2">
          {openTrades.isFetching && (
            <span className="text-[10px] text-[var(--color-text-muted)] animate-pulse">refreshing…</span>
          )}
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
                <table className="w-full text-xs min-w-[800px]">
                  <thead className="border-b border-[var(--color-border)] bg-[var(--color-surface-2)]">
                    <tr className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)]">
                      <th className="text-left px-3 py-2.5">Symbol</th>
                      <th className="text-left px-3 py-2.5">Side</th>
                      <th className="text-left px-3 py-2.5">Expiry</th>
                      <th className="text-right px-3 py-2.5">Qty</th>
                      <th className="text-right px-3 py-2.5">Entry</th>
                      <th className="text-right px-3 py-2.5">LTP</th>
                      <th className="text-right px-3 py-2.5">P&amp;L</th>
                      <th className="text-right px-3 py-2.5">Tgt/SL</th>
                      <th className="text-right px-3 py-2.5">Source</th>
                      <th className="text-right px-3 py-2.5">Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(openTrades.data ?? []).map((t) => (
                      <TradeRow key={t.trade_id} trade={t} onClose={handleClose} closing={closingId} />
                    ))}
                    {(openTrades.data ?? []).length === 0 && (
                      <tr>
                        <td colSpan={10} className="px-4 py-10 text-center text-sm text-[var(--color-text-muted)]">
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
