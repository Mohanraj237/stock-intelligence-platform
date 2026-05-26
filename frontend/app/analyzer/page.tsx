"use client";
import { useState, useEffect, Suspense } from "react";
import { useQuery } from "@tanstack/react-query";
import { useSearchParams, useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, THead, TBody, TR, TH, TD } from "@/components/ui/table";
import { ErrorState, EmptyState } from "@/components/ui/empty-state";
import { Badge } from "@/components/ui/badge";
import { TimeframeSelector } from "@/components/timeframe-selector";
import { SymbolInput } from "@/components/common/symbol-input";
import { PageHeader } from "@/components/common/page-header";
import { KPI } from "@/components/common/kpi";
import { VerdictPill } from "@/components/common/verdict-pill";
import { MarkdownBlock } from "@/components/common/markdown-block";
import { PriceChart } from "@/components/charts/PriceChart";
import { formatNum, formatPct, formatINR, trendClass } from "@/lib/utils";
import type { Timeframe } from "@/lib/types";

export default function AnalyzerPage() {
  return (
    <Suspense fallback={<Skeleton className="h-screen" />}>
      <AnalyzerInner />
    </Suspense>
  );
}

function AnalyzerInner() {
  const sp = useSearchParams();
  const router = useRouter();
  const [symbol, setSymbol] = useState(sp.get("symbol") ?? "RELIANCE");
  const [tf, setTf] = useState<Timeframe>("1D");

  useEffect(() => {
    const url = new URL(window.location.href);
    url.searchParams.set("symbol", symbol);
    router.replace(url.pathname + "?" + url.searchParams.toString(), { scroll: false });
  }, [symbol, router]);

  const ohlcv = useQuery({ queryKey: ["ohlcv", symbol, tf], queryFn: () => api.ohlcv(symbol, tf) });
  const verdict = useQuery({ queryKey: ["verdict", symbol, tf], queryFn: () => api.verdict(symbol, tf) });
  const indicators = useQuery({ queryKey: ["indicators", symbol, tf], queryFn: () => api.indicators(symbol, tf) });
  const fundamentals = useQuery({ queryKey: ["fund", symbol], queryFn: () => api.fundamentals(symbol) });
  const quarterly = useQuery({ queryKey: ["quarterly", symbol], queryFn: () => api.quarterly(symbol, 8) });
  const patterns = useQuery({ queryKey: ["patterns", symbol, tf], queryFn: () => api.detectPatterns(symbol, tf) });
  const balance = useQuery({ queryKey: ["balance", symbol], queryFn: () => api.balanceSheet(symbol) });
  const cashflow = useQuery({ queryKey: ["cashflow", symbol], queryFn: () => api.cashFlow(symbol) });
  const ratios = useQuery({ queryKey: ["ratios", symbol], queryFn: () => api.ratiosHistory(symbol) });
  const shareh = useQuery({ queryKey: ["shareh", symbol], queryFn: () => api.shareholding(symbol) });
  const peers = useQuery({ queryKey: ["peers", symbol], queryFn: () => api.peers(symbol) });
  const chartAnalysis = useQuery({
    queryKey: ["chart-analysis", symbol, tf],
    queryFn: () => api.chartAnalysis(symbol, tf),
  });

  return (
    <div className="max-w-[1500px] mx-auto space-y-5">
      <PageHeader
        title={`Stock Analyzer · ${symbol}`}
        subtitle="Deep-dive across chart, AI, technicals, fundamentals, balance sheet, cash flow, ratio trends, shareholding, peers, and AI chart analysis."
        actions={
          <>
            <SymbolInput initial={symbol} onSubmit={setSymbol} />
            <TimeframeSelector value={tf} onChange={setTf} />
          </>
        }
      />

      {verdict.data && (
        <div className="grid grid-cols-2 md:grid-cols-6 gap-3">
          <KPI label="Verdict" value={<VerdictPill verdict={verdict.data.verdict} />} />
          <KPI label="Composite" value={verdict.data.composite_score.toFixed(0)} />
          <KPI label="Tech" value={verdict.data.tech_score.toFixed(0)} />
          <KPI label="Funda" value={verdict.data.fund_score.toFixed(0)} />
          <KPI label="Pattern" value={verdict.data.pattern_score.toFixed(0)} />
          <KPI label="Confidence" value={verdict.data.confidence} />
        </div>
      )}

      <Tabs defaultValue="chart">
        <TabsList className="flex-wrap h-auto">
          <TabsTrigger value="chart">Chart</TabsTrigger>
          <TabsTrigger value="ai">AI Analysis</TabsTrigger>
          <TabsTrigger value="patterns">Patterns</TabsTrigger>
          <TabsTrigger value="tech">Technicals</TabsTrigger>
          <TabsTrigger value="fund">Fundamentals</TabsTrigger>
          <TabsTrigger value="qtr">Quarterly</TabsTrigger>
          <TabsTrigger value="bs">Balance Sheet</TabsTrigger>
          <TabsTrigger value="cf">Cash Flow</TabsTrigger>
          <TabsTrigger value="ratios">Ratio Trends</TabsTrigger>
          <TabsTrigger value="sh">Shareholding</TabsTrigger>
          <TabsTrigger value="peers">Peers</TabsTrigger>
          <TabsTrigger value="ca">AI Chart Analysis</TabsTrigger>
        </TabsList>

        <TabsContent value="chart">
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between gap-3 flex-wrap">
                <CardTitle>{symbol} · {tf}</CardTitle>
                {(patterns.data?.length ?? 0) > 0 && (
                  <div className="flex items-center gap-2 flex-wrap text-[11px]">
                    <span className="muted">Overlays:</span>
                    {patterns.data!.slice(0, 6).map((p, i) => (
                      <Badge key={i} variant={p.direction === "Bullish" ? "success" : p.direction === "Bearish" ? "danger" : "default"}>
                        {p.name} · {p.confidence.toFixed(0)}%
                      </Badge>
                    ))}
                    {(patterns.data?.length ?? 0) > 6 && <Badge variant="default">+{patterns.data!.length - 6}</Badge>}
                  </div>
                )}
              </div>
            </CardHeader>
            <CardContent>
              {ohlcv.isLoading ? <Skeleton className="h-[500px]" /> :
                ohlcv.error ? <ErrorState message={(ohlcv.error as Error).message} retry={() => ohlcv.refetch()} /> :
                <PriceChart
                  bars={ohlcv.data?.bars ?? []}
                  patterns={patterns.data ?? []}
                  target={verdict.data?.price_target}
                  stop={verdict.data?.stop_loss}
                />}
              <div className="flex items-center gap-4 mt-3 text-[10px] muted flex-wrap">
                <LegendDot color="var(--color-warning)" label="EMA 20" />
                <LegendDot color="var(--color-accent)"  label="EMA 50" />
                <LegendDot color="#26a69a"             label="EMA 200" />
                <LegendDot color="var(--color-success)" label="Target" />
                <LegendDot color="var(--color-danger)"  label="Stop" />
                {(patterns.data?.length ?? 0) > 0 && <LegendDot color="var(--color-warning)" label="Pattern trendlines (dotted)" />}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="ai">
          {verdict.isLoading ? <Skeleton className="h-72" /> :
            verdict.error ? <ErrorState message={(verdict.error as Error).message} /> :
            !verdict.data ? <EmptyState title="No verdict" /> : (
              <div className="space-y-4">
                {/* Header: verdict + target/stop/confidence */}
                <Card>
                  <CardContent className="p-4">
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <div className="flex items-center gap-3">
                        <VerdictPill verdict={verdict.data.verdict} />
                        <div>
                          <div className="text-2xl font-semibold tnum text-white">{verdict.data.composite_score.toFixed(0)}<span className="text-sm muted ml-1">/ 100</span></div>
                          <div className="text-[11px] muted">Composite score · confidence {verdict.data.confidence}</div>
                        </div>
                      </div>
                      <div className="flex items-center gap-6 tnum text-sm">
                        <div>
                          <div className="text-[11px] muted">Target</div>
                          <div className="up font-medium">{formatINR(verdict.data.price_target)}</div>
                        </div>
                        <div>
                          <div className="text-[11px] muted">Stop loss</div>
                          <div className="down font-medium">{formatINR(verdict.data.stop_loss)}</div>
                        </div>
                        <div>
                          <div className="text-[11px] muted">R:R (approx)</div>
                          <div className="font-medium text-white">{computeRR(verdict.data.price_target, verdict.data.stop_loss, indicators.data?.close)}</div>
                        </div>
                      </div>
                    </div>
                  </CardContent>
                </Card>

                {/* Score breakdown — horizontal bars */}
                <Card>
                  <CardHeader><CardTitle>Score breakdown</CardTitle></CardHeader>
                  <CardContent className="space-y-2">
                    <ScoreBar label="Technical"   value={verdict.data.tech_score} />
                    <ScoreBar label="Fundamental" value={verdict.data.fund_score} />
                    <ScoreBar label="Pattern"     value={verdict.data.pattern_score} />
                    <ScoreBar label="Momentum"    value={verdict.data.momentum_score} />
                  </CardContent>
                </Card>

                <div className="grid md:grid-cols-2 gap-4">
                  <Card>
                    <CardHeader><CardTitle>Bull case</CardTitle></CardHeader>
                    <CardContent>
                      {verdict.data.bull_case.length === 0 ? <p className="text-sm muted">No bullish signals.</p> : (
                        <ul className="text-sm space-y-2">
                          {verdict.data.bull_case.map((b, i) => (
                            <li key={i} className="flex gap-2"><span className="up shrink-0">▲</span><span>{b}</span></li>
                          ))}
                        </ul>
                      )}
                    </CardContent>
                  </Card>
                  <Card>
                    <CardHeader><CardTitle>Bear case</CardTitle></CardHeader>
                    <CardContent>
                      {verdict.data.bear_case.length === 0 ? <p className="text-sm muted">No bearish signals.</p> : (
                        <ul className="text-sm space-y-2">
                          {verdict.data.bear_case.map((b, i) => (
                            <li key={i} className="flex gap-2"><span className="down shrink-0">▼</span><span>{b}</span></li>
                          ))}
                        </ul>
                      )}
                    </CardContent>
                  </Card>
                </div>

                <Card>
                  <CardHeader><CardTitle>Risk flags</CardTitle></CardHeader>
                  <CardContent>
                    {verdict.data.risk_flags.length === 0 ? <p className="text-sm muted">No flags raised.</p> : (
                      <div className="flex flex-wrap gap-2">
                        {verdict.data.risk_flags.map((r, i) => <Badge key={i} variant="warning">{r}</Badge>)}
                      </div>
                    )}
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader><CardTitle>Signal chain · {verdict.data.signal_chain.length}</CardTitle></CardHeader>
                  <CardContent>
                    {verdict.data.signal_chain.length === 0 ? <p className="text-sm muted">No signals.</p> : (
                      <ul className="text-sm space-y-1.5">
                        {verdict.data.signal_chain.map((s, i) => {
                          const sentiment = signalSentiment(s);
                          return (
                            <li key={i} className="flex items-start gap-2">
                              <span className={`mt-1 inline-block size-1.5 rounded-full shrink-0 ${
                                sentiment === "bull" ? "bg-[var(--color-success)]" :
                                sentiment === "bear" ? "bg-[var(--color-danger)]" :
                                "bg-[var(--color-text-muted)]"
                              }`} />
                              <span className={sentiment === "bull" ? "text-[var(--color-success)]" : sentiment === "bear" ? "text-[var(--color-danger)]" : "text-[var(--color-text)]"}>{s}</span>
                            </li>
                          );
                        })}
                      </ul>
                    )}
                  </CardContent>
                </Card>
              </div>
            )}
        </TabsContent>

        <TabsContent value="patterns">
          {patterns.isLoading ? <Skeleton className="h-72" /> :
            !patterns.data?.length ? <EmptyState title={`No patterns detected on ${tf}`} /> : (
              <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-3">
                {patterns.data.map((p, i) => (
                  <Card key={i}>
                    <CardHeader>
                      <div className="flex items-center justify-between gap-2">
                        <CardTitle className="truncate">{p.name}</CardTitle>
                        <Badge variant={p.direction === "Bullish" ? "success" : p.direction === "Bearish" ? "danger" : "default"}>
                          {p.direction}
                        </Badge>
                      </div>
                      <div className="mt-2 flex items-center gap-2 text-[11px] muted">
                        <span>Confidence</span>
                        <div className="flex-1 h-1.5 rounded-full bg-[var(--color-surface-2)] overflow-hidden">
                          <div
                            className={`h-full rounded-full ${p.direction === "Bullish" ? "bg-[var(--color-success)]" : p.direction === "Bearish" ? "bg-[var(--color-danger)]" : "bg-[var(--color-text-muted)]"}`}
                            style={{ width: `${Math.min(100, Math.max(0, p.confidence))}%` }}
                            aria-label={`Confidence ${p.confidence.toFixed(0)} percent`}
                          />
                        </div>
                        <span className="tnum text-white">{p.confidence.toFixed(0)}%</span>
                      </div>
                    </CardHeader>
                    <CardContent className="space-y-2">
                      {p.description && <p className="text-xs muted leading-relaxed">{p.description}</p>}
                      <div className="grid grid-cols-2 gap-2 text-xs pt-1">
                        {p.target && <Field label="Target" value={<span className="up">{formatINR(p.target)}</span>} />}
                        {p.stop && <Field label="Stop" value={<span className="down">{formatINR(p.stop)}</span>} />}
                        {p.support && <Field label="Support" value={formatINR(p.support)} />}
                        {p.resistance && <Field label="Resistance" value={formatINR(p.resistance)} />}
                      </div>
                      {p.category && <div className="text-[10px] muted uppercase tracking-wider">{p.category}</div>}
                    </CardContent>
                  </Card>
                ))}
              </div>
            )}
        </TabsContent>

        <TabsContent value="tech">
          {indicators.isLoading ? <Skeleton className="h-60" /> :
            indicators.error ? <ErrorState message={(indicators.error as Error).message} /> : (
              <Card>
                <CardContent className="p-0">
                  <Table>
                    <THead><TR><TH>Indicator</TH><TH className="text-right">Value</TH></TR></THead>
                    <TBody>
                      {Object.entries(indicators.data ?? {}).map(([k, v]) => (
                        <TR key={k}>
                          <TD className="font-medium text-xs muted">{k}</TD>
                          <TD className="text-right tnum">{typeof v === "number" ? formatNum(v as number, { maxFrac: 4 }) : "—"}</TD>
                        </TR>
                      ))}
                    </TBody>
                  </Table>
                </CardContent>
              </Card>
            )}
        </TabsContent>

        <TabsContent value="fund">
          {fundamentals.isLoading ? <Skeleton className="h-72" /> :
            fundamentals.error ? <ErrorState message={(fundamentals.error as Error).message} /> :
            fundamentals.data?.error ? <EmptyState title="Screener.in unavailable" description={fundamentals.data.error} /> : (
              <div className="grid md:grid-cols-2 gap-4">
                <Card>
                  <CardHeader><CardTitle>{fundamentals.data?.name ?? symbol}</CardTitle></CardHeader>
                  <CardContent>
                    <div className="grid grid-cols-2 gap-3 text-sm">
                      <Field label="Sector" value={fundamentals.data?.sector ?? "—"} />
                      <Field label="Industry" value={fundamentals.data?.industry ?? "—"} />
                      <Field label="Market Cap" value={formatNum(fundamentals.data?.market_cap, { compact: true })} />
                      <Field label="PE" value={formatNum(fundamentals.data?.pe, { maxFrac: 2 })} />
                      <Field label="PB" value={formatNum(fundamentals.data?.pb, { maxFrac: 2 })} />
                      <Field label="Book Value" value={formatINR(fundamentals.data?.book_value)} />
                      <Field label="Dividend Yield" value={formatPct(fundamentals.data?.dividend_yield ?? null)} />
                      <Field label="EPS" value={formatNum(fundamentals.data?.eps, { maxFrac: 2 })} />
                      <Field label="ROE" value={formatPct(fundamentals.data?.roe ?? null)} />
                      <Field label="ROCE" value={formatPct(fundamentals.data?.roce ?? null)} />
                      <Field label="OPM" value={formatPct(fundamentals.data?.opm ?? null)} />
                      <Field label="NPM" value={formatPct(fundamentals.data?.npm ?? null)} />
                      <Field label="D/E" value={formatNum(fundamentals.data?.debt_to_equity, { maxFrac: 2 })} />
                      <Field label="Interest Cov." value={formatNum(fundamentals.data?.interest_coverage, { maxFrac: 2 })} />
                      <Field label="Promoter %" value={formatPct(fundamentals.data?.promoter_holding ?? null)} />
                      <Field label="Sales growth" value={formatPct(fundamentals.data?.sales_growth ?? null, { sign: true })} />
                      <Field label="Profit growth" value={formatPct(fundamentals.data?.profit_growth ?? null, { sign: true })} />
                    </div>
                  </CardContent>
                </Card>
                <Card>
                  <CardHeader><CardTitle>About</CardTitle></CardHeader>
                  <CardContent>
                    <p className="text-sm muted whitespace-pre-wrap">{fundamentals.data?.about ?? "No description available."}</p>
                  </CardContent>
                </Card>
                {(fundamentals.data?.pros?.length ?? 0) > 0 && (
                  <Card>
                    <CardHeader><CardTitle>Pros</CardTitle></CardHeader>
                    <CardContent>
                      <ul className="text-sm space-y-1.5">
                        {(fundamentals.data?.pros ?? []).map((p, i) => <li key={i} className="up">+ {p}</li>)}
                      </ul>
                    </CardContent>
                  </Card>
                )}
                {(fundamentals.data?.cons?.length ?? 0) > 0 && (
                  <Card>
                    <CardHeader><CardTitle>Cons</CardTitle></CardHeader>
                    <CardContent>
                      <ul className="text-sm space-y-1.5">
                        {(fundamentals.data?.cons ?? []).map((p, i) => <li key={i} className="down">− {p}</li>)}
                      </ul>
                    </CardContent>
                  </Card>
                )}
              </div>
            )}
        </TabsContent>

        <TabsContent value="qtr">
          {quarterly.isLoading ? <Skeleton className="h-60" /> :
            quarterly.error ? <ErrorState message={(quarterly.error as Error).message} /> :
            !quarterly.data?.length ? <EmptyState title="No quarterly data" /> : (
              <Card>
                <CardContent className="p-0">
                  <Table>
                    <THead><TR>
                      <TH>Period</TH>
                      <TH className="text-right">Sales</TH>
                      <TH className="text-right">Net Profit</TH>
                      <TH className="text-right">OPM %</TH>
                      <TH className="text-right">Sales YoY</TH>
                      <TH className="text-right">Profit YoY</TH>
                    </TR></THead>
                    <TBody>
                      {quarterly.data.map((q, i) => (
                        <TR key={i}>
                          <TD className="font-medium text-white">{q.period}</TD>
                          <TD className="text-right tnum">{formatNum(q.sales, { compact: true })}</TD>
                          <TD className="text-right tnum">{formatNum(q.net_profit, { compact: true })}</TD>
                          <TD className="text-right tnum muted">{formatNum(q.opm_pct, { maxFrac: 1 })}</TD>
                          <TD className={`text-right tnum ${trendClass(q.sales_yoy_pct)}`}>{formatPct(q.sales_yoy_pct, { sign: true })}</TD>
                          <TD className={`text-right tnum ${trendClass(q.profit_yoy_pct)}`}>{formatPct(q.profit_yoy_pct, { sign: true })}</TD>
                        </TR>
                      ))}
                    </TBody>
                  </Table>
                </CardContent>
              </Card>
            )}
        </TabsContent>

        <TabsContent value="bs"><PeriodicTable q={balance} title="Balance Sheet" /></TabsContent>
        <TabsContent value="cf"><PeriodicTable q={cashflow} title="Cash Flow" /></TabsContent>
        <TabsContent value="ratios"><PeriodicTable q={ratios} title="Ratio Trends" /></TabsContent>

        <TabsContent value="sh">
          {shareh.isLoading ? <Skeleton className="h-60" /> :
            shareh.error ? <ErrorState message={(shareh.error as Error).message} /> : (
              <div className="space-y-4">
                <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
                  <KPI label="Promoter %" value={formatPct(shareh.data?.latest?.promoter ?? null)} />
                  <KPI label="FII %" value={formatPct(shareh.data?.latest?.fii ?? null)} />
                  <KPI label="DII %" value={formatPct(shareh.data?.latest?.dii ?? null)} />
                  <KPI label="Public %" value={formatPct(shareh.data?.latest?.public ?? null)} />
                  <KPI label="Pledge %" value={formatPct(shareh.data?.latest?.pledge ?? null)} trend={shareh.data?.latest?.pledge && shareh.data.latest.pledge > 25 ? "down" : undefined} />
                </div>
                {shareh.data?.history?.length ? (
                  <Card>
                    <CardHeader><CardTitle>Quarterly history</CardTitle></CardHeader>
                    <CardContent className="p-0">
                      <RowsTable rows={shareh.data.history} firstCol="period" />
                    </CardContent>
                  </Card>
                ) : <EmptyState title="No shareholding history" />}
              </div>
            )}
        </TabsContent>

        <TabsContent value="peers">
          {peers.isLoading ? <Skeleton className="h-40" /> :
            peers.error ? <ErrorState message={(peers.error as Error).message} /> :
            !peers.data?.peers?.length ? <EmptyState title="No peers data available for this stock" /> : (
              <Card>
                <CardHeader>
                  <CardTitle>
                    {symbol} · peers
                    {peers.data.sector && <span className="muted text-xs font-normal ml-2">· {peers.data.sector}</span>}
                    {peers.data.source && peers.data.source !== "screener" && (
                      <span className="muted text-xs font-normal ml-2">· from {String(peers.data.source)}</span>
                    )}
                  </CardTitle>
                </CardHeader>
                <CardContent className="p-0">
                  <Table>
                    <THead><TR>
                      <TH>Symbol</TH>
                      <TH>Company</TH>
                      <TH className="text-right">Price</TH>
                      <TH className="text-right">Chg %</TH>
                      <TH className="text-right">52W H</TH>
                      <TH className="text-right">52W L</TH>
                    </TR></THead>
                    <TBody>
                      {(peers.data.peers as Array<{ symbol?: string; name?: string; company?: string; last_price?: number; change_pct?: number; week52_high?: number; week52_low?: number }>).map((p, i) => (
                        <TR key={i}>
                          <TD>
                            <a href={`/analyzer?symbol=${encodeURIComponent(p.symbol ?? "")}`} className="font-medium text-white hover:text-[var(--color-primary)] focus:outline-none focus:underline">
                              {p.symbol ?? p.name ?? "—"}
                            </a>
                          </TD>
                          <TD className="text-xs muted truncate max-w-[260px]">{p.company ?? p.name ?? "—"}</TD>
                          <TD className="text-right tnum">{formatNum(p.last_price)}</TD>
                          <TD className={`text-right tnum ${trendClass(p.change_pct)}`}>{formatPct(p.change_pct, { sign: true })}</TD>
                          <TD className="text-right tnum muted">{formatNum(p.week52_high)}</TD>
                          <TD className="text-right tnum muted">{formatNum(p.week52_low)}</TD>
                        </TR>
                      ))}
                    </TBody>
                  </Table>
                </CardContent>
              </Card>
            )}
        </TabsContent>

        <TabsContent value="ca">
          {chartAnalysis.isLoading ? <Skeleton className="h-96" /> :
            chartAnalysis.error ? <ErrorState message={(chartAnalysis.error as Error).message} /> :
            !chartAnalysis.data ? <EmptyState title="No analysis" /> : (
              <div className="space-y-4">
                <Card>
                  <CardHeader>
                    <div className="flex items-center justify-between gap-3">
                      <CardTitle className="text-base">
                        {chartAnalysis.data.final_verdict || "—"}
                      </CardTitle>
                      <Badge variant={chartAnalysis.data.confidence === "High" ? "success" : chartAnalysis.data.confidence === "Low" ? "warning" : "info"}>
                        Confidence · {chartAnalysis.data.confidence}
                      </Badge>
                    </div>
                  </CardHeader>
                  {chartAnalysis.data.pro_explanation && (
                    <CardContent>
                      <MarkdownBlock text={chartAnalysis.data.pro_explanation} />
                    </CardContent>
                  )}
                </Card>

                {Object.keys(chartAnalysis.data.probability_scores ?? {}).length > 0 && (
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                    {Object.entries(chartAnalysis.data.probability_scores).map(([k, v]) => (
                      <KPI key={k} label={k} value={`${(v as number).toFixed(1)} / 10`} />
                    ))}
                  </div>
                )}

                <div className="grid md:grid-cols-3 gap-3">
                  <KPI label="Entry" value={formatINR(chartAnalysis.data.entry)} />
                  <KPI label="Stop loss" value={formatINR(chartAnalysis.data.stop_loss)} trend="down" />
                  <KPI label="Targets" value={chartAnalysis.data.targets.length > 0 ? chartAnalysis.data.targets.map((t) => formatINR(t)).join(", ") : "—"} trend="up" />
                </div>

                {(chartAnalysis.data.red_flags?.length ?? 0) > 0 && (
                  <Card>
                    <CardHeader><CardTitle>Red flags</CardTitle></CardHeader>
                    <CardContent>
                      <div className="flex flex-wrap gap-2">
                        {chartAnalysis.data.red_flags.map((r, i) => <Badge key={i} variant="danger">{r}</Badge>)}
                      </div>
                    </CardContent>
                  </Card>
                )}

                {chartAnalysis.data.sections && Object.keys(chartAnalysis.data.sections).length > 0 && (
                  <div className="grid md:grid-cols-2 gap-3">
                    {Object.entries(chartAnalysis.data.sections).map(([title, content]) => (
                      <Card key={title}>
                        <CardHeader><CardTitle>{title}</CardTitle></CardHeader>
                        <CardContent>
                          <MarkdownBlock text={typeof content === "string" ? content : JSON.stringify(content, null, 2)} />
                        </CardContent>
                      </Card>
                    ))}
                  </div>
                )}
              </div>
            )}
        </TabsContent>
      </Tabs>
    </div>
  );
}

