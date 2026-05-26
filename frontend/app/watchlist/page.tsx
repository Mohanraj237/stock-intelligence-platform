"use client";
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Trash2, Star } from "lucide-react";
import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { SymbolAutocomplete } from "@/components/common/symbol-autocomplete";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, THead, TBody, TR, TH, TD } from "@/components/ui/table";
import { EmptyState, ErrorState } from "@/components/ui/empty-state";
import { PageHeader } from "@/components/common/page-header";
import { formatNum, formatPct, trendClass } from "@/lib/utils";
import { toast } from "sonner";

export default function WatchlistPage() {
  const qc = useQueryClient();
  const [sym, setSym] = useState("");
  const list = useQuery({ queryKey: ["watchlist"], queryFn: api.watchlist });

  const add = useMutation({
    mutationFn: (s: string) => api.addToWatchlist(s),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["watchlist"] }); setSym(""); toast.success("Added"); },
    onError: (e) => toast.error((e as Error).message),
  });
  const rm = useMutation({
    mutationFn: (s: string) => api.removeFromWatchlist(s),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["watchlist"] }); toast.success("Removed"); },
  });

  return (
    <div className="max-w-6xl mx-auto space-y-5">
      <PageHeader title="Watchlist" subtitle="Live snapshots of stocks you're tracking" />

      <Card>
        <CardHeader><CardTitle>Add stock</CardTitle></CardHeader>
        <CardContent>
          <form
            onSubmit={(e) => { e.preventDefault(); if (sym.trim()) add.mutate(sym.trim().toUpperCase()); }}
            className="flex items-center gap-2"
          >
            <SymbolAutocomplete
              value={sym}
              onChange={setSym}
              onSelect={(s) => add.mutate(s)}
              placeholder="Add by symbol or company"
              className="w-72"
            />
            <Button type="submit" disabled={add.isPending || !sym.trim()}>
              {add.isPending ? "Adding…" : "Add"}
            </Button>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Holdings ({list.data?.length ?? 0})</CardTitle></CardHeader>
        <CardContent>
          {list.isLoading ? <Skeleton className="h-48" /> :
            list.error ? <ErrorState message={(list.error as Error).message} retry={() => list.refetch()} /> :
            !list.data?.length ? <EmptyState icon={Star} title="Nothing here yet" description="Add a symbol above to start tracking." /> : (
              <Table>
                <THead>
                  <TR>
                    <TH>Symbol</TH>
                    <TH className="text-right">Price</TH>
                    <TH className="text-right">Change %</TH>
                    <TH className="text-right">RSI</TH>
                    <TH className="text-right">MACD hist</TH>
                    <TH className="text-right">SMA50</TH>
                    <TH className="text-right">SMA200</TH>
                    <TH className="text-right"></TH>
                  </TR>
                </THead>
                <TBody>
                  {list.data.map((r) => (
                    <TR key={r.symbol}>
                      <TD className="font-medium text-white">{r.symbol}</TD>
                      <TD className="text-right tnum">{formatNum(r.last_price)}</TD>
                      <TD className={`text-right tnum ${trendClass(r.change_pct)}`}>{formatPct(r.change_pct, { sign: true })}</TD>
                      <TD className="text-right tnum">{formatNum(r.rsi, { maxFrac: 1 })}</TD>
                      <TD className={`text-right tnum ${trendClass(r.macd_hist)}`}>{formatNum(r.macd_hist, { maxFrac: 2 })}</TD>
                      <TD className="text-right tnum muted">{formatNum(r.sma50)}</TD>
                      <TD className="text-right tnum muted">{formatNum(r.sma200)}</TD>
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
