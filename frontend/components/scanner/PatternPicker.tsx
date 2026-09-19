"use client";

import { useState } from "react";
import { ChevronDown, Info } from "lucide-react";
import { cn } from "@/lib/utils";
import type { PatternGroups, PatternMode, PatternOption } from "@/lib/scanner-types";

export const FAMILY_META: Record<string, { label: string; active: string; muted: string }> = {
  candlestick:  { label: "Candlestick",   active: "text-yellow-300 border-yellow-500/50 bg-yellow-500/15", muted: "text-yellow-400/60" },
  price_action: { label: "Price Action",  active: "text-blue-300   border-blue-500/50   bg-blue-500/15",   muted: "text-blue-400/60"   },
  volume:       { label: "Volume",        active: "text-orange-300 border-orange-500/50 bg-orange-500/15", muted: "text-orange-400/60" },
  chart:        { label: "Chart Pattern", active: "text-purple-300 border-purple-500/50 bg-purple-500/15", muted: "text-purple-400/60" },
  harmonic:     { label: "Harmonic",      active: "text-pink-300   border-pink-500/50   bg-pink-500/15",   muted: "text-pink-400/60"   },
  smc:          { label: "Smart Money",   active: "text-emerald-300 border-emerald-500/50 bg-emerald-500/15", muted: "text-emerald-400/60" },
};

/** Every id a top-level option owns, including its directional variants. */
function idsOf(p: PatternOption): string[] {
  return [p.pattern_id, ...p.variants.map((v) => v.pattern_id)];
}

function familyIds(patterns: PatternOption[]): string[] {
  return patterns.flatMap(idsOf);
}

/**
 * Two-level pattern selector.
 *
 * Selection is by `pattern_id`, not display text. Selecting a parent selects
 * its directional variants too — picking "Inside Bar" used to silently discard
 * every "Inside Bar Breakout" hit because matching was on the exact emitted
 * name.
 */