function Field({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <div className="text-xs muted">{label}</div>
      <div className="font-medium text-white tnum">{value}</div>
    </div>
  );
}

function LegendDot({ color, label }: { color: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className="size-2 rounded-full" style={{ background: color }} />
      <span>{label}</span>
    </span>
  );
}

function ScoreBar({ label, value }: { label: string; value: number }) {
  const pct = Math.max(0, Math.min(100, value));
  const tone = pct >= 70 ? "bg-[var(--color-success)]" : pct >= 50 ? "bg-[var(--color-primary)]" : pct >= 30 ? "bg-[var(--color-warning)]" : "bg-[var(--color-danger)]";
  return (
    <div className="flex items-center gap-3">
      <div className="w-28 text-xs muted">{label}</div>
      <div className="flex-1 h-2 rounded-full bg-[var(--color-surface-2)] overflow-hidden">
        <div className={`h-full rounded-full ${tone} transition-all`} style={{ width: `${pct}%` }} />
      </div>
      <div className="w-10 text-right tnum text-xs font-medium text-white">{pct.toFixed(0)}</div>
    </div>
  );
}

function computeRR(target: number | null | undefined, stop: number | null | undefined, current: number | null | undefined): string {
  if (!target || !stop || !current) return "—";
  const reward = target - current;
  const risk = current - stop;
  if (risk <= 0 || reward <= 0) return "—";
  return `1 : ${(reward / risk).toFixed(2)}`;
}

