"use client";
import { useEffect, useState } from "react";
import { useQueries } from "@tanstack/react-query";
import { X } from "lucide-react";
import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { SymbolAutocomplete } from "@/components/common/symbol-autocomplete";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, THead, TBody, TR, TH, TD } from "@/components/ui/table";
import { PageHeader } from "@/components/common/page-header";
import { formatNum, formatPct, trendClass } from "@/lib/utils";
import { useRegion } from "@/lib/region";
import type { Fundamentals } from "@/lib/types";

const IN_DEFAULTS = ["RELIANCE", "TCS", "INFY"];
const US_DEFAULTS = ["AAPL", "MSFT", "GOOGL"];

export default function ComparePage() {
  const { region, isUS } = useRegion();
  const [symbols, setSymbols] = useState<string[]>(isUS ? US_DEFAULTS : IN_DEFAULTS);
  useEffect(() => { setSymbols(isUS ? US_DEFAULTS : IN_DEFAULTS); }, [isUS]);
  const [draft, setDraft] = useState("");

  const queries = useQueries({
    queries: symbols.map((s) => ({
      queryKey: ["fund", s, region],
      queryFn: () => api.fundamentals(s, region),
    })),
  });

  const add = () => {
    const v = draft.trim().toUpperCase();
    if (v && !symbols.includes(v) && symbols.length < 4) {
      setSymbols([...symbols, v]);
      setDraft("");
    }
  };

  const rm = (s: string) => setSymbols(symbols.filter((x) => x !== s));

  return (
    <div className="max-w-6xl mx-auto space-y-5">
      <PageHeader title="Compare" subtitle="Side-by-side fundamentals for up to 4 stocks." />

      <Card>
        <CardHeader><CardTitle>Symbols</CardTitle></CardHeader>
        <CardContent>
          <div className="flex flex-wrap items-center gap-2">
            {symbols.map((s) => (
              <span key={s} className="inline-flex items-center gap-1 rounded-md border border-[var(--color-border)] bg-[var(--color-surface-2)] pl-2 pr-1 py-1 text-sm font-medium">
                {s}
                <button type="button" onClick={() => rm(s)} aria-label={`Remove ${s}`} className="rounded-sm p-0.5 hover:bg-[var(--color-border)] focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)]">
                  <X className="size-3" />
                </button>
              </span>
            ))}
            {symbols.length < 4 && (
              <form onSubmit={(e) => { e.preventDefault(); add(); }} className="flex items-center gap-2">
                <SymbolAutocomplete
                  value={draft}
                  onChange={setDraft}
                  onSelect={(sym) => {
                    if (sym && !symbols.includes(sym) && symbols.length < 4) {
                      setSymbols([...symbols, sym]);
                      setDraft("");
                    }
                  }}
                  placeholder="Add stock"
                  className="w-56"
                />
                <Button type="submit" size="sm" disabled={!draft.trim()}>Add</Button>
              </form>
            )}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Fundamentals comparison</CardTitle></CardHeader>
        <CardContent className="p-0">
          {queries.some((q) => q.isLoading) && <div className="p-4"><Skeleton className="h-60" /></div>}
          {!queries.some((q) => q.isLoading) && (
            <Table>
              <THead>
                <TR>
                  <TH>Metric</TH>
                  {symbols.map((s) => <TH key={s} className="text-right">{s}</TH>)}
                </TR>
              </THead>
              <TBody>
                <Row label="Sector"        symbols={symbols} fmt={(f) => f?.sector ?? "—"} qs={queries} />
                <Row label="Market Cap"    symbols={symbols} fmt={(f) => formatNum(f?.market_cap, { compact: true })} qs={queries} />
                <Row label="PE"            symbols={symbols} fmt={(f) => formatNum(f?.pe, { maxFrac: 2 })} qs={queries} />
                <Row label="PB"            symbols={symbols} fmt={(f) => formatNum(f?.pb, { maxFrac: 2 })} qs={queries} />
                <Row label="ROE %"         symbols={symbols} fmt={(f) => formatPct(f?.roe ?? null)} qs={queries} trendKey="roe" />
                <Row label="ROCE %"        symbols={symbols} fmt={(f) => formatPct(f?.roce ?? null)} qs={queries} trendKey="roce" />
                <Row label="OPM %"         symbols={symbols} fmt={(f) => formatPct(f?.opm ?? null)} qs={queries} trendKey="opm" />
                <Row label="D/E"           symbols={symbols} fmt={(f) => formatNum(f?.debt_to_equity, { maxFrac: 2 })} qs={queries} />
                <Row label="Sales growth"  symbols={symbols} fmt={(f) => formatPct(f?.sales_growth ?? null, { sign: true })} qs={queries} trendKey="sales_growth" />
                <Row label="Profit growth" symbols={symbols} fmt={(f) => formatPct(f?.profit_growth ?? null, { sign: true })} qs={queries} trendKey="profit_growth" />
                <Row label="Promoter %"    symbols={symbols} fmt={(f) => formatPct(f?.promoter_holding ?? null)} qs={queries} />
                <Row label="Dividend %"    symbols={symbols} fmt={(f) => formatPct(f?.dividend_yield ?? null)} qs={queries} />
              </TBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function Row({
  label, symbols, fmt, qs, trendKey,
}: {
  label: string;
  symbols: string[];
  fmt: (f: Fundamentals | undefined) => string;
  qs: { data?: Fundamentals }[];
  trendKey?: keyof Fundamentals;
}) {
  return (
    <TR>
      <TD className="font-medium text-xs muted">{label}</TD>
      {symbols.map((s, i) => {
        const f = qs[i]?.data;
        const v = trendKey && f ? Number(f[trendKey] ?? 0) : null;
        return <TD key={s} className={`text-right tnum ${v != null ? trendClass(v) : ""}`}>{fmt(f)}</TD>;
      })}
    </TR>
  );
}
