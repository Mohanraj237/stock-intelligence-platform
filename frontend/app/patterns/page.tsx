"use client";
import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { Beaker } from "lucide-react";
import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Table, THead, TBody, TR, TH, TD } from "@/components/ui/table";
import { EmptyState, ErrorState } from "@/components/ui/empty-state";
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from "@/components/ui/select";
import { UniverseSelect } from "@/components/common/universe-select";
import { PageHeader } from "@/components/common/page-header";
import { ScanProgressCard, type ScanProgress } from "@/components/common/scan-progress";
import type { Direction, Timeframe, PatternScanResult } from "@/lib/types";
import { TIMEFRAMES, TIMEFRAME_LABEL } from "@/lib/types";
import { formatNum, formatPct, trendClass } from "@/lib/utils";
import { streamPost } from "@/lib/sse";
import { toast } from "sonner";
import { useRegion } from "@/lib/region";

export default function PatternsPage() {
  const { region, isUS } = useRegion();
  const lib = useQuery({ queryKey: ["pattern-library"], queryFn: api.patternLibrary });
  const [universe, setUniverse] = useState(isUS ? "S&P 500" : "NIFTY 50");
  useEffect(() => { setUniverse(isUS ? "S&P 500" : "NIFTY 50"); }, [isUS]);
  const [direction, setDirection] = useState<"all" | Direction>("all");
  const [tfs, setTfs] = useState<Timeframe[]>(["1D", "1W", "1M"]);
  const [minConf, setMinConf] = useState("60");
  const [selectedPatterns, setSelectedPatterns] = useState<string[]>([]);

  const [scanning, setScanning] = useState(false);
  const [progress, setProgress] = useState<ScanProgress>({ done: 0, total: 0, matched: 0 });
  const [result, setResult] = useState<PatternScanResult | null>(null);
  const [scanError, setScanError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const startScan = async () => {
    if (tfs.length === 0) { toast.error("Pick at least one timeframe"); return; }
    setScanning(true); setResult(null); setScanError(null);
    setProgress({ done: 0, total: 0, matched: 0 });
    const ctl = new AbortController();
    abortRef.current = ctl;
    await streamPost<PatternScanResult>("/api/patterns/scan/stream", {
      universe, pattern_names: selectedPatterns,
      direction: direction === "all" ? null : direction,
      timeframes: tfs, min_confidence: Number(minConf),
      breakout_states: [], max_symbols: null, region,
    }, {
      onStart:    (e) => setProgress({ done: 0, total: e.total ?? 0, matched: 0, current: "" }),
      onProgress: (e) => setProgress({ done: e.done ?? 0, total: e.total ?? 0, matched: e.matched ?? 0, current: e.current, elapsedMs: e.elapsed_ms }),
      onResult:   (r) => setResult(r),
      onDone:     () => setScanning(false),
      onError:    (err) => { setScanError(err.message); setScanning(false); },
      signal:     ctl.signal,
    });
  };

  const cancelScan = () => {
    abortRef.current?.abort();
    setScanning(false);
    setScanError("Cancelled");
  };

  const scan = result;

  const toggleTf = (tf: Timeframe) => setTfs((cur) => cur.includes(tf) ? cur.filter((x) => x !== tf) : [...cur, tf]);
  const togglePattern = (name: string) => setSelectedPatterns((cur) => cur.includes(name) ? cur.filter((x) => x !== name) : [...cur, name]);

  return (
    <div className="max-w-[1500px] mx-auto space-y-5">
      <PageHeader title="Pattern Lab" subtitle="Multi-timeframe chart-pattern detection with confluence scoring." />

      <Card>
        <CardHeader><CardTitle>Configure scan</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          <div className="grid md:grid-cols-3 gap-3">
            <div className="space-y-1">
              <Label>Universe</Label>
              <UniverseSelect value={universe} onChange={setUniverse} />
            </div>
            <div className="space-y-1">
              <Label>Direction</Label>
              <Select value={direction} onValueChange={(v) => setDirection(v as "all" | Direction)}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All</SelectItem>
                  <SelectItem value="Bullish">Bullish</SelectItem>
                  <SelectItem value="Bearish">Bearish</SelectItem>
                  <SelectItem value="Neutral">Neutral</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label>Min confidence</Label>
              <Input type="number" min={0} max={100} value={minConf} onChange={(e) => setMinConf(e.target.value)} />
            </div>
          </div>

          <div>
            <Label>Timeframes</Label>
            <div className="flex flex-wrap gap-2 mt-1">
              {TIMEFRAMES.map((tf) => {
                const active = tfs.includes(tf);
                return (
                  <button
                    key={tf}
                    type="button"
                    aria-pressed={active}
                    onClick={() => toggleTf(tf)}
                    className={`px-3 py-1 text-xs rounded border transition-colors focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)] ${
                      active
                        ? "border-[var(--color-primary)] bg-[var(--color-primary)] text-white"
                        : "border-[var(--color-border)] muted hover:text-white"
                    }`}
                  >
                    {tf} · {TIMEFRAME_LABEL[tf]}
                  </button>
                );
              })}
            </div>
          </div>

          <div>
            <Label>Patterns ({selectedPatterns.length === 0 ? "All" : `${selectedPatterns.length} selected`})</Label>
            <div className="flex flex-wrap gap-1.5 mt-1 max-h-32 overflow-y-auto p-2 rounded border border-[var(--color-border)] bg-[var(--color-surface-2)]/40">
              {(lib.data ?? []).map((p) => {
                const active = selectedPatterns.includes(p.name);
                return (
                  <button
                    key={p.name}
                    type="button"
                    aria-pressed={active}
                    onClick={() => togglePattern(p.name)}
                    className={`px-2 py-0.5 text-[11px] rounded border transition-colors focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)] ${
                      active
                        ? "border-[var(--color-primary)] bg-[var(--color-primary)] text-white"
                        : "border-[var(--color-border)] muted hover:text-white"
                    }`}
                  >
                    {p.name}
                  </button>
                );
              })}
            </div>
          </div>

          <Button onClick={startScan} disabled={scanning || tfs.length === 0}>
            {scanning ? "Scanning…" : "Run pattern scan"}
          </Button>
        </CardContent>
      </Card>

      {scanning && <ScanProgressCard progress={progress} onCancel={cancelScan} label="Scanning patterns" />}
      {scanError && !scanning && <ErrorState message={scanError} retry={startScan} />}

      {scan && (
        <Card>
          <CardHeader>
            <CardTitle>
              Hits · {scan.total_matched}/{scan.total_scanned} matched ·{" "}
              <span className="text-xs font-normal muted">{(scan.duration_ms / 1000).toFixed(1)}s</span>
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            {scan.rows.length === 0 ? (
              <div className="p-4"><EmptyState icon={Beaker} title="No matches" description="Loosen min-confidence or pick more timeframes." /></div>
            ) : (
              <Table>
                <THead><TR>
                  <TH>Symbol</TH>
                  <TH className="text-right">Price</TH>
                  <TH className="text-right">Confluence</TH>
                  <TH>TFs</TH>
                  <TH>Patterns</TH>
                </TR></THead>
                <TBody>
                  {scan.rows.map((r, i) => (
                    <TR key={`${r.symbol}-${i}`}>
                      <TD>
                        <Link href={`/analyzer?symbol=${encodeURIComponent(r.symbol)}`} className="font-medium text-white hover:text-[var(--color-primary)] focus:outline-none focus:underline">
                          {r.symbol}
                        </Link>
                      </TD>
                      <TD className="text-right tnum">{formatNum(r.last_price)}</TD>
                      <TD className={`text-right tnum ${trendClass(r.confluence_score - 50)}`}>{r.confluence_score.toFixed(0)}</TD>
                      <TD className="text-xs muted">{r.timeframes_present.join(", ") || "—"}</TD>
                      <TD>
                        <div className="flex flex-wrap gap-1">
                          {r.patterns.slice(0, 4).map((p, j) => (
                            <Badge key={j} variant={p.direction === "Bullish" ? "success" : p.direction === "Bearish" ? "danger" : "default"}>
                              {p.name} ({p.confidence.toFixed(0)})
                            </Badge>
                          ))}
                          {r.patterns.length > 4 && <Badge variant="default">+{r.patterns.length - 4}</Badge>}
                        </div>
                      </TD>
                    </TR>
                  ))}
                </TBody>
              </Table>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
