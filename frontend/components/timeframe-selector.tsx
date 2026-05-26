"use client";
import { useRef } from "react";
import { TIMEFRAMES, type Timeframe, TIMEFRAME_LABEL } from "@/lib/types";
import { cn } from "@/lib/utils";

export function TimeframeSelector({
  value, onChange, className,
}: {
  value: Timeframe;
  onChange: (tf: Timeframe) => void;
  className?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);

  const onKeyDown: React.KeyboardEventHandler<HTMLDivElement> = (e) => {
    const idx = TIMEFRAMES.indexOf(value);
    let next: number | null = null;
    if (e.key === "ArrowRight" || e.key === "ArrowDown")  next = (idx + 1) % TIMEFRAMES.length;
    if (e.key === "ArrowLeft"  || e.key === "ArrowUp")    next = (idx - 1 + TIMEFRAMES.length) % TIMEFRAMES.length;
    if (e.key === "Home") next = 0;
    if (e.key === "End")  next = TIMEFRAMES.length - 1;
    if (next === null) return;
    e.preventDefault();
    const tf = TIMEFRAMES[next];
    onChange(tf);
    requestAnimationFrame(() => {
      const btn = ref.current?.querySelector<HTMLButtonElement>(`[data-tf="${tf}"]`);
      btn?.focus();
    });
  };

  return (
    <div
      ref={ref}
      role="radiogroup"
      aria-label="Timeframe"
      onKeyDown={onKeyDown}
      className={cn(
        "inline-flex items-center gap-0.5 rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] p-0.5",
        className,
      )}
    >
      {TIMEFRAMES.map((tf) => {
        const active = tf === value;
        return (
          <button
            key={tf}
            type="button"
            data-tf={tf}
            role="radio"
            aria-checked={active}
            tabIndex={active ? 0 : -1}
            onClick={() => onChange(tf)}
            className={cn(
              "px-3 py-1 text-xs rounded transition-colors tnum",
              "focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)]",
              active
                ? "bg-[var(--color-surface-2)] text-white"
                : "text-[var(--color-text-muted)] hover:text-white",
            )}
            title={TIMEFRAME_LABEL[tf]}
          >
            {tf}
          </button>
        );
      })}
    </div>
  );
}
