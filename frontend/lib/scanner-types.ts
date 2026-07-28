// Types for the F&O Live Scanner — /api/live-scanner/scan

export interface ScoreBreakdown {
  trend:      number;  // 0-30
  momentum:   number;  // 0-25
  volume:     number;  // 0-15
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
  exit_rule: string;
  lot_size: number;
  iv_note: string;
  liquidity_ok: boolean;
  raw_risk_pts: number;
}

export interface BacktestInfo {
  hit_rate: number | null;
  sample_size: number;
  note?: string;
}

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
  backtest:         BacktestInfo | null;
  patterns?:        Array<{ name: string; family: string; confidence: number; direction: string; tier: number }>;
  breakout_state:   string;          // "FRESH_BREAKOUT" | "CONFIRMED_BREAKOUT" | etc.
  breakout_label:   string;
  breakout_color:   string;
  structural_score: number;
}

export interface ScanSummary {
  total_symbols: number;
  unique_setups: number;
  total_setups: number;
  bullish: number;
  bearish: number;
  range: number;
  strong_80plus: number;
  by_timeframe: Record<string, number>;
}

export interface ScanResponse {
  setups: SetupCard[];
  summary: ScanSummary;
  universe: string;
  threshold: number;
  timeframes: string[];
  disclaimer: string;
}

export interface ScanParams {
  universe:       "indices" | "stocks";
  threshold:      number;
  timeframes?:    string;   // comma-separated subset of the 8 TFs; omitted/empty = all
  pattern_names?: string;   // comma-separated exact pattern names; omitted/empty = all patterns
}