export function PatternPicker({
  groups,
  loading,
  selected,
  onChange,
  mode,
  onModeChange,
}: {
  groups:   PatternGroups;
  loading:  boolean;
  selected: Set<string>;
  onChange: (next: Set<string>) => void;
  mode:     PatternMode;
  onModeChange: (m: PatternMode) => void;
}) {
  const [open, setOpen]                     = useState(false);
  const [expandedFamilies, setExpanded]     = useState<Set<string>>(new Set());

  const toggleIds = (ids: string[], on: boolean) => {
    const next = new Set(selected);
    ids.forEach((id) => (on ? next.add(id) : next.delete(id)));
    onChange(next);
  };

  const toggleFamilyOpen = (family: string) =>
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(family)) next.delete(family); else next.add(family);
      return next;
    });

  const count = selected.size;

  return (
    <div className="pt-3 border-t border-[var(--color-border)]">
      <div
        role="button"
        tabIndex={0}
        onClick={() => setOpen((v) => !v)}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setOpen((v) => !v); }
        }}
        className="flex items-center gap-2 w-full text-left group cursor-pointer"
      >
        <ChevronDown className={cn(
          "size-3.5 text-white/40 transition-transform duration-150 shrink-0",
          !open && "-rotate-90",
        )} />
        <span className="text-[11px] uppercase tracking-wider text-[var(--color-text-muted)] group-hover:text-white/70 transition-colors">
          Patterns
        </span>
        {count > 0 ? (
          <span className="text-[11px] text-[var(--color-primary)] font-medium">
            {count} selected
          </span>
        ) : (
          <span className="text-[11px] text-[var(--color-text-muted)]">— all patterns (no filter)</span>
        )}
        {count > 0 && (
          <button
            onClick={(e) => { e.stopPropagation(); onChange(new Set()); }}
            className="ml-auto text-[10px] text-[var(--color-text-muted)] hover:text-white underline underline-offset-2"
          >
            Clear all
          </button>
        )}
      </div>

      {open && (
        <div className="mt-3 space-y-2">
          {loading && (
            <p className="text-[11px] text-[var(--color-text-muted)]">Loading patterns…</p>
          )}

          {/* How the selection is applied — this changes what the score means. */}
          <div className="rounded-lg border border-white/6 bg-white/2 px-3 py-2.5 space-y-1.5">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-[10px] font-semibold uppercase tracking-wider text-[var(--color-text-muted)]">
                Apply selection as
              </span>
              {([
                { value: "filter", label: "Filter results" },
                { value: "shape",  label: "Shape the score" },
              ] as const).map((o) => (
                <button
                  key={o.value}
                  onClick={() => onModeChange(o.value)}
                  className={cn(
                    "px-2.5 py-0.5 rounded-full text-[11px] font-medium border transition-all",
                    mode === o.value
                      ? "text-white border-[var(--color-primary)] bg-[var(--color-primary)]/20"
                      : "border-white/10 text-white/35 hover:text-white/55 hover:border-white/20",
                  )}
                >
                  {o.label}
                </button>
              ))}
            </div>
            <p className="flex items-start gap-1.5 text-[11px] text-[var(--color-text-muted)]">
              <Info className="size-3 mt-0.5 shrink-0" />
              {mode === "filter"
                ? "Scores are computed from every pattern, then only setups containing one of your picks are shown. A score of 72 means the same thing here as in an unfiltered scan."
                : "Only your picks may contribute to the Candle Trigger and Structural categories, so scores drop by up to 30 points. Lower the minimum score to compensate."}
            </p>
          </div>

          {Object.entries(groups).map(([family, patterns]) => {
            const meta     = FAMILY_META[family]
              ?? { label: family, active: "text-white border-white/30 bg-white/10", muted: "text-white/60" };
            const allIds   = familyIds(patterns);
            const allSel   = allIds.every((id) => selected.has(id));
            const famOpen  = expandedFamilies.has(family);
            const selCount = allIds.filter((id) => selected.has(id)).length;

            return (
              <div key={family} className="rounded-lg border border-white/6 bg-white/2 overflow-hidden">
                <div
                  role="button"
                  tabIndex={0}
                  onClick={() => toggleFamilyOpen(family)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggleFamilyOpen(family); }
                  }}
                  className="flex items-center gap-2 w-full px-3 py-2 text-left hover:bg-white/5 transition-colors cursor-pointer"
                >
                  <ChevronDown className={cn(
                    "size-3 text-white/30 transition-transform duration-150 shrink-0",
                    !famOpen && "-rotate-90",
                  )} />
                  <span className={cn("text-[10px] font-semibold uppercase tracking-wider", meta.muted)}>
                    {meta.label}
                  </span>
                  <span className="text-[9px] text-white/20">({allIds.length})</span>
                  {selCount > 0 && (
                    <span className={cn("text-[9px] font-medium ml-1", meta.muted)}>
                      {selCount} selected
                    </span>
                  )}
                  {famOpen && (
                    <button
                      onClick={(e) => { e.stopPropagation(); toggleIds(allIds, !allSel); }}
                      className="ml-auto text-[9px] text-[var(--color-text-muted)] hover:text-white underline underline-offset-2"
                    >
                      {allSel ? "Deselect all" : "Select all"}
                    </button>
                  )}
                </div>

                {famOpen && (
                  <div className="flex flex-wrap gap-1.5 px-3 pb-3 pt-1">
                    {patterns.map((p) => {
                      const ids    = idsOf(p);
                      const active = selected.has(p.pattern_id);
                      return (
                        <span key={p.pattern_id} className="inline-flex items-center gap-0.5">
                          <button
                            onClick={() => toggleIds(ids, !active)}
                            title={p.variants.length
                              ? `Also selects: ${p.variants.map((v) => v.name).join(", ")}`
                              : undefined}
                            className={cn(
                              "px-2.5 py-0.5 rounded-full text-[11px] font-medium border transition-all",
                              active
                                ? meta.active
                                : "border-white/10 text-white/35 bg-transparent hover:text-white/55 hover:border-white/20",
                            )}
                          >
                            {p.name}
                            {p.variants.length > 0 && (
                              <span className="ml-1 opacity-50">+{p.variants.length}</span>
                            )}
                          </button>
                          {/* Variants are individually selectable too. */}
                          {p.variants.map((v) => {
                            const vActive = selected.has(v.pattern_id);
                            return (
                              <button
                                key={v.pattern_id}
                                onClick={() => toggleIds([v.pattern_id], !vActive)}
                                title={v.name}
                                className={cn(
                                  "px-1.5 py-0.5 rounded-full text-[10px] font-medium border transition-all",
                                  vActive
                                    ? meta.active
                                    : "border-white/8 text-white/25 bg-transparent hover:text-white/45",
                                )}
                              >
                                {v.direction === "bearish" ? "↓" : "↑"}
                              </button>
                            );
                          })}
                        </span>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
