"use client";
import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { KPI } from "@/components/common/kpi";
import { PageHeader } from "@/components/common/page-header";
import { formatINR, formatNum } from "@/lib/utils";
import { toast } from "sonner";

const num = (s: string) => Number(s) || 0;

export default function PositionSizingPage() {
  return (
    <div className="max-w-5xl mx-auto space-y-5">
      <PageHeader title="Position Sizing" subtitle="Compute exact share quantity, capital at risk, and Kelly fractions." />

      <Tabs defaultValue="single">
        <TabsList>
          <TabsTrigger value="single">Single Stock</TabsTrigger>
          <TabsTrigger value="kelly">Kelly Criterion</TabsTrigger>
        </TabsList>
        <TabsContent value="single"><SingleStock /></TabsContent>
        <TabsContent value="kelly"><Kelly /></TabsContent>
      </Tabs>
    </div>
  );
}

function SingleStock() {
  const [f, setF] = useState({ capital: "500000", risk_pct: "1", entry: "", stop: "", target: "", max_position_pct: "25" });
  const m = useMutation({
    mutationFn: () => fetch("/api/positions/calc", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        capital: num(f.capital), risk_pct: num(f.risk_pct),
        entry: num(f.entry), stop: num(f.stop),
        target: f.target ? num(f.target) : null,
        max_position_pct: num(f.max_position_pct),
      }),
    }).then((r) => r.json()),
    onError: (e) => toast.error((e as Error).message),
  });

  const valid = num(f.entry) > 0 && num(f.stop) > 0 && num(f.entry) !== num(f.stop);

  return (
    <Card>
      <CardHeader><CardTitle>Trade calculator</CardTitle></CardHeader>
      <CardContent className="space-y-4">
        <form
          onSubmit={(e) => { e.preventDefault(); if (valid) m.mutate(); }}
          className="grid md:grid-cols-3 gap-3"
        >
          {([
            ["Capital (₹)", "capital", "number"],
            ["Risk per trade (%)", "risk_pct", "number"],
            ["Max position (%)", "max_position_pct", "number"],
            ["Entry (₹)", "entry", "number"],
            ["Stop loss (₹)", "stop", "number"],
            ["Target (₹) — optional", "target", "number"],
          ] as const).map(([label, key, type]) => (
            <div key={key} className="space-y-1">
              <Label>{label}</Label>
              <Input type={type} value={(f as Record<string, string>)[key]} onChange={(e) => setF({ ...f, [key]: e.target.value })} />
            </div>
          ))}
          <div className="md:col-span-3">
            <Button type="submit" disabled={!valid || m.isPending}>
              {m.isPending ? "Computing…" : "Compute position"}
            </Button>
          </div>
        </form>

        {m.isPending && <Skeleton className="h-32" />}
        {m.data && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <KPI label="Quantity" value={m.data.qty} />
            <KPI label="Capital deployed" value={formatINR(m.data.deployed)} />
            <KPI label="At risk" value={formatINR(m.data.at_risk)} trend="down" />
            <KPI label="R:R" value={m.data.rr ? formatNum(m.data.rr, { maxFrac: 2 }) : "—"} />
            {(m.data.notes ?? []).length > 0 && (
              <div className="md:col-span-4 text-xs muted">
                {m.data.notes.map((n: string, i: number) => <div key={i}>• {n}</div>)}
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function Kelly() {
  const [f, setF] = useState({ capital: "500000", win_rate: "55", avg_win_pct: "8", avg_loss_pct: "4", fractional: "0.5" });
  const m = useMutation({
    mutationFn: () => fetch("/api/positions/kelly", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        capital: num(f.capital), win_rate: num(f.win_rate),
        avg_win_pct: num(f.avg_win_pct), avg_loss_pct: num(f.avg_loss_pct),
        fractional: num(f.fractional),
      }),
    }).then((r) => r.json()),
  });

  return (
    <Card>
      <CardHeader><CardTitle>Kelly Criterion</CardTitle></CardHeader>
      <CardContent className="space-y-4">
        <form onSubmit={(e) => { e.preventDefault(); m.mutate(); }} className="grid md:grid-cols-3 gap-3">
          {([
            ["Capital (₹)", "capital"],
            ["Historical win rate (%)", "win_rate"],
            ["Avg winner (%)", "avg_win_pct"],
            ["Avg loser (%)", "avg_loss_pct"],
            ["Kelly fraction (1=full, 0.5=half, 0.25=quarter)", "fractional"],
          ] as const).map(([label, key]) => (
            <div key={key} className="space-y-1">
              <Label>{label}</Label>
              <Input type="number" step="0.01" value={(f as Record<string, string>)[key]} onChange={(e) => setF({ ...f, [key]: e.target.value })} />
            </div>
          ))}
          <div className="md:col-span-3">
            <Button type="submit" disabled={m.isPending}>
              {m.isPending ? "Computing…" : "Compute Kelly"}
            </Button>
          </div>
        </form>
        {m.data && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <KPI label="Full Kelly %" value={`${(m.data.full_kelly_pct ?? 0).toFixed(2)}%`} />
            <KPI label="Used %" value={`${(m.data.used_kelly_pct ?? 0).toFixed(2)}%`} />
            <KPI label="Deploy" value={formatINR(m.data.deploy_amount)} />
            <KPI label="Edge" value={`${(m.data.edge ?? 0).toFixed(2)}%`} trend={m.data.edge >= 0 ? "up" : "down"} />
            {m.data.note && <div className="md:col-span-4 text-xs muted">{m.data.note}</div>}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
