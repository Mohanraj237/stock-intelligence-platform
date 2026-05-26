"use client";
import * as TabsPrimitive from "@radix-ui/react-tabs";
import { cn } from "@/lib/utils";

export const Tabs = TabsPrimitive.Root;

export function TabsList({ className, ...rest }: React.ComponentProps<typeof TabsPrimitive.List>) {
  return (
    <TabsPrimitive.List
      className={cn(
        "inline-flex items-center gap-1 rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] p-1",
        className,
      )}
      {...rest}
    />
  );
}

export function TabsTrigger({ className, ...rest }: React.ComponentProps<typeof TabsPrimitive.Trigger>) {
  return (
    <TabsPrimitive.Trigger
      className={cn(
        "rounded px-3 py-1.5 text-xs font-medium text-[var(--color-text-muted)]",
        "data-[state=active]:bg-[var(--color-surface-2)] data-[state=active]:text-white",
        className,
      )}
      {...rest}
    />
  );
}

export function TabsContent({ className, ...rest }: React.ComponentProps<typeof TabsPrimitive.Content>) {
  return <TabsPrimitive.Content className={cn("mt-4", className)} {...rest} />;
}
