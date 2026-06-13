/**
 * Pure utility functions for F&O calculations.
 * No React imports — safe to import in Vitest without jsdom.
 */

/** Sentiment interpretation of a PCR value per spec §6. */
export type PcrSentimentResult = {
  label: string;
  variant: "success" | "warning" | "danger" | "default";
};

/**
 * Map a PCR OI value to a human-readable sentiment label and badge variant.
 * Thresholds from PRODUCT_ANALYSIS_FNO.md §6.
 */
export function getPcrSentiment(pcr: number): PcrSentimentResult {
  if (pcr > 1.3)  return { label: "Strongly Bullish", variant: "success" };
  if (pcr >= 1.0) return { label: "Mildly Bullish",   variant: "success" };
  if (pcr >= 0.7) return { label: "Neutral",          variant: "default" };
  if (pcr >= 0.5) return { label: "Mildly Bearish",   variant: "warning" };
  return           { label: "Strongly Bearish",        variant: "danger"  };
}

/**
 * Merge separate PCR and VIX history arrays (both keyed by date) into a single
 * array for Recharts, sorted oldest → newest.
 */
export interface PcrHistoryEntry {
  date: string;
  nifty_pcr: number;
  banknifty_pcr: number;
}

export interface VixHistoryEntry {
  date: string;
  vix: number;
}

export interface MergedHistoryPoint {
  date: string;
  nifty_pcr: number | null;
  banknifty_pcr: number | null;
  vix: number | null;
}

export function mergeHistory(
  pcrHistory: PcrHistoryEntry[],
  vixHistory: VixHistoryEntry[],
): MergedHistoryPoint[] {
  const vixByDate = new Map(vixHistory.map((v) => [v.date, v.vix]));
  const allDates = Array.from(
    new Set([
      ...pcrHistory.map((p) => p.date),
      ...vixHistory.map((v) => v.date),
    ]),
  ).sort(); // ISO dates sort lexicographically = chronologically

  const pcrByDate = new Map(pcrHistory.map((p) => [p.date, p]));

  return allDates.map((date) => {
    const pcr = pcrByDate.get(date);
    return {
      date,
      nifty_pcr:     pcr?.nifty_pcr    ?? null,
      banknifty_pcr: pcr?.banknifty_pcr ?? null,
      vix:           vixByDate.get(date) ?? null,
    };
  });
}
