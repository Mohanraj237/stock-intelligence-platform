import { cn } from "@/lib/utils";

export function KPI({
  label, value, hint, trend, className,
}: {
  label: string;
  value: React.ReactNode;
  hint?: React.ReactNode;
  trend?: "up" | "down" | "neutral";
  className?: string;
}) {
  return (
    <div className={cn("rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] p-3", className)}>
      <div className="text-[11px] uppercase tracking-wider muted">{label}</div>
      <div className={cn(
        "mt-1 text-lg font-semibold tnum",
        trend === "up" ? "up" : trend === "down" ? "down" : "text-white",
      )}>
        {value}
      </div>
      {hint && <div className="text-[11px] muted mt-1">{hint}</div>}
    </div>
  );
}
