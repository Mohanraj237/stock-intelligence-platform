// Types for the F&O Live Scanner — /api/live-scanner/scan

export interface ScoreBreakdown {
  trend:      number;  // 0-30 (normalised — reaches 30 on unanimous votes)
  momentum:   number;  // 0-25
  volume:     number;  // 0-15; 0 and excluded when volume_available is false
  candle:     number;  // 0-25
  structural: number;  // 0-5
}

export interface OptionPlan {
  action: "BUY" | "SELL";
  option_type: "CE" | "PE";
  strike: number;
  expiry: string;
  entry_spot: number;
  entry_premium: number;
  sl_spot: number;
  sl_premium: number;
  t1_spot: number;
  t2_spot: number;
  t1_premium: number;
  t2_premium: number;
  rr: number;
  /** How `rr` was arrived at — it is a fixed design parameter, not a measurement. */
  rr_basis: string;
  exit_rule: string;
  lot_size: number;
  /** true = symbol missing from the contract table; the lot size is a guess. */
  lot_size_estimated: boolean;
  /** Flat ATM delta the premium levels assume (0.5) — they are not exact. */
  delta_assumption: number;
  /** 0–100, or null when it could not be computed from stored IV history. */
  iv_rank: number | null;
  iv_note: string;
  liquidity_ok: boolean;
  raw_risk_pts: number;
}

export interface BacktestInfo {
  hit_rate: number | null;
  sample_size: number;
  /** Timeframe the hit rate was measured on — the card's own, not always daily. */
  timeframe?: string;
  window_bars?: number;
  /** Registry detector actually walked. */
  detector?: string | null;
  /** Why there is no hit rate. Always present when hit_rate is null. */
  reason?: string | null;
  note?: string;
}

export interface DetectedPattern {
  name:        string;
  pattern_id?: string;
  parent_id?:  string;
  family:      string;
  confidence:  number;
  direction:   string;
  tier:        number;
}

/** One entry from GET /patterns — variants nested under their parent. */
export interface PatternOption {
  pattern_id: string;
  name:       string;
  direction:  string;
  tier:       number;
  source:     "registry" | "variant" | "legacy";
  variants:   PatternOption[];
}

export type PatternGroups = Record<string, PatternOption[]>;

/**
 * "filter" — score from the full detector set, then keep only cards containing
 *            a selected pattern. Scores match an unfiltered scan.
 * "shape"  — legacy: the selection lowers the reachable score.
 */
export type PatternMode = "filter" | "shape";

export interface SetupCard {
  symbol:           string;
  timeframe:        string;          // "5m" | "15m" | "1h" | "1d"
  direction:        "bullish" | "bearish" | "range";
  confluence_score: number;          // 0-100
  score_breakdown:  ScoreBreakdown;
  pattern:          string;
  trigger_price:    number;
  atr:              number;
  rel_vol:          number;
  reasons:          string[];
  plan:             OptionPlan | null;
  /** Why there is no plan. Empty when a plan was produced. */
  plan_unavailable_reason?: string;
  backtest:         BacktestInfo | null;
  patterns?:        DetectedPattern[];
  breakout_state:   string;          // "FRESH_BREAKOUT" | "CONFIRMED_BREAKOUT" | etc.
  breakout_label:   string;
  breakout_color:   string;
  structural_score: number;
  /** false for indices — the Volume category is excluded and the rest rescaled. */
  volume_available?: boolean;
  bars_used?:        number;
  lookback_note?:    string;
}

/** Counters explaining what the scan could NOT do. */
export interface ScanDiagnostics {
  scanned:                   number;
  skipped_no_data:           number;
  skipped_insufficient_bars: number;
  errors:                    Array<{ symbol: string; reason: string }>;
  errors_truncated?:         number;
  cache_hit_rate?:           number;
}

export interface ScanSummary extends ScanDiagnostics {
  total_symbols: number;
  unique_setups: number;
  total_setups: number;
  bullish: number;
  bearish: number;
  range: number;
  strong_80plus: number;
  by_timeframe: Record<string, number>;
  daily_setups?: number;
  intraday_setups?: number;
}

export interface ScanResponse {
  setups: SetupCard[];
  summary: ScanSummary;
  universe: string;
  threshold: number;
  timeframes: string[];
  pattern_mode?: PatternMode;
  disclaimer: string;
}

export interface ScanParams {
  universe:       "indices" | "stocks" | "dynamic";
  threshold:      number;
  timeframes?:    string;   // comma-separated subset of the 8 TFs; omitted = all
  pattern_names?: string;   // comma-separated pattern ids; omitted = all patterns
  pattern_mode?:  PatternMode;
}
