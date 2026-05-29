"use client";
/**
 * Typeahead for NSE stock symbols.
 *
 * Loads the merged universe catalog once (cached for an hour by TanStack Query),
 * filters in-memory as the user types, and shows a keyboard-navigable dropdown.
 *
 * Ranking: exact symbol > symbol prefix > symbol contains > company contains.
 */
import { useEffect, useMemo, useRef, useState, useId } from "react";
import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { useRegion } from "@/lib/region";
import type { Region } from "@/lib/api";

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ||
  process.env.API_URL ||
  "http://127.0.0.1:8000";

interface CatalogEntry { symbol: string; company: string }

async function fetchCatalog(region: Region): Promise<CatalogEntry[]> {
  const res = await fetch(`${API_BASE}/api/universe/all-symbols?region=${region}`);
  if (!res.ok) throw new Error(`Catalog HTTP ${res.status}`);
  return res.json();
}

export interface SymbolAutocompleteProps {
  value: string;
  onChange: (sym: string) => void;
  /** Fires when the user explicitly picks a row (Enter or click). */
  onSelect?: (sym: string) => void;
  placeholder?: string;
  className?: string;
  inputClassName?: string;
  autoFocus?: boolean;
  ariaLabel?: string;
  /** Hide the dropdown — useful when caller just wants free-text input. */
  disableSuggestions?: boolean;
}

export function SymbolAutocomplete({
  value, onChange, onSelect,
  placeholder = "Search by symbol or company",
  className, inputClassName, autoFocus, ariaLabel = "Stock symbol",
  disableSuggestions,
}: SymbolAutocompleteProps) {
  const { region } = useRegion();
  const listboxId = useId();
  const wrapRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);

  const catalog = useQuery({
    queryKey: ["symbol-catalog", region],
    queryFn: () => fetchCatalog(region),
    staleTime: 60 * 60_000,           // 1h
    gcTime: 24 * 60 * 60_000,         // 24h
  });

  const matches = useMemo<CatalogEntry[]>(() => {
    const all = catalog.data ?? [];
    const q = value.trim();
    if (!q) return all.slice(0, 12);
    const qu = q.toUpperCase();
    const ql = q.toLowerCase();
    const ranked: { rank: number; e: CatalogEntry }[] = [];
    for (const e of all) {
      const s = e.symbol;
      const c = (e.company || "").toLowerCase();
      if (s === qu)               ranked.push({ rank: 0, e });
      else if (s.startsWith(qu))  ranked.push({ rank: 1, e });
      else if (s.includes(qu))    ranked.push({ rank: 2, e });
      else if (c.includes(ql))    ranked.push({ rank: 3, e });
      if (ranked.length >= 50) break;
    }
    ranked.sort((a, b) => a.rank - b.rank || a.e.symbol.localeCompare(b.e.symbol));
    return ranked.slice(0, 12).map((r) => r.e);
  }, [catalog.data, value]);

  // Reset active index when the candidate set shrinks/grows
  useEffect(() => { if (active >= matches.length) setActive(0); }, [matches, active]);

  // Click-outside to close
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (!wrapRef.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  const pick = (sym: string) => {
    onChange(sym);
    setOpen(false);
    onSelect?.(sym);
    requestAnimationFrame(() => inputRef.current?.blur());
  };

  const onKeyDown: React.KeyboardEventHandler<HTMLInputElement> = (e) => {
    if (disableSuggestions) return;
    if (!open && (e.key === "ArrowDown" || e.key === "ArrowUp")) {
      setOpen(true); e.preventDefault(); return;
    }
    if (e.key === "ArrowDown") { e.preventDefault(); setActive((i) => Math.min(matches.length - 1, i + 1)); }
    else if (e.key === "ArrowUp")   { e.preventDefault(); setActive((i) => Math.max(0, i - 1)); }
    else if (e.key === "Home")      { e.preventDefault(); setActive(0); }
    else if (e.key === "End")       { e.preventDefault(); setActive(matches.length - 1); }
    else if (e.key === "Enter") {
      const pick_ = matches[active];
      if (open && pick_) { e.preventDefault(); pick(pick_.symbol); }
      else if (value.trim()) { e.preventDefault(); onSelect?.(value.trim().toUpperCase()); }
    }
    else if (e.key === "Escape" && open) {
      e.preventDefault(); setOpen(false);
    }
  };

  const showDropdown = open && !disableSuggestions && matches.length > 0;

  return (
    <div ref={wrapRef} className={cn("relative", className)}>
      <Search className="size-4 absolute left-2 top-1/2 -translate-y-1/2 text-[var(--color-text-muted)] pointer-events-none" />
      <Input
        ref={inputRef}
        value={value}
        onChange={(e) => { onChange(e.target.value); setOpen(true); setActive(0); }}
        onFocus={() => setOpen(true)}
        onKeyDown={onKeyDown}
        placeholder={placeholder}
        autoFocus={autoFocus}
        aria-label={ariaLabel}
        aria-autocomplete="list"
        aria-controls={listboxId}
        aria-expanded={showDropdown}
        aria-activedescendant={showDropdown ? `${listboxId}-opt-${active}` : undefined}
        role="combobox"
        autoComplete="off"
        spellCheck={false}
        className={cn("pl-8 uppercase", inputClassName)}
      />
      {showDropdown && (
        <ul
          role="listbox"
          id={listboxId}
          className="absolute z-50 mt-1 w-full max-h-72 overflow-y-auto rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] shadow-xl"
        >
          {matches.map((m, i) => {
            const isActive = i === active;
            return (
              <li
                key={m.symbol}
                id={`${listboxId}-opt-${i}`}
                role="option"
                aria-selected={isActive}
                onMouseEnter={() => setActive(i)}
                onMouseDown={(e) => { e.preventDefault(); pick(m.symbol); }}
                className={cn(
                  "px-3 py-2 cursor-pointer flex items-center justify-between gap-3 text-sm",
                  isActive ? "bg-[var(--color-surface-2)]" : "hover:bg-[var(--color-surface-2)]/60",
                )}
              >
                <span className="font-medium text-white tnum">{m.symbol}</span>
                {m.company && (
                  <span className="text-xs muted truncate">{m.company}</span>
                )}
              </li>
            );
          })}
          {catalog.isLoading && (
            <li className="px-3 py-2 text-xs muted">Loading catalog…</li>
          )}
        </ul>
      )}
    </div>
  );
}
