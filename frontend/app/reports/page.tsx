"use client";
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Download, FileText } from "lucide-react";
import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { SymbolAutocomplete } from "@/components/common/symbol-autocomplete";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, THead, TBody, TR, TH, TD } from "@/components/ui/table";
import { EmptyState, ErrorState } from "@/components/ui/empty-state";
import { TimeframeSelector } from "@/components/timeframe-selector";
import { PageHeader } from "@/components/common/page-header";
import type { Timeframe } from "@/lib/types";
import { toast } from "sonner";

export default function ReportsPage() {
  const qc = useQueryClient();
  const [sym, setSym] = useState("RELIANCE");
  const [tf, setTf] = useState<Timeframe>("1D");
  const list = useQuery({ queryKey: ["reports-list"], queryFn: api.listReports });

  const gen = useMutation({
    mutationFn: () => api.generateReport(sym.toUpperCase(), tf),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["reports-list"] }); toast.success("Report generated"); },
    onError: (e) => toast.error((e as Error).message),
  });

  return (
    <div className="max-w-5xl mx-auto space-y-5">
      <PageHeader title="Reports" subtitle="Generate full-fidelity PDF research reports for any stock." />

      <Card>
        <CardHeader><CardTitle>Generate</CardTitle></CardHeader>
        <CardContent>
          <form
            onSubmit={(e) => { e.preventDefault(); if (sym.trim()) gen.mutate(); }}
            className="flex flex-wrap items-center gap-3"
          >
            <SymbolAutocomplete
              value={sym}
              onChange={setSym}
              placeholder="Search stock"
              className="w-64"
            />
            <TimeframeSelector value={tf} onChange={setTf} />
            <Button type="submit" disabled={!sym.trim() || gen.isPending}>
              {gen.isPending ? "Generating…" : "Generate report"}
            </Button>
            <p className="text-xs muted ml-auto">PDFs save to <code>storage/reports/</code></p>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Library ({list.data?.length ?? 0})</CardTitle></CardHeader>
        <CardContent className="p-0">
          {list.isLoading ? <div className="p-4"><Skeleton className="h-40" /></div> :
            list.error ? <div className="p-4"><ErrorState message={(list.error as Error).message} retry={() => list.refetch()} /></div> :
            !list.data?.length ? <div className="p-4"><EmptyState icon={FileText} title="No reports yet" /></div> : (
              <Table>
                <THead><TR>
                  <TH>Filename</TH>
                  <TH className="text-right">Size</TH>
                  <TH className="text-right">Generated</TH>
                  <TH className="text-right"></TH>
                </TR></THead>
                <TBody>
                  {list.data.map((r) => (
                    <TR key={r.filename}>
                      <TD className="font-medium text-white">{r.filename}</TD>
                      <TD className="text-right tnum muted">{(r.size / 1024).toFixed(1)} KB</TD>
                      <TD className="text-right tnum muted">{new Date(r.mtime * 1000).toLocaleString()}</TD>
                      <TD className="text-right">
                        <a
                          href={`/api/reports/file/${encodeURIComponent(r.filename)}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center gap-1 text-xs text-[var(--color-primary)] hover:underline focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)] rounded px-1"
                        >
                          <Download className="size-3" /> Download
                        </a>
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
