"use client";
import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ArrowDown, ArrowUp } from "lucide-react";
import Link from "next/link";
import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, THead, TBody, TR, TH, TD } from "@/components/ui/table";
import { ErrorState } from "@/components/ui/empty-state";
import { UniverseSelect } from "@/components/common/universe-select";
import { PageHeader } from "@/components/common/page-header";
import { formatNum, formatPct, trendClass } from "@/lib/utils";
import { useRegion } from "@/lib/region";
import type { UniverseRow } from "@/lib/types";

type SortKey = keyof Pick<UniverseRow, "symbol" | "last_price" | "change_pct" | "volume" | "return_30d" | "return_1y">;

export default function UniverseExplorerPage() {
  const { region, isUS } = useRegion();
  const [universe, setUniverse] = useState(isUS ? "S&P 500" : "NIFTY 50");
  useEffect(() => { setUniverse(isUS ? "S&P 500" : "NIFTY 50"); }, [isUS]);
  const [filter, setFilter] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("change_pct");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");

  const q = useQuery({
    queryKey: ["universe-quotes", universe, region],
    queryFn: () => api.universeQuotes(universe, region),
  });

  const rows = useMemo(() => {
    let r = q.data ?? [];
    if (filter) {
      const f = filter.toUpperCase();
      r = r.filter((x) => x.symbol.toUpperCase().includes(f) || (x.company ?? "").toUpperCase().includes(f));
    }
    return [...r].sort((a, b) => {
      const av = a[sortKey] ?? -Infinity;
      const bv = b[sortKey] ?? -Infinity;
      if (typeof av === "string" || typeof bv === "string") {
        return sortDir === "asc" ? String(av).localeCompare(String(bv)) : String(bv).localeCompare(String(av));
      }
      return sortDir === "asc" ? Number(av) - Number(bv) : Number(bv) - Number(av);
    });
  }, [q.data, filter, sortKey, sortDir]);

  const sortBy = (k: SortKey) => {
    if (k === sortKey) setSortDir(sortDir === "asc" ? "desc" : "asc");
    else { setSortKey(k); setSortDir("desc"); }
  };

  return (
    <div className="max-w-[1500px] mx-auto space-y-5">
      <PageHeader
        title="Universe Explorer"
        subtitle="Browse and filter index constituents with live prices."
        actions={
          <>
            <UniverseSelect value={universe} onChange={setUniverse} />
            <Input
              aria-label="Filter symbols"
              placeholder="Filter symbol/company"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              className="w-56"
            />
          </>
        }
      />

      <Card>
        <CardHeader>
          <CardTitle>{universe} · {q.data?.length ?? 0} stocks</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {q.isLoading ? <div className="p-4"><Skeleton className="h-72" /></div> :
            q.error ? <div className="p-4"><ErrorState message={(q.error as Error).message} retry={() => q.refetch()} /></div> : (
              <Table>
                <THead>
                  <TR>
                    <SortHead k="symbol" label="Symbol" cur={sortKey} dir={sortDir} onClick={sortBy} align="left" />
                    <TH>Company</TH>
                    <SortHead k="last_price" label="Price" cur={sortKey} dir={sortDir} onClick={sortBy} align="right" />
                    <SortHead k="change_pct" label="Chg %" cur={sortKey} dir={sortDir} onClick={sortBy} align="right" />
                    <TH className="text-right">High</TH>
                    <TH className="text-right">Low</TH>
                    <TH className="text-right">52W H</TH>
                    <TH className="text-right">52W L</TH>
                    <SortHead k="volume" label="Volume" cur={sortKey} dir={sortDir} onClick={sortBy} align="right" />
                    <SortHead k="return_30d" label="30D %" cur={sortKey} dir={sortDir} onClick={sortBy} align="right" />
                    <SortHead k="return_1y" label="1Y %" cur={sortKey} dir={sortDir} onClick={sortBy} align="right" />
                  </TR>
                </THead>
                <TBody>
                  {rows.map((r) => (
                    <TR key={r.symbol}>
                      <TD>
                        <Link href={`/analyzer?symbol=${encodeURIComponent(r.symbol)}`} className="font-medium text-white hover:text-[var(--color-primary)] focus:outline-none focus:underline">
                          {r.symbol}
                        </Link>
                      </TD>
                      <TD className="text-xs muted truncate max-w-[200px]">{r.company ?? "—"}</TD>
                      <TD className="text-right tnum">{formatNum(r.last_price)}</TD>
                      <TD className={`text-right tnum ${trendClass(r.change_pct)}`}>{formatPct(r.change_pct, { sign: true })}</TD>
                      <TD className="text-right tnum muted">{formatNum(r.high)}</TD>
                      <TD className="text-right tnum muted">{formatNum(r.low)}</TD>
                      <TD className="text-right tnum muted">{formatNum(r.week52_high)}</TD>
                      <TD className="text-right tnum muted">{formatNum(r.week52_low)}</TD>
                      <TD className="text-right tnum muted">{formatNum(r.volume, { compact: true })}</TD>
                      <TD className={`text-right tnum ${trendClass(r.return_30d)}`}>{formatPct(r.return_30d, { sign: true })}</TD>
                      <TD className={`text-right tnum ${trendClass(r.return_1y)}`}>{formatPct(r.return_1y, { sign: true })}</TD>
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

function SortHead({ k, label, cur, dir, onClick, align }: {
  k: SortKey; label: string; cur: SortKey; dir: "asc" | "desc";
  onClick: (k: SortKey) => void; align: "left" | "right";
}) {
  const Active = cur === k;
  return (
    <TH className={align === "right" ? "text-right" : "text-left"}>
      <button
        type="button"
        onClick={() => onClick(k)}
        className="inline-flex items-center gap-1 hover:text-white focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)] rounded px-0.5"
      >
        {label}
        {Active && (dir === "asc" ? <ArrowUp className="size-3" /> : <ArrowDown className="size-3" />)}
      </button>
    </TH>
  );
}
