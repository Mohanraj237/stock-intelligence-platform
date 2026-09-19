// Types for the Equity Live Scanner — /api/equity-scanner/scan/stream

import type {
  BacktestInfo, DetectedPattern, PatternGroups, PatternMode, PatternOption,
  ScanDiagnostics, ScoreBreakdown,
} from "./scanner-types";

export type {
  BacktestInfo, DetectedPattern, PatternGroups, PatternMode, PatternOption,
  ScanDiagnostics, ScoreBreakdown,
};

export interface EquityPlan {
  action:          "BUY" | "SELL";
  entry_price:     number;
  sl_price:        number;
  t1_price:        number;
  t2_price:        number;
  rr:              number;
  /** How `rr` was arrived at — it is a fixed design parameter, not a measurement. */
  rr_basis:        string;
  exit_rule:       string;
  risk_per_share:  number;
  currency:        string;  // "₹" | "$"
}

export interface EquitySetupCard {
  symbol:           string;
  timeframe:        string;   // "1d" | "1wk" | "1mo"
  direction:        "bullish" | "bearish" | "range";
  confluence_score: number;   // 0-100
  score_breakdown:  ScoreBreakdown;
  pattern:          string;
  trigger_price:    number;
  atr:              number;
  rel_vol:          number;
  reasons:          string[];
  plan:             EquityPlan | null;
  backtest:         BacktestInfo | null;
  patterns?:        DetectedPattern[];
  breakout_state:   string;   // "FRESH_BREAKOUT" | "CONFIRMED_BREAKOUT" | etc.
  breakout_label:   string;
  breakout_color:   string;
  structural_score: number;
  /** false for indices — the Volume category is excluded and the rest rescaled. */
  volume_available?: boolean;
  bars_used?:        number;
  lookback_note?:    string;
}

export interface EquityScanSummary extends ScanDiagnostics {
  total_symbols:   number;
  unique_setups:   number;
  total_setups:    number;
  bullish:         number;
  bearish:         number;
  range:           number;
  strong_80plus:   number;
  by_timeframe:    Record<string, number>;
}

export interface EquityScanResponse {
  setups:      EquitySetupCard[];
  summary:     EquityScanSummary;
  universe:    string;
  currency:    string;
  threshold:   number;
  timeframes:  string[];
  pattern_mode?: PatternMode;
  disclaimer:  string;
}

export interface EquityScanParams {
  universe:          string;
  threshold:         number;
  pattern_names?:    string;   // comma-separated pattern ids, e.g. "hammer,bull_flag"
  pattern_mode?:     PatternMode;
  min_pattern_conf?: number;   // 0.0–1.0
  timeframes?:       string;   // comma-separated subset of "1d,1wk,1mo"; omitted = all
}

export interface ScanProgressState {
  done:        number;
  total:       number;
  currentSym:  string;
  found:       number;
  setupsSoFar: number;
  enriching:   boolean;
  /** Echoed by the SSE `start` event — what the backend actually resolved. */
  resolved?: {
    universe:     string;
    timeframes:   string[];
    threshold:    number;
    pattern_mode: PatternMode;
  };
}
