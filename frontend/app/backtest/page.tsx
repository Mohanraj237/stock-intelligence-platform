"use client";
import { useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { TestTube2, Trophy, AlertTriangle, Info } from "lucide-react";
import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Table, THead, TBody, TR, TH, TD } from "@/components/ui/table";
import { EmptyState, ErrorState } from "@/components/ui/empty-state";
import { Badge } from "@/components/ui/badge";
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from "@/components/ui/select";
import { UniverseSelect } from "@/components/common/universe-select";
import { PageHeader } from "@/components/common/page-header";
import { ScanProgressCard, type ScanProgress } from "@/components/common/scan-progress";
import { KPI } from "@/components/common/kpi";
import { formatNum, formatPct, trendClass } from "@/lib/utils";
import { streamPost } from "@/lib/sse";
import {
  ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip,
  BarChart, Bar, Cell, ReferenceLine,
} from "recharts";
import { toast } from "sonner";

interface BacktestApiResult {
  win_rate: number; avg_return: number; expectancy: number;
  profit_factor: number; max_drawdown: number; avg_holding_days: number;
  avg_winner: number; avg_loser: number; best_winner: number; worst_loser: number;
  total_trades: number;
  equity_curve: number[];
  trades: { symbol: string; entry_date: string; exit_date: string; entry_price: number; exit_price: number; return_pct: number; bars_held: number; exit_reason: string }[];
  verdict: string; audit_log: string[]; duration_ms: number;
}

