import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

// Cached formatter instances — Intl.NumberFormat creation is expensive per-call
const _fmtCache = new Map<string, Intl.NumberFormat>();
function _fmt(locale: string, opts: Intl.NumberFormatOptions): Intl.NumberFormat {
  const key = `${locale}:${JSON.stringify(opts)}`;
  if (!_fmtCache.has(key)) _fmtCache.set(key, new Intl.NumberFormat(locale, opts));
  return _fmtCache.get(key)!;
}

export function formatINR(n: number | null | undefined, opts: { maxFrac?: number } = {}): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  const maxFrac = opts.maxFrac ?? 2;
  return _fmt("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: maxFrac,
    minimumFractionDigits: 0,
  }).format(n);
}

export function formatCurrency(
  n: number | null | undefined,
  region: "IN" | "US",
  opts: { maxFrac?: number } = {},
): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  const maxFrac = opts.maxFrac ?? 2;
  return _fmt(region === "US" ? "en-US" : "en-IN", {
    style: "currency",
    currency: region === "US" ? "USD" : "INR",
    maximumFractionDigits: maxFrac,
    minimumFractionDigits: 0,
  }).format(n);
}

export function formatNum(n: number | null | undefined, opts: { maxFrac?: number; compact?: boolean } = {}): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  const maxFrac = opts.maxFrac ?? 2;
  return _fmt("en-IN", {
    notation: opts.compact ? "compact" : "standard",
    maximumFractionDigits: maxFrac,
  }).format(n);
}

export function formatPct(n: number | null | undefined, opts: { sign?: boolean; maxFrac?: number } = {}): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  const maxFrac = opts.maxFrac ?? 2;
  const sign = opts.sign && n > 0 ? "+" : "";
  return `${sign}${n.toFixed(maxFrac)}%`;
}

export function trendClass(n: number | null | undefined): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "";
  if (n > 0) return "up";
  if (n < 0) return "down";
  return "muted";
}