function signalSentiment(s: string): "bull" | "bear" | "neutral" {
  const lc = s.toLowerCase();
  const bull = ["bullish", "bull", "above", "uptrend", "momentum", "breakout", "above ema", "above sma", "golden cross", "support", "buy", "strong"];
  const bear = ["bearish", "bear", "below", "downtrend", "death cross", "breakdown", "weak", "overbought", "extended", "decline", "sell", "warning"];
  if (bull.some((k) => lc.includes(k)) && !bear.some((k) => lc.includes(k))) return "bull";
  if (bear.some((k) => lc.includes(k))) return "bear";
  return "neutral";
}

interface PeriodicQuery {
  isLoading: boolean;
  error: unknown;
  data?: { rows: Record<string, number | string | null>[] };
}

function PeriodicTable({ q, title }: { q: PeriodicQuery; title: string }) {
  if (q.isLoading) return <Skeleton className="h-72" />;
  if (q.error) return <ErrorState message={(q.error as Error).message} />;
  if (!q.data?.rows?.length) return <EmptyState title={`No ${title.toLowerCase()} data`} />;
  return (
    <Card>
      <CardHeader><CardTitle>{title}</CardTitle></CardHeader>
      <CardContent className="p-0">
        <RowsTable rows={q.data.rows} firstCol="period" />
      </CardContent>
    </Card>
  );
}

function RowsTable({ rows, firstCol }: { rows: Record<string, number | string | null>[]; firstCol: string }) {
  if (rows.length === 0) return null;
  const columns = Object.keys(rows[0]).filter((c) => c !== firstCol);
  return (
    <Table>
      <THead><TR>
        <TH>{firstCol}</TH>
        {columns.map((c) => <TH key={c} className="text-right">{c}</TH>)}
      </TR></THead>
      <TBody>
        {rows.map((row, i) => (
          <TR key={i}>
            <TD className="font-medium text-white">{String(row[firstCol] ?? "—")}</TD>
            {columns.map((c) => {
              const v = row[c];
              const isNum = typeof v === "number";
              return (
                <TD key={c} className="text-right tnum text-xs">
                  {v == null ? "—" : isNum ? formatNum(v as number, { maxFrac: 2, compact: Math.abs(v as number) > 9999 }) : String(v)}
                </TD>
              );
            })}
          </TR>
        ))}
      </TBody>
    </Table>
  );
}
