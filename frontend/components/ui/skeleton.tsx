import { cn } from "@/lib/utils";

export function Skeleton({ className, ...rest }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      role="status"
      aria-label="Loading"
      className={cn("animate-pulse rounded-md bg-[var(--color-surface-2)]", className)}
      {...rest}
    />
  );
}
