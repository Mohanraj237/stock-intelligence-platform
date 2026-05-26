"use client";
import { Activity } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

export interface ScanProgress {
  done: number;
  total: number;
  matched?: number;
  current?: string;
  elapsedMs?: number;
}

export function ScanProgressCard({
  progress, onCancel, label = "Scanning",
}: {
  progress: ScanProgress;
  onCancel?: () => void;
  label?: string;
}) {
  const pct = progress.total > 0 ? Math.min(100, (progress.done / progress.total) * 100) : 0;
  const eta =
    progress.elapsedMs && progress.done > 0 && progress.total > 0
      ? ((progress.elapsedMs / progress.done) * (progress.total - progress.done)) / 1000
      : null;

  return (
    <Card>
      <CardContent className="p-4">
        <div className="flex items-center justify-between gap-4 mb-3">
          <div className="flex items-center gap-2">
            <Activity className="size-4 text-[var(--color-primary)] animate-pulse" />
            <span className="text-sm font-medium text-white">
              {label} · <span className="tnum">{progress.done}</span>
              <span className="muted"> / {progress.total}</span>
            </span>
            {(progress.matched ?? 0) > 0 && (
              <span className="text-xs muted">· {progress.matched} matches so far</span>
            )}
          </div>
          <div className="flex items-center gap-3 text-xs muted">
            {progress.current && (
              <span className="tnum">Current: <span className="text-white">{progress.current}</span></span>
            )}
            {eta !== null && eta > 1 && (
              <span className="tnum">ETA ~ {Math.round(eta)}s</span>
            )}
            {onCancel && (
              <Button size="sm" variant="ghost" onClick={onCancel}>Cancel</Button>
            )}
          </div>
        </div>
        <div className="h-2 rounded-full bg-[var(--color-surface-2)] overflow-hidden">
          <div
            className="h-full rounded-full bg-[var(--color-primary)] transition-all duration-200"
            style={{ width: `${pct}%` }}
            role="progressbar"
            aria-valuenow={Math.round(pct)}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label={`${label} ${Math.round(pct)}% complete`}
          />
        </div>
        <div className="flex items-center justify-between mt-1 text-[10px] muted tnum">
          <span>{pct.toFixed(0)}%</span>
          {progress.elapsedMs !== undefined && (
            <span>{(progress.elapsedMs / 1000).toFixed(1)}s elapsed</span>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
