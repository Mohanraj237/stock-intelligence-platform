"use client";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { KPI } from "@/components/common/kpi";
import { MarketStatusBanner } from "@/components/market-status-banner";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { formatNum, formatPct, trendClass } from "@/lib/utils";
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, Legend, ComposedChart, Line, ReferenceLine } from "recharts";
import { useRegion } from "@/lib/region";

export default function DashboardPage() {
  const { region, isUS } = useRegion();
  const indices = useQuery({ queryKey: ["indices", region], queryFn: () => api.indices(region), refetchInterval: 60_000 });
  const sectors = useQuery({ queryKey: ["sectors", region], queryFn: () => api.sectors(region), refetchInterval: 120_000 });
  const fii = useQuery({ queryKey: ["fii-dii"], queryFn: api.fiiDii, refetchInterval: 5 * 60_000, enabled: !isUS });

  return (
    <div className="space-y-6 max-w-[1400px] mx-auto">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-white">Dashboard</h1>
          <p className="text-xs muted">Market-wide situational awareness · auto-refresh 60s</p>
        </div>
      </header>

      <MarketStatusBanner />

      {/* Index cards */}
      <section>
        <h2 className="text-xs uppercase tracking-wider muted mb-2">Indices</h2>
        {indices.isLoading ? (
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="h-20 rounded-md bg-[var(--color-surface)] animate-pulse" />
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
            {(indices.data ?? []).slice(0, 6).map((idx, i) => (
              <Card key={`${idx.symbol || idx.name || "idx"}-${i}`}>
                <CardContent className="p-3">
                  <div className="text-[11px] muted truncate">{idx.name || idx.symbol}</div>
                  <div className="mt-1 text-lg font-semibold tnum text-white">
                    {formatNum(idx.last_price)}
                  </div>
                  <div className={`text-[11px] tnum ${trendClass(idx.change_pct)}`}>
                    {formatPct(idx.change_pct, { sign: true })}
                    {idx.change != null && (
                      <span className="muted ml-1">({idx.change >= 0 ? "+" : ""}{idx.change.toFixed(2)})</span>
                    )}
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </section>

      <Tabs defaultValue="sectors">
        <TabsList>
          <TabsTrigger value="sectors">Sectors</TabsTrigger>
          {!isUS && <TabsTrigger value="fii-dii">FII/DII</TabsTrigger>}
          <TabsTrigger value="movers">Top Movers</TabsTrigger>
        </TabsList>

        <TabsContent value="sectors">
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle>Sector heatmap</CardTitle>
                {sectors.data && (
                  <div className="flex items-center gap-3 text-[11px] muted">
                    <span className="inline-flex items-center gap-1"><span className="size-3 rounded" style={{ background: "#1ec48a" }} /> Strong gain</span>
                    <span className="inline-flex items-center gap-1"><span className="size-3 rounded" style={{ background: "#ef5350" }} /> Strong loss</span>
                  </div>
                )}
              </div>
            </CardHeader>
            <CardContent>
              {sectors.isLoading ? (
                <div className="h-72 bg-[var(--color-surface-2)] animate-pulse rounded" />
              ) : (
                <SectorHeatmap data={sectors.data ?? []} />
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="fii-dii">
          <FIIDIIPanel data={fii.data ?? []} loading={fii.isLoading} />
        </TabsContent>

        <TabsContent value="movers">
          <TopMovers />
        </TabsContent>
      </Tabs>
    </div>
  );
}

interface SectorRow {
  name: string;
  change_pct: number;
  advances: number;
  declines: number;
  unchanged: number;
}

function SectorHeatmap({ data }: { data: SectorRow[] }) {
  const ordered = [...data].sort((a, b) => (b.change_pct ?? 0) - (a.change_pct ?? 0));
  const maxAbs = Math.max(0.01, ...ordered.map((s) => Math.abs(s.change_pct || 0)));

  const tone = (chg: number) => {
    const t = Math.min(Math.abs(chg) / Math.max(maxAbs, 1.5), 1);
    const alpha = 0.18 + t * 0.65;
    if (chg > 0)  return { bg: `rgba(30, 196, 138, ${alpha})`, border: "rgba(30, 196, 138, 0.55)" };
    if (chg < 0)  return { bg: `rgba(239, 83,  80,  ${alpha})`, border: "rgba(239, 83,  80,  0.55)" };
    return { bg: "rgba(148, 163, 184, 0.18)", border: "rgba(148, 163, 184, 0.4)" };
  };

  if (ordered.length === 0) {
    return <div className="h-48 grid place-items-center text-sm muted">No sector data</div>;
  }

  return (
    <div className="grid gap-2 grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6">
      {ordered.filter((s) => s.name).map((s, i) => {
        const t = tone(s.change_pct ?? 0);
        const adv = s.advances ?? 0, dec = s.declines ?? 0;
        const total = adv + dec + (s.unchanged ?? 0);
        const advPct = total ? Math.round((adv / total) * 100) : 0;
        return (
          <div
            key={`${s.name}-${i}`}
            className="rounded-md p-3 border transition-transform hover:scale-[1.02] focus-within:scale-[1.02]"
            style={{ background: t.bg, borderColor: t.border }}
            title={`${s.name}: ${formatPct(s.change_pct, { sign: true })} · adv ${adv} / dec ${dec}`}
          >
            <div className="text-[11px] font-medium text-white truncate">{s.name.replace(/^NIFTY\s+/i, "")}</div>
            <div className={`mt-1 text-xl font-semibold tnum ${trendClass(s.change_pct)}`}>
              {formatPct(s.change_pct, { sign: true })}
            </div>
            {total > 0 && (
              <>
                <div className="mt-2 text-[10px] muted tnum flex justify-between">
                  <span className="up">▲ {adv}</span>
                  <span className="down">▼ {dec}</span>
                </div>
                <div className="mt-1 h-1 rounded-full bg-[var(--color-bg)]/40 overflow-hidden">
                  <div className="h-full bg-[var(--color-success)]" style={{ width: `${advPct}%` }} />
                </div>
              </>
            )}
          </div>
        );
      })}
    </div>
  );
}

interface FIIDIIRow {
  date: string;
  fii_buy: number; fii_sell: number; fii_net: number;
  dii_buy: number; dii_sell: number; dii_net: number;
}

function FIIDIIPanel({ data, loading }: { data: FIIDIIRow[]; loading: boolean }) {
  if (loading) return <div className="h-96 rounded-md bg-[var(--color-surface)] animate-pulse" />;
  if (!data || data.length === 0) {
    return (
      <Card><CardContent className="py-12 text-center text-sm muted">No FII/DII data available</CardContent></Card>
    );
  }

  // Recent activity, oldest first for chart
  const sorted = [...data].sort((a, b) => a.date.localeCompare(b.date));
  const recent30 = sorted.slice(-30);

  // Cumulative running totals for trend lines
  let cFII = 0, cDII = 0;
  const cum = recent30.map((r) => {
    cFII += r.fii_net;
    cDII += r.dii_net;
    return { date: r.date, fii_cum: cFII, dii_cum: cDII, net_cum: cFII + cDII };
  });

  const today    = recent30[recent30.length - 1];
  const last5    = recent30.slice(-5);
  const fiiSum5  = last5.reduce((a, r) => a + r.fii_net, 0);
  const diiSum5  = last5.reduce((a, r) => a + r.dii_net, 0);
  const fiiSum30 = recent30.reduce((a, r) => a + r.fii_net, 0);
  const diiSum30 = recent30.reduce((a, r) => a + r.dii_net, 0);

  const fmtCr = (n: number) => `${n >= 0 ? "+" : ""}₹${formatNum(n, { maxFrac: 0 })} Cr`;

  // Compact label: "26 Apr"
  const labelDate = (d: string) => {
    const dt = new Date(d);
    if (Number.isNaN(dt.getTime())) return d;
    return dt.toLocaleDateString("en-IN", { day: "2-digit", month: "short" });
  };

  return (
    <div className="space-y-4">
      {/* KPI strip */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <KPI label={`FII · ${labelDate(today.date)}`} value={fmtCr(today.fii_net)} trend={today.fii_net >= 0 ? "up" : "down"}
             hint={`Buy ₹${formatNum(today.fii_buy)} · Sell ₹${formatNum(today.fii_sell)} Cr`} />
        <KPI label={`DII · ${labelDate(today.date)}`} value={fmtCr(today.dii_net)} trend={today.dii_net >= 0 ? "up" : "down"}
             hint={`Buy ₹${formatNum(today.dii_buy)} · Sell ₹${formatNum(today.dii_sell)} Cr`} />
        <KPI label="Last 5 sessions (net)" value={fmtCr(fiiSum5 + diiSum5)} trend={(fiiSum5 + diiSum5) >= 0 ? "up" : "down"}
             hint={`FII ${fmtCr(fiiSum5)} · DII ${fmtCr(diiSum5)}`} />
        <KPI label="Last 30 sessions (net)" value={fmtCr(fiiSum30 + diiSum30)} trend={(fiiSum30 + diiSum30) >= 0 ? "up" : "down"}
             hint={`FII ${fmtCr(fiiSum30)} · DII ${fmtCr(diiSum30)}`} />
      </div>

      {/* Daily flow chart with cumulative net line overlay */}
      <Card>
        <CardHeader><CardTitle>Daily flows + cumulative net (₹ Cr · last {recent30.length} sessions)</CardTitle></CardHeader>
        <CardContent>
          <div style={{ width: "100%", height: 360 }}>
            <ResponsiveContainer>
              <ComposedChart
                data={recent30.map((r, i) => ({
                  date: labelDate(r.date),
                  fii_net: r.fii_net,
                  dii_net: r.dii_net,
                  net_cum: cum[i].net_cum,
                }))}
                margin={{ top: 10, right: 24, bottom: 0, left: 8 }}
              >
                <XAxis dataKey="date" tick={{ fill: "#94a3b8", fontSize: 10 }} interval={Math.max(0, Math.floor(recent30.length / 10))} />
                <YAxis yAxisId="left" tick={{ fill: "#94a3b8", fontSize: 10 }} tickFormatter={(v) => `${v >= 0 ? "+" : ""}${(v / 1000).toFixed(1)}k`} />
                <YAxis yAxisId="right" orientation="right" tick={{ fill: "#94a3b8", fontSize: 10 }} tickFormatter={(v) => `${v >= 0 ? "+" : ""}${(v / 1000).toFixed(1)}k`} />
                <ReferenceLine yAxisId="left" y={0} stroke="#475569" strokeDasharray="2 2" />
                <Tooltip
                  contentStyle={{ background: "#131822", border: "1px solid #232a3a", fontSize: 12, color: "#fff" }}
                  formatter={(v: number, k: string) => [`${v >= 0 ? "+" : ""}₹${formatNum(v, { maxFrac: 0 })} Cr`, k.replace(/_/g, " ").toUpperCase()]}
                />
                <Legend wrapperStyle={{ fontSize: 11, color: "#94a3b8" }} />
                <Bar  yAxisId="left"  dataKey="fii_net" name="FII Net"      fill="#818cf8" />
                <Bar  yAxisId="left"  dataKey="dii_net" name="DII Net"      fill="#1ec48a" />
                <Line yAxisId="right" dataKey="net_cum" name="Cumulative net" stroke="#f5c542" strokeWidth={2} dot={false} />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
          <p className="text-[11px] muted mt-2">
            Green DII bars + red FII bars typical pattern: <span className="text-white">domestic absorbing foreign selling</span>.
            Both green = strongest broad-based buying signal. Cumulative line above zero = net positive flow over the window.
          </p>
        </CardContent>
      </Card>

      {/* Per-day table for last 10 days */}
      <Card>
        <CardHeader><CardTitle>Last 10 sessions · detail</CardTitle></CardHeader>
        <CardContent className="p-0 overflow-x-auto">
          <table className="w-full text-sm tnum">
            <thead className="border-b border-[var(--color-border)] bg-[var(--color-surface-2)]">
              <tr className="text-[10px] uppercase tracking-wider muted text-right">
                <th className="text-left px-3 py-2">Date</th>
                <th className="px-3 py-2">FII Buy</th>
                <th className="px-3 py-2">FII Sell</th>
                <th className="px-3 py-2">FII Net</th>
                <th className="px-3 py-2">DII Buy</th>
                <th className="px-3 py-2">DII Sell</th>
                <th className="px-3 py-2">DII Net</th>
                <th className="px-3 py-2">Combined</th>
              </tr>
            </thead>
            <tbody>
              {[...recent30].reverse().slice(0, 10).map((r, i) => {
                const combined = r.fii_net + r.dii_net;
                return (
                  <tr key={i} className="border-b border-[var(--color-border)] hover:bg-[var(--color-surface-2)]/60 text-right">
                    <td className="text-left px-3 py-2 font-medium text-white">{labelDate(r.date)}</td>
                    <td className="px-3 py-2 muted">{formatNum(r.fii_buy, { maxFrac: 0 })}</td>
                    <td className="px-3 py-2 muted">{formatNum(r.fii_sell, { maxFrac: 0 })}</td>
                    <td className={`px-3 py-2 ${trendClass(r.fii_net)}`}>{fmtCr(r.fii_net)}</td>
                    <td className="px-3 py-2 muted">{formatNum(r.dii_buy, { maxFrac: 0 })}</td>
                    <td className="px-3 py-2 muted">{formatNum(r.dii_sell, { maxFrac: 0 })}</td>
                    <td className={`px-3 py-2 ${trendClass(r.dii_net)}`}>{fmtCr(r.dii_net)}</td>
                    <td className={`px-3 py-2 font-medium ${trendClass(combined)}`}>{fmtCr(combined)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </CardContent>
      </Card>
    </div>
  );
}

function TopMovers() {
  const { region, isUS } = useRegion();
  const indexName  = isUS ? "DOW 30"   : "NIFTY 50";
  const indexLabel = isUS ? "DOW 30"   : "NIFTY 50";

  const universe = useQuery({
    queryKey: ["universe-quotes", indexName, region],
    queryFn: () => api.universeQuotes(indexName, region),
    refetchInterval: 60_000,
  });
  if (universe.isLoading) return <div className="h-72 rounded-md bg-[var(--color-surface)] animate-pulse" />;
  const data = (universe.data ?? []).filter((r) => r.change_pct != null);
  const gainers = [...data].sort((a, b) => (b.change_pct ?? 0) - (a.change_pct ?? 0)).slice(0, 5);
  const losers  = [...data].sort((a, b) => (a.change_pct ?? 0) - (b.change_pct ?? 0)).slice(0, 5);
  return (
    <div className="grid md:grid-cols-2 gap-4">
      <Card>
        <CardHeader><CardTitle>Top Gainers · {indexLabel}</CardTitle></CardHeader>
        <CardContent>
          <MoverList rows={gainers} positive />
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle>Top Losers · {indexLabel}</CardTitle></CardHeader>
        <CardContent>
          <MoverList rows={losers} positive={false} />
        </CardContent>
      </Card>
    </div>
  );
}

function MoverList({ rows, positive }: { rows: { symbol: string; last_price?: number | null; change_pct?: number | null }[]; positive: boolean }) {
  return (
    <ul className="text-sm divide-y divide-[var(--color-border)]">
      {rows.filter((r) => r.symbol).map((r, i) => (
        <li key={`${r.symbol}-${i}`} className="flex items-center justify-between py-2">
          <span className="font-medium text-white">{r.symbol}</span>
          <span className="flex items-center gap-3 tnum text-xs">
            <span className="muted">{formatNum(r.last_price)}</span>
            <span className={positive ? "up" : "down"}>{formatPct(r.change_pct, { sign: true })}</span>
          </span>
        </li>
      ))}
    </ul>
  );
}
