"use client";
import * as LabelPrimitive from "@radix-ui/react-label";
import { cn } from "@/lib/utils";

export function Label({ className, ...rest }: React.ComponentProps<typeof LabelPrimitive.Root>) {
  return (
    <LabelPrimitive.Root
      className={cn(
        "text-xs font-medium text-[var(--color-text-muted)] peer-disabled:opacity-50",
        className,
      )}
      {...rest}
    />
  );
}
