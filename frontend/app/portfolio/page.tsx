"use client";
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Trash2, Wallet } from "lucide-react";
import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { SymbolAutocomplete } from "@/components/common/symbol-autocomplete";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, THead, TBody, TR, TH, TD } from "@/components/ui/table";
import { EmptyState, ErrorState } from "@/components/ui/empty-state";
import { KPI } from "@/components/common/kpi";
import { PageHeader } from "@/components/common/page-header";
import { formatCurrency, formatNum, formatPct, trendClass } from "@/lib/utils";
import { useRegion } from "@/lib/region";
import { toast } from "sonner";

export default function PortfolioPage() {
  const { region, currencySymbol } = useRegion();
  const qc = useQueryClient();
  const portfolio = useQuery({ queryKey: ["portfolio"], queryFn: api.portfolio });
  const [form, setForm] = useState({ symbol: "", qty: "", buy_price: "", buy_date: "" });

  const add = useMutation({
    mutationFn: () => api.addHolding({
      symbol: form.symbol.toUpperCase().trim(),
      qty: Number(form.qty),
      buy_price: Number(form.buy_price),
      buy_date: form.buy_date || undefined,
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["portfolio"] });
      setForm({ symbol: "", qty: "", buy_price: "", buy_date: "" });
      toast.success("Holding added");
    },
    onError: (e) => toast.error((e as Error).message),
  });

  const rm = useMutation({
    mutationFn: (s: string) => api.removeHolding(s),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["portfolio"] }); toast.success("Removed"); },
  });

  const valid = form.symbol.trim() && Number(form.qty) > 0 && Number(form.buy_price) > 0;

  return (
    <div className="max-w-6xl mx-auto space-y-5">
      <PageHeader title="Portfolio" subtitle="Local holdings + live P&L (no broker integration)." />

      {portfolio.data && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <KPI label="Holdings" value={portfolio.data.holdings_count} />
          <KPI label="Invested" value={formatCurrency(portfolio.data.total_invested, region)} />
          <KPI label="Current value" value={formatCurrency(portfolio.data.current_value, region)} />
          <KPI
            label="P&L"
            value={`${formatCurrency(portfolio.data.total_pnl, region)} (${formatPct(portfolio.data.total_pnl_pct, { sign: true })})`}
            trend={portfolio.data.total_pnl >= 0 ? "up" : "down"}
          />
        </div>
      )}

      <Card>
        <CardHeader><CardTitle>Add holding</CardTitle></CardHeader>
        <CardContent>
          <form
            onSubmit={(e) => { e.preventDefault(); if (valid) add.mutate(); }}
            className="grid md:grid-cols-5 gap-3 items-end"
          >
            <div className="space-y-1">
              <Label>Symbol</Label>
              <SymbolAutocomplete
                value={form.symbol}
                onChange={(s) => setForm({ ...form, symbol: s })}
                placeholder="Search symbol or company"
              />
            </div>
            <div className="space-y-1">
              <Label>Quantity</Label>
              <Input type="number" min={0} step="0.0001" value={form.qty} onChange={(e) => setForm({ ...form, qty: e.target.value })} />
            </div>
            <div className="space-y-1">
              <Label>Buy price ({currencySymbol})</Label>
              <Input type="number" min={0} step="0.01" value={form.buy_price} onChange={(e) => setForm({ ...form, buy_price: e.target.value })} />
            </div>
            <div className="space-y-1">
              <Label>Buy date</Label>
              <Input type="date" value={form.buy_date} onChange={(e) => setForm({ ...form, buy_date: e.target.value })} />
            </div>
            <Button type="submit" disabled={!valid || add.isPending}>
              {add.isPending ? "Adding…" : "Add holding"}
            </Button>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Holdings</CardTitle></CardHeader>
        <CardContent>
          {portfolio.isLoading ? <Skeleton className="h-40" /> :
            portfolio.error ? <ErrorState message={(portfolio.error as Error).message} retry={() => portfolio.refetch()} /> :
            !portfolio.data?.rows.length ? <EmptyState icon={Wallet} title="No holdings yet" /> : (
              <Table>
                <THead><TR>
                  <TH>Symbol</TH>
                  <TH className="text-right">Qty</TH>
                  <TH className="text-right">Buy</TH>
                  <TH className="text-right">CMP</TH>
                  <TH className="text-right">Today %</TH>
                  <TH className="text-right">Invested</TH>
                  <TH className="text-right">Value</TH>
                  <TH className="text-right">P&L</TH>
                  <TH className="text-right">P&L %</TH>
                  <TH className="text-right"></TH>
                </TR></THead>
                <TBody>
                  {portfolio.data.rows.map((r) => (
                    <TR key={r.symbol}>
                      <TD className="font-medium text-white">{r.symbol}</TD>
                      <TD className="text-right tnum">{r.qty}</TD>
                      <TD className="text-right tnum muted">{formatCurrency(r.buy_price, region)}</TD>
                      <TD className="text-right tnum">{formatCurrency(r.cmp, region)}</TD>
                      <TD className={`text-right tnum ${trendClass(r.today_change_pct)}`}>{formatPct(r.today_change_pct, { sign: true })}</TD>
                      <TD className="text-right tnum muted">{formatCurrency(r.invested, region)}</TD>
                      <TD className="text-right tnum">{formatCurrency(r.current_value, region)}</TD>
                      <TD className={`text-right tnum ${trendClass(r.pnl)}`}>{formatCurrency(r.pnl, region)}</TD>
                      <TD className={`text-right tnum ${trendClass(r.pnl_pct)}`}>{formatPct(r.pnl_pct, { sign: true })}</TD>
                      <TD className="text-right">
                        <Button variant="ghost" size="icon" aria-label={`Remove ${r.symbol}`} onClick={() => rm.mutate(r.symbol)}>
                          <Trash2 className="size-3.5" />
                        </Button>
                      </TD>
                    </TR>
                  ))}
                </TBody>
              </Table>
            )}
        </CardContent>
      </Card>
    </div>
  );
}
