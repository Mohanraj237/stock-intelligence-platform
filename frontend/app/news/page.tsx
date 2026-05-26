"use client";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Newspaper, ExternalLink } from "lucide-react";
import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorState, EmptyState } from "@/components/ui/empty-state";
import { SymbolInput } from "@/components/common/symbol-input";
import { PageHeader } from "@/components/common/page-header";
import type { Sentiment } from "@/lib/types";

const SENT_VARIANT: Record<Sentiment, "success" | "info" | "warning" | "danger" | "default"> = {
  POSITIVE: "success",
  MILDLY_POSITIVE: "success",
  NEUTRAL: "default",
  MILDLY_NEGATIVE: "warning",
  NEGATIVE: "danger",
};

export default function NewsPage() {
  return (
    <div className="max-w-5xl mx-auto space-y-5">
      <PageHeader title="News" subtitle="Aggregated headlines + NSE corporate announcements with auto-classified sentiment." />
      <Tabs defaultValue="market">
        <TabsList>
          <TabsTrigger value="market">Market News</TabsTrigger>
          <TabsTrigger value="stock">Stock-Specific</TabsTrigger>
          <TabsTrigger value="ann">NSE Announcements</TabsTrigger>
        </TabsList>
        <TabsContent value="market"><MarketNews /></TabsContent>
        <TabsContent value="stock"><StockNews /></TabsContent>
        <TabsContent value="ann"><Announcements /></TabsContent>
      </Tabs>
    </div>
  );
}

function MarketNews() {
  const q = useQuery({ queryKey: ["news-market"], queryFn: () => api.marketNews(60) });
  if (q.isLoading) return <Skeleton className="h-96" />;
  if (q.error) return <ErrorState message={(q.error as Error).message} retry={() => q.refetch()} />;
  if (!q.data?.length) return <EmptyState icon={Newspaper} title="No headlines" />;
  return <NewsList items={q.data} />;
}

function StockNews() {
  const [sym, setSym] = useState("RELIANCE");
  const q = useQuery({ queryKey: ["news-stock", sym], queryFn: () => api.stockNews(sym, 25) });
  return (
    <div className="space-y-4">
      <SymbolInput initial={sym} onSubmit={setSym} />
      {q.isLoading ? <Skeleton className="h-72" /> :
        q.error ? <ErrorState message={(q.error as Error).message} /> :
        !q.data?.length ? <EmptyState icon={Newspaper} title={`No headlines mentioning ${sym}`} /> :
        <NewsList items={q.data} />}
    </div>
  );
}

function Announcements() {
  const [sym, setSym] = useState("RELIANCE");
  const q = useQuery({ queryKey: ["announcements", sym], queryFn: () => api.announcements(sym) });
  return (
    <div className="space-y-4">
      <SymbolInput initial={sym} onSubmit={setSym} />
      {q.isLoading ? <Skeleton className="h-72" /> :
        q.error ? <ErrorState message={(q.error as Error).message} /> :
        !q.data?.length ? <EmptyState title="No announcements" /> : (
          <Card>
            <CardHeader><CardTitle>{sym} · {q.data.length} disclosures</CardTitle></CardHeader>
            <CardContent>
              <ul className="divide-y divide-[var(--color-border)]">
                {q.data.slice(0, 50).map((a, i) => (
                  <li key={i} className="py-3">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <div className="text-sm font-medium text-white">{a.subject}</div>
                        {a.desc && <p className="text-xs muted mt-1 line-clamp-3">{a.desc}</p>}
                        {a.date && <div className="text-[11px] muted mt-1">{a.date}</div>}
                      </div>
                      <Badge variant={SENT_VARIANT[a.sentiment]}>{a.sentiment.replace("_", " ")}</Badge>
                    </div>
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
        )}
    </div>
  );
}

function NewsList({ items }: { items: { title: string; summary?: string | null; url?: string | null; published?: string | null; source: string; sentiment: Sentiment }[] }) {
  return (
    <Card>
      <CardContent className="p-0">
        <ul className="divide-y divide-[var(--color-border)]">
          {items.map((n, i) => (
            <li key={i} className="px-4 py-3">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <a
                    href={n.url ?? "#"}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-sm font-medium text-white hover:text-[var(--color-primary)] focus:outline-none focus:underline inline-flex items-center gap-1"
                  >
                    {n.title}
                    {n.url && <ExternalLink className="size-3 opacity-70 shrink-0" />}
                  </a>
                  {n.summary && <p className="text-xs muted mt-1 line-clamp-2">{n.summary}</p>}
                  <div className="flex items-center gap-2 mt-1 text-[11px] muted">
                    <span>{n.source}</span>
                    {n.published && <><span>·</span><span>{n.published}</span></>}
                  </div>
                </div>
                <Badge variant={SENT_VARIANT[n.sentiment]} className="shrink-0">
                  {n.sentiment.replace("_", " ")}
                </Badge>
              </div>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}
