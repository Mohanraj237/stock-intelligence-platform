"use client";

import * as RadixTooltip from "@radix-ui/react-tooltip";
import { cn } from "@/lib/utils";

/**
 * HelpTip — inline jargon tooltip (P2-10).
 * Wraps any inline element; shows `tip` text on hover/focus.
 *
 * Usage:
 *   <HelpTip tip="Put-Call Ratio: total PE OI ÷ total CE OI">PCR</HelpTip>
 */
export function HelpTip({
  tip,
  children,
  className,
}: {
  tip: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <RadixTooltip.Provider delayDuration={200}>
      <RadixTooltip.Root>
        <RadixTooltip.Trigger asChild>
          <span
            className={cn(
              "cursor-help border-b border-dotted border-[var(--color-text-muted)] text-inherit",
              className,
            )}
            tabIndex={0}
          >
            {children}
          </span>
        </RadixTooltip.Trigger>
        <RadixTooltip.Portal>
          <RadixTooltip.Content
            side="top"
            align="center"
            sideOffset={4}
            className="z-50 max-w-xs rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-[11px] text-[var(--color-text)] shadow-xl leading-relaxed animate-in fade-in-0 zoom-in-95"
          >
            {tip}
            <RadixTooltip.Arrow className="fill-[var(--color-border)]" />
          </RadixTooltip.Content>
        </RadixTooltip.Portal>
      </RadixTooltip.Root>
    </RadixTooltip.Provider>
  );
}
