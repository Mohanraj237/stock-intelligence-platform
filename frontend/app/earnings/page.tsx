"use client";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Calendar } from "lucide-react";
import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, THead, TBody, TR, TH, TD } from "@/components/ui/table";
import { EmptyState, ErrorState } from "@/components/ui/empty-state";
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from "@/components/ui/select";
import { SymbolInput } from "@/components/common/symbol-input";
import { PageHeader } from "@/components/common/page-header";
import { formatNum, formatPct, trendClass } from "@/lib/utils";
import type { Sentiment } from "@/lib/types";
import { useRegion } from "@/lib/region";

const SENT_VARIANT: Record<Sentiment, "success" | "info" | "warning" | "danger" | "default"> = {
  POSITIVE: "success",
  MILDLY_POSITIVE: "success",
  NEUTRAL: "default",
  MILDLY_NEGATIVE: "warning",
  NEGATIVE: "danger",
};

export default function EarningsPage() {
  return (
    <div className="max-w-6xl mx-auto space-y-5">
      <PageHeader title="Earnings Calendar" subtitle="Upcoming results from NSE board meetings + recent earnings sentiment." />
      <Tabs defaultValue="upcoming">
        <TabsList>
          <TabsTrigger value="upcoming">Upcoming</TabsTrigger>
          <TabsTrigger value="recent">Recent (per stock)</TabsTrigger>
        </TabsList>
        <TabsContent value="upcoming"><Upcoming /></TabsContent>
        <TabsContent value="recent"><Recent /></TabsContent>
      </Tabs>
    </div>
  );
}

function Upcoming() {
  const { region } = useRegion();
  const [days, setDays] = useState("14");
  const q = useQuery({ queryKey: ["earnings-upcoming", days, region], queryFn: () => api.upcomingEarnings(region, Number(days)) });
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <span className="text-xs muted">Look ahead:</span>
        <Select value={days} onValueChange={setDays}>
          <SelectTrigger className="w-32"><SelectValue /></SelectTrigger>
          <SelectContent>
            {["7", "14", "30", "60"].map((d) => <SelectItem key={d} value={d}>{d} days</SelectItem>)}
          </SelectContent>
        </Select>
        <span className="text-xs muted ml-auto">{q.data?.length ?? 0} results</span>
      </div>
      {q.isLoading ? <Skeleton className="h-72" /> :
        q.error ? <ErrorState message={(q.error as Error).message} /> :
        !q.data?.length ? <EmptyState icon={Calendar} title="No upcoming results" /> : (
          <Card>
            <CardContent className="p-0">
              <Table>
                <THead><TR>
                  <TH>Date</TH><TH>Symbol</TH><TH>Company</TH><TH>Agenda</TH>
                </TR></THead>
                <TBody>
                  {q.data.slice(0, 100).map((r, i) => (
                    <TR key={i}>
                      <TD className="tnum text-xs">{r.meeting_date}</TD>
                      <TD className="font-medium text-white">{r.symbol}</TD>
                      <TD className="text-xs muted">{r.company ?? "—"}</TD>
                      <TD className="text-xs muted truncate max-w-[440px]">{r.agenda ?? r.purpose ?? "—"}</TD>
                    </TR>
                  ))}
                </TBody>
              </Table>
            </CardContent>
          </Card>
        )}
    </div>
  );
}

function Recent() {
  const { region, isUS } = useRegion();
  const [sym, setSym] = useState(isUS ? "AAPL" : "RELIANCE");
  const q = useQuery({ queryKey: ["earnings-recent", sym, region], queryFn: () => api.recentEarnings(sym, region, 8) });
  return (
    <div className="space-y-4">
      <SymbolInput initial={sym} onSubmit={setSym} />
      {q.isLoading ? <Skeleton className="h-60" /> :
        q.error ? <ErrorState message={(q.error as Error).message} /> :
        !q.data?.length ? <EmptyState title={`No quarterly data for ${sym}`} /> : (
          <Card>
            <CardHeader><CardTitle>{sym} · last {q.data.length} quarters</CardTitle></CardHeader>
            <CardContent className="p-0">
              <Table>
                <THead><TR>
                  <TH>Period</TH>
                  <TH className="text-right">Sales</TH>
                  <TH className="text-right">Net Profit</TH>
                  <TH className="text-right">OPM %</TH>
                  <TH className="text-right">Sales YoY</TH>
                  <TH className="text-right">Profit YoY</TH>
                  <TH className="text-right">Sentiment</TH>
                </TR></THead>
                <TBody>
                  {q.data.map((e, i) => (
                    <TR key={i}>
                      <TD className="font-medium text-white">{e.period}</TD>
                      <TD className="text-right tnum">{formatNum(e.sales, { compact: true })}</TD>
                      <TD className="text-right tnum">{formatNum(e.net_profit, { compact: true })}</TD>
                      <TD className="text-right tnum muted">{formatNum(e.opm_pct, { maxFrac: 1 })}%</TD>
                      <TD className={`text-right tnum ${trendClass(e.sales_yoy_pct)}`}>{formatPct(e.sales_yoy_pct, { sign: true })}</TD>
                      <TD className={`text-right tnum ${trendClass(e.profit_yoy_pct)}`}>{formatPct(e.profit_yoy_pct, { sign: true })}</TD>
                      <TD className="text-right">
                        <Badge variant={SENT_VARIANT[e.sentiment]}>{e.sentiment.replace("_", " ")}</Badge>
                      </TD>
                    </TR>
                  ))}
                </TBody>
              </Table>
            </CardContent>
          </Card>
        )}
    </div>
  );
}
