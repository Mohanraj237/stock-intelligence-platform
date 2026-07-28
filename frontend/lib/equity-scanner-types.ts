// Types for the Equity Live Scanner — /api/equity-scanner/scan/stream

export interface ScoreBreakdown {
  trend:      number;  // 0-30
  momentum:   number;  // 0-25
  volume:     number;  // 0-15
  candle:     number;  // 0-25
  structural: number;  // 0-5
}

export interface EquityPlan {
  action:          "BUY" | "SELL";
  entry_price:     number;
  sl_price:        number;
  t1_price:        number;
  t2_price:        number;
  rr:              number;
  exit_rule:       string;
  risk_per_share:  number;
  currency:        string;  // "₹" | "$"
}

export interface BacktestInfo {
  hit_rate:    number | null;
  sample_size: number;
  note?:       string;
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
  patterns?:        Array<{ name: string; family: string; confidence: number; direction: string; tier: number }>;
  breakout_state:   string;   // "FRESH_BREAKOUT" | "CONFIRMED_BREAKOUT" | etc.
  breakout_label:   string;
  breakout_color:   string;
  structural_score: number;
}

export interface EquityScanSummary {
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
  disclaimer:  string;
}

export interface EquityScanParams {
  universe:          string;
  threshold:         number;
  pattern_names?:    string;   // comma-separated specific pattern names, e.g. "Hammer,Bull Flag"
  min_pattern_conf?: number;   // 0.0–1.0
  timeframes?:       string;   // comma-separated subset of "1d,1wk,1mo"; omitted/empty = all
}

export interface ScanProgressState {
  done:        number;
  total:       number;
  currentSym:  string;
  found:       number;
  setupsSoFar: number;
  enriching:   boolean;
}