export default function BacktestPage() {
  const lib = useQuery({ queryKey: ["pattern-library"], queryFn: api.patternLibrary });
  const [f, setF] = useState({
    universe: "NIFTY 50",
    pattern_name: "Bull Flag",
    period: "2y",
    max_symbols: "25",
    min_confidence: "60",
    max_holding_bars: "30",
    step_size: "5",
    rolling_window: "120",
  });
  const upd = (k: string, v: string) => setF({ ...f, [k]: v });

  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState<ScanProgress>({ done: 0, total: 0 });
  const [data, setData] = useState<BacktestApiResult | null>(null);
  const [runError, setRunError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const startRun = async () => {
    setRunning(true); setData(null); setRunError(null);
    setProgress({ done: 0, total: 0 });
    const ctl = new AbortController();
    abortRef.current = ctl;
    await streamPost<BacktestApiResult>("/api/backtests/run/stream", {
      universe: f.universe, pattern_name: f.pattern_name, period: f.period,
      max_symbols: Number(f.max_symbols), min_confidence: Number(f.min_confidence),
      max_holding_bars: Number(f.max_holding_bars), step_size: Number(f.step_size),
      rolling_window: Number(f.rolling_window),
    }, {
      onStart:    (e) => setProgress({ done: 0, total: e.total ?? 0, current: "" }),
      onProgress: (e) => setProgress({ done: e.done ?? 0, total: e.total ?? 0, current: e.current, elapsedMs: e.elapsed_ms }),
      onResult:   (r) => setData(r),
      onDone:     () => setRunning(false),
      onError:    (err) => { setRunError(err.message); setRunning(false); toast.error(err.message); },
      signal:     ctl.signal,
    });
  };

  const cancelRun = () => { abortRef.current?.abort(); setRunning(false); setRunError("Cancelled"); };

  // Compatibility shim for the rest of the page (was `m.data`/`m.isPending`)
  const m = { data, isPending: running, error: runError ? new Error(runError) : null, mutate: startRun };

  // Bucket return distribution into histogram bins
  const histogram = useMemo(() => {
    const trades = m.data?.trades ?? [];
    if (trades.length === 0) return [];
    const buckets = [-30, -20, -15, -10, -5, -2, 0, 2, 5, 10, 15, 20, 30];
    const out = buckets.slice(0, -1).map((lo, i) => {
      const hi = buckets[i + 1];
      const label = `${lo}/${hi}`;
      const count = trades.filter((t) => t.return_pct > lo && t.return_pct <= hi).length;
      return { label, count, mid: (lo + hi) / 2 };
    });
    return out;
  }, [m.data]);

  const exitReasons = useMemo(() => {
    const trades = m.data?.trades ?? [];
    const map: Record<string, number> = {};
    for (const t of trades) {
      const k = (t.exit_reason || "unknown").toLowerCase();
      map[k] = (map[k] ?? 0) + 1;
    }
    return Object.entries(map).map(([reason, count]) => ({ reason, count, pct: (count / Math.max(1, trades.length)) * 100 }));
  }, [m.data]);

  const topWinners = useMemo(() => [...(m.data?.trades ?? [])].sort((a, b) => b.return_pct - a.return_pct).slice(0, 5), [m.data]);
  const topLosers  = useMemo(() => [...(m.data?.trades ?? [])].sort((a, b) => a.return_pct - b.return_pct).slice(0, 5), [m.data]);

  const aliasNote = m.data?.audit_log?.find((l) => l.startsWith("Resolved pattern:"));

  return (
    <div className="max-w-[1400px] mx-auto space-y-5">
      <PageHeader title="Backtest" subtitle="Walk-forward historical pattern backtesting." />

      <Card>
        <CardHeader><CardTitle>Configure</CardTitle></CardHeader>
        <CardContent>
          <form onSubmit={(e) => { e.preventDefault(); m.mutate(); }} className="grid md:grid-cols-4 gap-3 items-end">
            <div className="space-y-1">
              <Label>Universe</Label>
              <UniverseSelect value={f.universe} onChange={(v) => upd("universe", v)} />
            </div>
            <div className="space-y-1">
              <Label>Pattern</Label>
              <Select value={f.pattern_name} onValueChange={(v) => upd("pattern_name", v)}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {(lib.data ?? []).map((p) => (
                    <SelectItem key={p.name} value={p.name}>{p.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label>Period</Label>
              <Select value={f.period} onValueChange={(v) => upd("period", v)}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {["1y", "2y", "5y", "max"].map((p) => <SelectItem key={p} value={p}>{p}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label>Max symbols</Label>
              <Input type="number" min={1} max={500} value={f.max_symbols} onChange={(e) => upd("max_symbols", e.target.value)} />
            </div>
            <div className="space-y-1">
              <Label>Min confidence</Label>
              <Input type="number" min={0} max={100} value={f.min_confidence} onChange={(e) => upd("min_confidence", e.target.value)} />
            </div>
            <div className="space-y-1">
              <Label>Max holding (bars)</Label>
              <Input type="number" min={1} max={500} value={f.max_holding_bars} onChange={(e) => upd("max_holding_bars", e.target.value)} />
            </div>
            <div className="space-y-1">
              <Label>Step size</Label>
              <Input type="number" min={1} max={50} value={f.step_size} onChange={(e) => upd("step_size", e.target.value)} />
            </div>
            <Button type="submit" disabled={m.isPending}>
              {m.isPending ? "Running…" : "Run backtest"}
            </Button>
          </form>
        </CardContent>
      </Card>

      {running && <ScanProgressCard progress={progress} onCancel={cancelRun} label="Backtesting" />}
      {m.error && !running && <ErrorState message={(m.error as Error).message} retry={() => m.mutate()} />}
      {m.data && (
        <>
          {aliasNote && (
            <div className="rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-xs muted flex items-center gap-2">
              <Info className="size-3.5 shrink-0" />
              {aliasNote}
            </div>
          )}

          {/* Verdict + headline KPIs */}
          <Card>
            <CardContent className="p-4">
              <div className="flex flex-wrap items-center justify-between gap-4">
                <div className="flex items-center gap-3">
                  <Badge variant={
                    m.data.verdict?.includes("Tradeable") ? "success" :
                    m.data.verdict?.includes("Marginal") ? "warning" :
                    m.data.verdict?.includes("Insufficient") ? "info" : "danger"
                  }>{m.data.verdict || "—"}</Badge>
                  <div>
                    <div className="text-xs muted">Pattern · {f.pattern_name}</div>
                    <div className="text-sm font-medium text-white">{m.data.total_trades} trades on {f.universe} over {f.period}</div>
                  </div>
                </div>
                <div className="text-xs muted tnum">Ran in {(m.data.duration_ms / 1000).toFixed(1)}s</div>
              </div>
            </CardContent>
          </Card>

          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
            <KPI label="Trades" value={m.data.total_trades} />
            <KPI label="Win rate" value={`${m.data.win_rate.toFixed(1)}%`} trend={m.data.win_rate >= 50 ? "up" : "down"} />
            <KPI label="Avg return" value={formatPct(m.data.avg_return, { sign: true })} trend={m.data.avg_return >= 0 ? "up" : "down"} />
            <KPI label="Expectancy" value={m.data.expectancy.toFixed(2)} trend={m.data.expectancy >= 0 ? "up" : "down"} />
            <KPI label="Profit factor" value={m.data.profit_factor.toFixed(2)} trend={m.data.profit_factor >= 1 ? "up" : "down"} />
            <KPI label="Max drawdown" value={formatPct(m.data.max_drawdown)} trend="down" />
            <KPI label="Avg winner" value={formatPct(m.data.avg_winner, { sign: true })} trend="up" />
            <KPI label="Avg loser"  value={formatPct(m.data.avg_loser,  { sign: true })} trend="down" />
            <KPI label="Best winner" value={formatPct(m.data.best_winner, { sign: true })} trend="up" />
            <KPI label="Worst loser" value={formatPct(m.data.worst_loser, { sign: true })} trend="down" />
            <KPI label="Avg hold" value={`${m.data.avg_holding_days.toFixed(1)} bars`} />
          </div>

          {/* Equity curve + return distribution side by side */}
          <div className="grid lg:grid-cols-2 gap-4">
            <Card>
              <CardHeader><CardTitle>Equity curve · 1% bet sizing</CardTitle></CardHeader>
              <CardContent>
                {!m.data.equity_curve?.length ? <EmptyState title="No equity data" /> : (
                  <div style={{ width: "100%", height: 280 }}>
                    <ResponsiveContainer>
                      <LineChart data={m.data.equity_curve.map((v, i) => ({ trade: i, equity: v }))}>
                        <XAxis dataKey="trade" tick={{ fill: "#94a3b8", fontSize: 10 }} label={{ value: "Trade #", position: "insideBottom", offset: -5, fill: "#94a3b8", fontSize: 10 }} />
                        <YAxis tick={{ fill: "#94a3b8", fontSize: 10 }} tickFormatter={(v) => `${(v >= 0 ? "+" : "")}${v.toFixed(0)}%`} />
                        <ReferenceLine y={0} stroke="#475569" strokeDasharray="2 2" />
                        <Tooltip
                          contentStyle={{ background: "#131822", border: "1px solid #232a3a", fontSize: 12, color: "#fff" }}
                          formatter={(v: number) => [`${v >= 0 ? "+" : ""}${v.toFixed(2)}%`, "Equity"]}
                        />
                        <Line type="monotone" dataKey="equity" stroke="#1ec48a" strokeWidth={2} dot={false} />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                )}
              </CardContent>
            </Card>
            <Card>
              <CardHeader><CardTitle>Return distribution</CardTitle></CardHeader>
              <CardContent>
                {histogram.length === 0 ? <EmptyState title="No trades to bucket" /> : (
                  <div style={{ width: "100%", height: 280 }}>
                    <ResponsiveContainer>
                      <BarChart data={histogram}>
                        <XAxis dataKey="label" tick={{ fill: "#94a3b8", fontSize: 9 }} interval={0} angle={-30} textAnchor="end" height={48} />
                        <YAxis tick={{ fill: "#94a3b8", fontSize: 10 }} allowDecimals={false} />
                        <Tooltip
                          contentStyle={{ background: "#131822", border: "1px solid #232a3a", fontSize: 12, color: "#fff" }}
                          formatter={(v: number) => [v, "Trades"]}
                          labelFormatter={(l) => `Return % bin: ${l}`}
                        />
                        <Bar dataKey="count">
                          {histogram.map((b, i) => (
                            <Cell key={i} fill={b.mid >= 0 ? "#1ec48a" : "#ef5350"} />
                          ))}
                        </Bar>
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                )}
              </CardContent>
            </Card>
          </div>

          {/* Exit reason breakdown */}
          {exitReasons.length > 0 && (
            <Card>
              <CardHeader><CardTitle>Exit reasons</CardTitle></CardHeader>
              <CardContent>
                <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3">
                  {exitReasons.map((r) => (
                    <div key={r.reason} className="rounded-md border border-[var(--color-border)] bg-[var(--color-surface-2)]/50 p-3">
                      <div className="text-[11px] muted capitalize">{r.reason}</div>
                      <div className="mt-1 flex items-baseline gap-2">
                        <span className="text-lg font-semibold tnum text-white">{r.count}</span>
                        <span className="text-xs muted tnum">({r.pct.toFixed(0)}%)</span>
                      </div>
                      <div className="mt-2 h-1.5 rounded-full bg-[var(--color-bg)] overflow-hidden">
                        <div className={`h-full ${r.reason.includes("target") ? "bg-[var(--color-success)]" : r.reason.includes("stop") ? "bg-[var(--color-danger)]" : "bg-[var(--color-text-muted)]"}`} style={{ width: `${r.pct}%` }} />
                      </div>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}

          {/* Top winners + top losers */}
          <div className="grid lg:grid-cols-2 gap-4">
            <Card>
              <CardHeader><CardTitle className="flex items-center gap-2"><Trophy className="size-4 up" /> Top 5 winners</CardTitle></CardHeader>
              <CardContent className="p-0"><WinnersLosersTable rows={topWinners} positive /></CardContent>
            </Card>
            <Card>
              <CardHeader><CardTitle className="flex items-center gap-2"><AlertTriangle className="size-4 down" /> Top 5 losers</CardTitle></CardHeader>
              <CardContent className="p-0"><WinnersLosersTable rows={topLosers} positive={false} /></CardContent>
            </Card>
          </div>

          {/* Full trade log */}
          <Card>
            <CardHeader>
              <CardTitle>
                Trade log · showing {Math.min(100, m.data.trades.length)} of {m.data.trades.length}
              </CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              {!m.data.trades.length ? (
                <div className="p-4"><EmptyState icon={TestTube2} title="No trades generated" description="Try a longer period, lower confidence, or a larger universe." /></div>
              ) : (
                <Table>
                  <THead><TR>
                    <TH>#</TH>
                    <TH>Symbol</TH>
                    <TH>Entry date</TH>
                    <TH>Exit date</TH>
                    <TH className="text-right">Entry ₹</TH>
                    <TH className="text-right">Exit ₹</TH>
                    <TH className="text-right">Return %</TH>
                    <TH className="text-right">Bars</TH>
                    <TH>Exit reason</TH>
                  </TR></THead>
                  <TBody>
                    {m.data.trades.slice(0, 100).map((t, i) => (
                      <TR key={i}>
                        <TD className="text-xs muted tnum">{i + 1}</TD>
                        <TD className="font-medium text-white">{t.symbol}</TD>
                        <TD className="text-xs muted tnum">{t.entry_date}</TD>
                        <TD className="text-xs muted tnum">{t.exit_date}</TD>
                        <TD className="text-right tnum">{formatNum(t.entry_price)}</TD>
                        <TD className="text-right tnum">{formatNum(t.exit_price)}</TD>
                        <TD className={`text-right tnum font-medium ${trendClass(t.return_pct)}`}>{formatPct(t.return_pct, { sign: true })}</TD>
                        <TD className="text-right tnum muted">{t.bars_held}</TD>
                        <TD>
                          <Badge variant={t.exit_reason?.includes("target") ? "success" : t.exit_reason?.includes("stop") ? "danger" : "default"}>
                            {t.exit_reason}
                          </Badge>
                        </TD>
                      </TR>
                    ))}
                  </TBody>
                </Table>
              )}
            </CardContent>
          </Card>

          {/* Audit log */}
          {(m.data.audit_log?.length ?? 0) > 0 && (
            <details className="rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] p-3">
              <summary className="cursor-pointer text-xs font-medium text-white">Audit log ({m.data.audit_log.length} lines)</summary>
              <pre className="mt-2 text-[11px] muted whitespace-pre-wrap font-mono">{m.data.audit_log.join("\n")}</pre>
            </details>
          )}
        </>
      )}
    </div>
  );
}

function WinnersLosersTable({ rows, positive }: { rows: { symbol: string; entry_date: string; exit_date: string; return_pct: number; bars_held: number; exit_reason: string }[]; positive: boolean }) {
  if (rows.length === 0) return <EmptyState title="—" />;
  return (
    <Table>
      <THead><TR>
        <TH>Symbol</TH>
        <TH>Entry → Exit</TH>
        <TH className="text-right">Return %</TH>
        <TH className="text-right">Bars</TH>
        <TH>Reason</TH>
      </TR></THead>
      <TBody>
        {rows.map((t, i) => (
          <TR key={i}>
            <TD className="font-medium text-white">{t.symbol}</TD>
            <TD className="text-xs muted tnum">{t.entry_date} → {t.exit_date}</TD>
            <TD className={`text-right tnum font-medium ${positive ? "up" : "down"}`}>{formatPct(t.return_pct, { sign: true })}</TD>
            <TD className="text-right tnum muted">{t.bars_held}</TD>
            <TD className="text-xs muted">{t.exit_reason}</TD>
          </TR>
        ))}
      </TBody>
    </Table>
  );
}
