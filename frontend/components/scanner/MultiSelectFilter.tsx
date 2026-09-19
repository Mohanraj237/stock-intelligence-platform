"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Check, ChevronDown, Search, X } from "lucide-react";
import { cn } from "@/lib/utils";

export interface MultiSelectOption {
  value: string;
  label: string;
  /** How many rows carry this value — shown as a hint next to the label. */
  count?: number;
}

/**
 * Checkbox dropdown for filtering already-loaded results.
 *
 * Empty selection means "no filter" rather than "show nothing", so the default
 * state matches the plain <select> filters next to it.
 */
export function MultiSelectFilter({
  label,
  options,
  selected,
  onChange,
  allLabel = "All",
  searchPlaceholder = "Search…",
  width = "w-56",
}: {
  label:    string;
  options:  MultiSelectOption[];
  selected: Set<string>;
  onChange: (next: Set<string>) => void;
  allLabel?: string;
  searchPlaceholder?: string;
  width?:   string;
}) {
  const [open, setOpen]     = useState(false);
  const [query, setQuery]   = useState("");
  const rootRef             = useRef<HTMLDivElement>(null);

  // Close on outside click / Escape
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    return q ? options.filter((o) => o.label.toLowerCase().includes(q)) : options;
  }, [options, query]);

  const toggle = (value: string) => {
    const next = new Set(selected);
    if (next.has(value)) next.delete(value); else next.add(value);
    onChange(next);
  };

  const summary =
    selected.size === 0 ? allLabel
    : selected.size === 1 ? (options.find((o) => o.value === [...selected][0])?.label ?? "1 selected")
    : `${selected.size} selected`;

  return (
    <div className="flex flex-col gap-1" ref={rootRef}>
      <label className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)]">
        {label}
      </label>

      <div className="relative">
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          disabled={options.length === 0}
          className={cn(
            "flex items-center gap-2 bg-[var(--color-surface-2)] border border-[var(--color-border)]",
            "text-white text-[13px] rounded-lg px-3 py-2.5 text-left",
            "focus:outline-none focus:ring-1 focus:ring-[var(--color-primary)]",
            options.length === 0 && "opacity-40 cursor-not-allowed",
            width,
          )}
        >
          <span className={cn("flex-1 truncate", selected.size === 0 && "text-white/60")}>
            {summary}
          </span>
          {selected.size > 0 && (
            <span
              role="button"
              tabIndex={0}
              aria-label="Clear filter"
              onClick={(e) => { e.stopPropagation(); onChange(new Set()); }}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") { e.preventDefault(); e.stopPropagation(); onChange(new Set()); }
              }}
              className="shrink-0 text-white/40 hover:text-white"
            >
              <X className="size-3.5" />
            </span>
          )}
          <ChevronDown className={cn(
            "size-3.5 shrink-0 text-white/40 transition-transform", open && "rotate-180",
          )} />
        </button>

        {open && (
          <div className={cn(
            "absolute z-30 mt-1 rounded-lg border border-[var(--color-border)]",
            "bg-[var(--color-surface)] shadow-xl overflow-hidden", width,
          )}>
            {/* Search — pattern lists get long */}
            <div className="flex items-center gap-1.5 px-2.5 py-2 border-b border-white/10">
              <Search className="size-3 text-white/30 shrink-0" />
              <input
                autoFocus
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder={searchPlaceholder}
                className="flex-1 bg-transparent text-[12px] text-white placeholder:text-white/25 focus:outline-none"
              />
            </div>

            <div className="flex items-center gap-2 px-2.5 py-1.5 border-b border-white/10">
              <button
                onClick={() => onChange(new Set(options.map((o) => o.value)))}
                className="text-[10px] text-[var(--color-text-muted)] hover:text-white underline underline-offset-2"
              >
                Select all
              </button>
              <button
                onClick={() => onChange(new Set())}
                className="text-[10px] text-[var(--color-text-muted)] hover:text-white underline underline-offset-2"
              >
                Clear
              </button>
              <span className="ml-auto text-[10px] text-white/25">
                {visible.length} of {options.length}
              </span>
            </div>

            <div className="max-h-64 overflow-y-auto py-1">
              {visible.length === 0 && (
                <p className="px-3 py-2 text-[11px] text-white/30">No match</p>
              )}
              {visible.map((o) => {
                const active = selected.has(o.value);
                return (
                  <button
                    key={o.value}
                    onClick={() => toggle(o.value)}
                    className={cn(
                      "flex items-center gap-2 w-full px-2.5 py-1.5 text-left text-[12px]",
                      "hover:bg-white/5 transition-colors",
                      active ? "text-white" : "text-white/60",
                    )}
                  >
                    <span className={cn(
                      "flex items-center justify-center size-3.5 rounded border shrink-0",
                      active
                        ? "bg-[var(--color-primary)] border-[var(--color-primary)]"
                        : "border-white/20",
                    )}>
                      {active && <Check className="size-2.5 text-white" />}
                    </span>
                    <span className="flex-1 truncate">{o.label}</span>
                    {o.count !== undefined && (
                      <span className="text-[10px] text-white/25 shrink-0">{o.count}</span>
                    )}
                  </button>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

/**
 * Distinct patterns across a result set, most common first.
 *
 * Both the pattern shown on the card and every pattern detected on it are
 * offered, so the dropdown can never list something that matches nothing —
 * and can never omit something the Pattern(s) column displays.
 */
export function patternOptionsFromCards(
  cards: Array<{ pattern: string; patterns?: Array<{ name: string }> }>,
): MultiSelectOption[] {
  const counts = new Map<string, number>();
  for (const c of cards) {
    const names = new Set<string>();
    if (c.pattern && c.pattern !== "None") names.add(c.pattern);
    for (const p of c.patterns ?? []) if (p.name) names.add(p.name);
    for (const n of names) counts.set(n, (counts.get(n) ?? 0) + 1);
  }
  return [...counts.entries()]
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .map(([value, count]) => ({ value, label: value, count }));
}

/** True when a card carries at least one of the selected pattern names. */
export function cardMatchesPatterns(
  card: { pattern: string; patterns?: Array<{ name: string }> },
  selected: Set<string>,
): boolean {
  if (selected.size === 0) return true;
  if (card.pattern && selected.has(card.pattern)) return true;
  return (card.patterns ?? []).some((p) => selected.has(p.name));
}

/**
 * The pattern name to *display* for a card once a pattern filter is active.
 *
 * A card can survive `cardMatchesPatterns` via a pattern buried in its
 * `patterns[]` list that isn't the headline `pattern` shown on the card (the
 * scorer's single "best" pick, e.g. a Double Top, can easily outrank a
 * lower-tier pattern like a Fair Value Gap for the headline slot while the
 * FVG still fired). Without this rewrite, a card filtered to "Bearish FVG"
 * would still show "Double Top" in the Pattern(s) column — indistinguishable
 * from the filter not having worked at all. This mirrors the equivalent
 * rewrite already done server-side for the pre-scan pattern filter
 * (`services/scan_support.py::apply_pattern_filters`), so both filtering
 * paths give the same "you always see a pattern you selected" guarantee.
 */
export function displayPatternFor(
  card: { pattern: string; patterns?: Array<{ name: string; confidence?: number }> },
  selected: Set<string>,
): string {
  if (selected.size === 0 || (card.pattern && selected.has(card.pattern))) {
    return card.pattern;
  }
  const matches = (card.patterns ?? []).filter((p) => selected.has(p.name));
  if (matches.length === 0) return card.pattern;
  const best = matches.reduce((a, b) => (b.confidence ?? 0) > (a.confidence ?? 0) ? b : a);
  return best.name;
}

/**
 * Distinct timeframes across a result set, most common first. Each scanner
 * supplies its own display label (e.g. "1d" -> "Daily" on the equity scanner,
 * "1d" -> "Daily" vs "5m" -> "5 min" on the F&O live scanner) since the two
 * scanners use different timeframe sets and labelling conventions.
 */
export function timeframeOptionsFromCards(
  cards: Array<{ timeframe: string }>,
  labelFor: (tf: string) => string = (tf) => tf,
): MultiSelectOption[] {
  const counts = new Map<string, number>();
  for (const c of cards) {
    if (c.timeframe) counts.set(c.timeframe, (counts.get(c.timeframe) ?? 0) + 1);
  }
  return [...counts.entries()]
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .map(([value, count]) => ({ value, label: labelFor(value), count }));
}

/** True when a card's timeframe is in the selection (empty selection = no filter). */
export function cardMatchesTimeframe(
  card: { timeframe: string },
  selected: Set<string>,
): boolean {
  return selected.size === 0 || selected.has(card.timeframe);
}
