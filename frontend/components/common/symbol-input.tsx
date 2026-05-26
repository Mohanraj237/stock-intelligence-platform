"use client";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { SymbolAutocomplete } from "./symbol-autocomplete";

/**
 * Search-style symbol picker with a Load button. Used in tab headers where the
 * caller wants explicit "submit" semantics (e.g. Stock Analyzer, News, Earnings).
 * Internally uses SymbolAutocomplete so users get typeahead suggestions.
 */
export function SymbolInput({
  initial = "RELIANCE", onSubmit, placeholder = "Symbol or company",
}: {
  initial?: string;
  onSubmit: (sym: string) => void;
  placeholder?: string;
}) {
  const [v, setV] = useState(initial);
  return (
    <form
      onSubmit={(e) => { e.preventDefault(); onSubmit(v.trim().toUpperCase()); }}
      className="flex items-center gap-2"
    >
      <SymbolAutocomplete
        value={v}
        onChange={setV}
        onSelect={(sym) => onSubmit(sym)}
        placeholder={placeholder}
        className="w-64"
      />
      <Button type="submit" size="sm">Load</Button>
    </form>
  );
}
