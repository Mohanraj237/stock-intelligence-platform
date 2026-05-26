"use client";
import { useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { Radar } from "lucide-react";
import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Table, THead, TBody, TR, TH, TD } from "@/components/ui/table";
import { EmptyState, ErrorState } from "@/components/ui/empty-state";
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from "@/components/ui/select";
import { UniverseSelect } from "@/components/common/universe-select";
import { PageHeader } from "@/components/common/page-header";
import { ScanProgressCard, type ScanProgress } from "@/components/common/scan-progress";
import { formatNum, formatPct, trendClass } from "@/lib/utils";
import { streamPost } from "@/lib/sse";
import type { ScanResult } from "@/lib/types";
import { toast } from "sonner";

export default function ScannerPage() {
  const types = useQuery({ queryKey: ["scan-types"], queryFn: api.scanTypes });
  const [universe, setUniverse] = useState("NIFTY 50");
  const [scanType, setScanType] = useState("breakout_ready");

  const [scanning, setScanning] = useState(false);
  const [progress, setProgress] = useState<ScanProgress>({ done: 0, total: 0, matched: 0 });
  const [result, setResult] = useState<ScanResult | null>(null);
  const [scanError, setScanError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const startScan = async () => {
    setScanning(true); setResult(null); setScanError(null);
    setProgress({ done: 0, total: 0, matched: 0 });
    const ctl = new AbortController();
    abortRef.current = ctl;
    await streamPost<ScanResult>("/api/scans/run/stream", {
      universe, scan_type: scanType, filters: {}, enable_ai: false, max_symbols: null,
    }, {
      onStart:    (e) => setProgress({ done: 0, total: e.total ?? 0, matched: 0, current: "" }),
      onProgress: (e) => setProgress({ done: e.done ?? 0, total: e.total ?? 0, matched: e.matched ?? 0, current: e.current, elapsedMs: e.elapsed_ms }),
      onResult:   (r) => setResult(r),
      onDone:     () => setScanning(false),
      onError:    (err) => { setScanError(err.message); setScanning(false); toast.error(err.message); },
      signal:     ctl.signal,
    });
  };

  const cancelScan = () => { abortRef.current?.abort(); setScanning(false); setScanError("Cancelled"); };

  return (
    <div className="max-w-[1500px] mx-auto space-y-5">
      <PageHeader title="Scanner" subtitle="12 pre-built scans across any NSE index, with full audit trail." />

      <Card>
        <CardHeader><CardTitle>Configure scan</CardTitle></CardHeader>
        <CardContent>
          <form
            onSubmit={(e) => { e.preventDefault(); startScan(); }}
            className="grid md:grid-cols-3 gap-3 items-end"
          >
            <div className="space-y-1">
              <Label>Universe</Label>
              <UniverseSelect value={universe} onChange={setUniverse} />
            </div>
            <div className="space-y-1">
              <Label>Scan type</Label>
              <Select value={scanType} onValueChange={setScanType}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {(types.data ?? []).map((t) => (
                    <SelectItem key={t.id} value={t.id}>{t.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <Button type="submit" disabled={scanning}>
              {scanning ? "Scanning…" : "Run scan"}
            </Button>
          </form>
          {scanType && types.data && (
            <p className="text-xs muted mt-3">
              {types.data.find((t) => t.id === scanType)?.desc}
            </p>
          )}
        </CardContent>
      </Card>

      {scanning && <ScanProgressCard progress={progress} onCancel={cancelScan} label="Scanning" />}
      {scanError && !scanning && <ErrorState message={scanError} retry={startScan} />}

      {result && (
        <Card>
          <CardHeader>
            <CardTitle>
              Results · {result.total_matched}/{result.total_scanned} matched ·{" "}
              <span className="muted text-xs font-normal">{(result.duration_ms / 1000).toFixed(1)}s</span>
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            {result.rows.length === 0 ? (
              <div className="p-4"><EmptyState icon={Radar} title="No matches" description="Try a different universe or relax the scan." /></div>
            ) : (
              <Table>
                <THead><TR>
                  <TH>Symbol</TH>
                  <TH className="text-right">Price</TH>
                  <TH className="text-right">Chg %</TH>
                  <TH className="text-right">RSI</TH>
                  <TH className="text-right">ADX</TH>
                  <TH className="text-right">SMA50</TH>
                  <TH className="text-right">SMA200</TH>
                  <TH className="text-right">MACD bull</TH>
                </TR></THead>
                <TBody>
                  {result.rows.map((r, i) => (
                    <TR key={`${r.symbol}-${i}`}>
                      <TD>
                        <Link href={`/analyzer?symbol=${encodeURIComponent(r.symbol)}`} className="font-medium text-white hover:text-[var(--color-primary)] focus:outline-none focus:underline">
                          {r.symbol}
                        </Link>
                      </TD>
                      <TD className="text-right tnum">{formatNum(r.last_price)}</TD>
                      <TD className={`text-right tnum ${trendClass(r.change_pct)}`}>{formatPct(r.change_pct, { sign: true })}</TD>
                      <TD className="text-right tnum">{formatNum(r.rsi, { maxFrac: 1 })}</TD>
                      <TD className="text-right tnum">{formatNum(r.adx, { maxFrac: 1 })}</TD>
                      <TD className="text-right tnum muted">{formatNum(r.sma50)}</TD>
                      <TD className="text-right tnum muted">{formatNum(r.sma200)}</TD>
                      <TD className="text-right text-xs">{r.macd_bullish ? "yes" : "no"}</TD>
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
