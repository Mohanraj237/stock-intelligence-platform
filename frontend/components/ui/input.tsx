import { forwardRef } from "react";
import { cn } from "@/lib/utils";

export const Input = forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...rest }, ref) => (
    <input
      ref={ref}
      className={cn(
        "flex h-9 w-full rounded-md border border-[var(--color-border)] bg-[var(--color-surface)]",
        "px-3 py-1 text-sm text-white placeholder:text-[var(--color-text-muted)]",
        "focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)] focus:ring-offset-1 focus:ring-offset-[var(--color-bg)]",
        "disabled:opacity-50 disabled:cursor-not-allowed tnum",
        className,
      )}
      {...rest}
    />
  ),
);
Input.displayName = "Input";
