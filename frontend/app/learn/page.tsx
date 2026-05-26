"use client";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { PageHeader } from "@/components/common/page-header";

export default function LearnPage() {
  return (
    <div className="max-w-5xl mx-auto space-y-5">
      <PageHeader title="Learn" subtitle="Reference material for chart patterns, indicators, fundamentals & risk." />
      <Tabs defaultValue="patterns">
        <TabsList>
          <TabsTrigger value="patterns">Chart Patterns</TabsTrigger>
          <TabsTrigger value="indicators">Indicators</TabsTrigger>
          <TabsTrigger value="fundamentals">Fundamentals</TabsTrigger>
          <TabsTrigger value="risk">Risk Management</TabsTrigger>
        </TabsList>
        <TabsContent value="patterns"><Patterns /></TabsContent>
        <TabsContent value="indicators"><Indicators /></TabsContent>
        <TabsContent value="fundamentals"><Fundamentals /></TabsContent>
        <TabsContent value="risk"><RiskManagement /></TabsContent>
      </Tabs>
    </div>
  );
}

function Patterns() {
  const { data, isLoading } = useQuery({ queryKey: ["pattern-library"], queryFn: api.patternLibrary });
  if (isLoading) return <Skeleton className="h-96" />;
  return (
    <div className="grid md:grid-cols-2 gap-4">
      {(data ?? []).map((p) => (
        <Card key={p.name}>
          <CardHeader>
            <div className="flex items-center justify-between gap-2">
              <CardTitle>{p.name}</CardTitle>
              <Badge variant={p.direction === "Bullish" ? "success" : p.direction === "Bearish" ? "danger" : "default"}>
                {p.direction}
              </Badge>
            </div>
            <CardDescription>{p.category} · best on {p.best_timeframes}</CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-[var(--color-text)] leading-relaxed">{p.description}</p>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

const INDICATORS = [
  { name: "RSI (Relative Strength Index)", levels: "Below 30 = oversold · Above 70 = overbought", use: "Spot stretched conditions; pair with trend." },
  { name: "MACD", levels: "Crossover above signal = bullish; histogram > 0 = momentum up", use: "Confirm trend changes; avoid in choppy markets." },
  { name: "ADX", levels: "Below 20 = no trend · Above 25 = trend; 40+ = strong", use: "Use as filter — only trade trend setups when ADX > 20." },
  { name: "EMA / SMA", levels: "Price > 50 SMA = uptrend bias; 50 > 200 = bull regime", use: "Trend filter; never fight the moving averages." },
  { name: "Bollinger Bands", levels: "Width contraction → expansion = breakout", use: "Spot squeezes before breakouts." },
  { name: "Stochastic", levels: "Below 20 = oversold · Above 80 = overbought", use: "Mean-reversion in ranging markets." },
];

function Indicators() {
  return (
    <div className="grid md:grid-cols-2 gap-4">
      {INDICATORS.map((i) => (
        <Card key={i.name}>
          <CardHeader><CardTitle>{i.name}</CardTitle></CardHeader>
          <CardContent className="text-sm space-y-2">
            <p><span className="muted">Key levels: </span>{i.levels}</p>
            <p><span className="muted">How to use: </span>{i.use}</p>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

const FUNDS = [
  { name: "PE (Price/Earnings)", desc: "Healthy varies by sector. <20 cheap, 20-40 fair, >40 rich (with caveats)." },
  { name: "PB (Price/Book)", desc: "<1 deep value, 1-3 normal, >5 premium. Banks watched closely." },
  { name: "ROE", desc: ">15% strong; sustained 20%+ is a quality signal." },
  { name: "ROCE", desc: ">15% indicates capital-efficient operations." },
  { name: "Debt/Equity", desc: "<0.5 conservative; >1.0 elevated (capital-intensive sectors aside)." },
  { name: "OPM (Operating margin)", desc: "Stable / rising margin compounds over years." },
  { name: "Promoter holding", desc: ">50% strong skin in the game; pledge % > 25 is a warning." },
];

function Fundamentals() {
  return (
    <div className="grid md:grid-cols-2 gap-4">
      {FUNDS.map((f) => (
        <Card key={f.name}>
          <CardHeader><CardTitle>{f.name}</CardTitle></CardHeader>
          <CardContent className="text-sm">{f.desc}</CardContent>
        </Card>
      ))}
    </div>
  );
}

function RiskManagement() {
  const items = [
    ["Risk per trade", "Cap at 1% of total capital. A 10-loss streak = 10% drawdown — survivable."],
    ["R:R (Reward / Risk)", "Minimum 2:1 expected. 3:1 ideal for swing trades."],
    ["Position size formula", "Qty = (Capital × Risk%) / (Entry − Stop)"],
    ["Stop discipline", "Pre-set stop before placing trade. Never widen a stop after entry."],
    ["Diversification", "Max 5–8 open positions; spread across sectors."],
    ["Trailing stops", "Lock in once price moves > 1.5R in your favour."],
    ["Daily / weekly drawdown", "Stop trading after −3% day or −5% week. Sleep on it."],
  ] as const;
  return (
    <Card>
      <CardHeader><CardTitle>The seven rules</CardTitle></CardHeader>
      <CardContent>
        <dl className="space-y-3 text-sm">
          {items.map(([k, v]) => (
            <div key={k} className="border-b border-[var(--color-border)] pb-3 last:border-0 last:pb-0">
              <dt className="font-medium text-white">{k}</dt>
              <dd className="muted mt-1">{v}</dd>
            </div>
          ))}
        </dl>
      </CardContent>
    </Card>
  );
}
