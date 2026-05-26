/**
 * TypeScript types mirroring backend/schemas/*.py.
 * Keep in lockstep with Pydantic models. (Future: auto-generate from OpenAPI.)
 */

export type Timeframe = "1D" | "1W" | "1M";
export const TIMEFRAMES: Timeframe[] = ["1D", "1W", "1M"];
export const TIMEFRAME_LABEL: Record<Timeframe, string> = { "1D": "Daily", "1W": "Weekly", "1M": "Monthly" };

export type Direction = "Bullish" | "Bearish" | "Neutral";
export type Verdict = "STRONG_BUY" | "BUY" | "NEUTRAL" | "HOLD" | "SELL" | "STRONG_SELL";
export type BreakoutState =
  | "VERGE_BREAKOUT" | "FRESH_BREAKOUT" | "CONFIRMED_BREAKOUT" | "EXTENDED" | "NO_BREAKOUT"
  | "VERGE_BREAKDOWN" | "FRESH_BREAKDOWN" | "CONFIRMED_BREAKDOWN";
export type Sentiment = "POSITIVE" | "MILDLY_POSITIVE" | "NEUTRAL" | "MILDLY_NEGATIVE" | "NEGATIVE";

// ── Market ─────────────────────────────────────────
export interface MarketStatus {
  status: string;
  is_open: boolean;
  trade_date?: string | null;
  nifty?: number | null;
  nifty_change_pct?: number | null;
  market_cap_lakh_cr?: number | null;
  gift_nifty?: number | null;
  gift_nifty_change_pct?: number | null;
}

export interface IndexPerf {
  symbol: string;
  name: string;
  last_price: number;
  change: number;
  change_pct: number;
  open?: number | null;
  high?: number | null;
  low?: number | null;
  prev_close?: number | null;
}

export interface SectorPerf {
  name: string;
  symbol: string;
  last_price?: number | null;
  change_pct: number;
  advances: number;
  declines: number;
  unchanged: number;
}

export interface FIIDIIRow {
  date: string;
  fii_buy: number; fii_sell: number; fii_net: number;
  dii_buy: number; dii_sell: number; dii_net: number;
}

export interface UniverseRow {
  symbol: string;
  company?: string | null;
  last_price?: number | null;
  change_pct?: number | null;
  open?: number | null;
  high?: number | null;
  low?: number | null;
  prev_close?: number | null;
  week52_high?: number | null;
  week52_low?: number | null;
  volume?: number | null;
  return_30d?: number | null;
  return_1y?: number | null;
  rsi?: number | null;
  adx?: number | null;
  signal?: string | null;
  score?: number | null;
}

export interface OHLCVBar {
  time: number;
  open: number; high: number; low: number; close: number;
  volume?: number | null;
}

export interface OHLCVResponse {
  symbol: string;
  timeframe: Timeframe;
  bars: OHLCVBar[];
  source: string;
}

// ── Stock ──────────────────────────────────────────
export interface Indicators {
  close?: number; open?: number; high?: number; low?: number;
  rsi?: number; ao?: number;
  ema20?: number; ema50?: number; ema100?: number; ema200?: number;
  sma20?: number; sma50?: number; sma100?: number; sma200?: number;
  bb_upper?: number; bb_lower?: number; bb_middle?: number;
  macd?: number; macd_signal?: number; macd_hist?: number;
  adx?: number; plus_di?: number; minus_di?: number;
  stoch_k?: number; stoch_d?: number;
  cci20?: number; atr?: number; change_pct?: number;
}

export interface Fundamentals {
  name?: string | null; sector?: string | null; industry?: string | null;
  market_cap?: number | null; pe?: number | null; pb?: number | null;
  book_value?: number | null; dividend_yield?: number | null; eps?: number | null;
  roe?: number | null; roce?: number | null; opm?: number | null; npm?: number | null;
  sales_growth?: number | null; profit_growth?: number | null;
  debt_to_equity?: number | null; interest_coverage?: number | null;
  promoter_holding?: number | null; fii_holding?: number | null; dii_holding?: number | null;
  public_holding?: number | null; pledge_pct?: number | null;
  about?: string | null; pros: string[]; cons: string[]; insights: string[];
  peers: Record<string, unknown>[];
  error?: string | null;
}

export interface AIVerdict {
  symbol: string;
  verdict: Verdict;
  composite_score: number;
  tech_score: number;
  fund_score: number;
  pattern_score: number;
  momentum_score: number;
  confidence: string;
  price_target?: number | null;
  stop_loss?: number | null;
  bull_case: string[];
  bear_case: string[];
  risk_flags: string[];
  signal_chain: string[];
}

export interface QuarterlyRow {
  period: string;
  sales?: number | null; net_profit?: number | null;
  opm_pct?: number | null; sales_yoy_pct?: number | null; profit_yoy_pct?: number | null;
}

export interface ChartAnalysis {
  symbol: string;
  timeframe: Timeframe;
  sections: Record<string, unknown>;
  probability_scores: Record<string, number>;
  final_verdict: string;
  confidence: string;
  pro_explanation: string;
  entry?: number | null;
  stop_loss?: number | null;
  targets: number[];
  red_flags: string[];
}

// ── Pattern ────────────────────────────────────────
export interface PatternHit {
  name: string;
  category: string;
  direction: Direction;
  confidence: number;
  status?: string | null;
  description?: string | null;
  target?: number | null; stop?: number | null;
  support?: number | null; resistance?: number | null;
  points: { x: number; y: number }[];
  lines: Record<string, unknown>[];
  zones: Record<string, unknown>[];
  timeframe?: Timeframe | null;
}

export interface BreakoutClassification {
  state: BreakoutState;
  label: string;
  color: string;
  level?: number | null;
  current_price?: number | null;
  distance_pct?: number | null;
  bars_since_breakout: number;
  volume_confirmed: boolean;
  is_bullish: boolean;
  is_bearish: boolean;
  timeframe?: Timeframe | null;
}

export interface MultiTFBreakout {
  symbol: string;
  by_timeframe: Record<string, BreakoutClassification>;
  overall: string;
}

export interface PatternScanRequest {
  universe: string;
  pattern_names: string[];
  direction?: Direction | null;
  timeframes: Timeframe[];
  min_confidence: number;
  breakout_states: BreakoutState[];
  max_symbols?: number | null;
}

export interface PatternStockResult {
  symbol: string;
  company?: string | null;
  last_price?: number | null;
  confluence_score: number;
  patterns: PatternHit[];
  breakouts: Record<string, BreakoutClassification>;
  timeframes_present: Timeframe[];
}

export interface PatternScanResult {
  request: PatternScanRequest;
  rows: PatternStockResult[];
  total_scanned: number;
  total_matched: number;
  duration_ms: number;
}

// ── Scan ───────────────────────────────────────────
export interface FilterCriteria {
  pe_max?: number | null; pb_max?: number | null; de_max?: number | null;
  roe_min?: number | null; roce_min?: number | null;
  sales_growth_min?: number | null; profit_growth_min?: number | null;
  promoter_min?: number | null;
  rsi_min?: number | null; rsi_max?: number | null; adx_min?: number | null;
  price_above_sma50?: boolean | null; price_above_sma200?: boolean | null;
  macd_bullish?: boolean | null;
  change_pct_min?: number | null; change_pct_max?: number | null;
}

export interface ScanRequest {
  universe: string;
  scan_type: string;
  filters: FilterCriteria;
  enable_ai: boolean;
  max_symbols?: number | null;
}

export interface ScanRow {
  symbol: string; company?: string | null;
  last_price?: number | null; change_pct?: number | null;
  rsi?: number | null; adx?: number | null;
  macd_bullish?: boolean | null;
  sma50?: number | null; sma200?: number | null;
  volume?: number | null;
  pe?: number | null; pb?: number | null; roe?: number | null;
  signal?: string | null;
  ai_score?: number | null; ai_verdict?: string | null;
  rules_passed: string[];
}

export interface ScanResult {
  request: ScanRequest;
  rows: ScanRow[];
  audit_log: Record<string, unknown>[];
  total_scanned: number; total_matched: number;
  duration_ms: number;
}

// ── News ───────────────────────────────────────────
export interface NewsItem {
  title: string; summary?: string | null; url?: string | null;
  published?: string | null; source: string; sentiment: Sentiment;
}

export interface AnnouncementItem {
  symbol: string; subject: string; desc?: string | null;
  date?: string | null; attachment_url?: string | null;
  sentiment: Sentiment;
}

// ── Earnings ───────────────────────────────────────
export interface UpcomingResult {
  symbol: string; company?: string | null;
  meeting_date: string; purpose?: string | null; agenda?: string | null;
}

export interface EarningsItem {
  symbol: string; period: string;
  sales?: number | null; net_profit?: number | null;
  opm_pct?: number | null;
  sales_yoy_pct?: number | null; profit_yoy_pct?: number | null;
  sentiment: Sentiment;
}

// ── Position ───────────────────────────────────────
export interface PositionSize {
  qty: number; deployed: number; at_risk: number;
  rr?: number | null; risk_pct: number; capital: number;
  entry: number; stop: number; target?: number | null;
  notes: string[];
}

// ── Portfolio ──────────────────────────────────────
export interface PortfolioRow {
  symbol: string; company?: string | null;
  qty: number; buy_price: number; buy_date?: string | null;
  cmp?: number | null; today_change_pct?: number | null;
  invested: number; current_value?: number | null;
  pnl?: number | null; pnl_pct?: number | null;
  signal?: string | null;
}

export interface PortfolioSummary {
  rows: PortfolioRow[];
  total_invested: number; current_value: number;
  total_pnl: number; total_pnl_pct: number;
  holdings_count: number;
}

// ── Watchlist ──────────────────────────────────────
export interface WatchlistRow {
  symbol: string; company?: string | null;
  last_price?: number | null; change_pct?: number | null;
  rsi?: number | null; macd_hist?: number | null;
  sma50?: number | null; sma200?: number | null;
  volume?: number | null; signal?: string | null; score?: number | null;
  added_at?: string | null;
}

// ── Rules ──────────────────────────────────────────
export type RuleOp = ">" | ">=" | "<" | "<=" | "==" | "between";
export type RuleLogic = "AND" | "OR";

export interface RuleCondition {
  field: string;
  op: RuleOp;
  value: number | string;
  value2?: number | string | null;
}

export interface Rule {
  id?: string;
  name: string;
  description?: string | null;
  conditions: RuleCondition[];
  logic: RuleLogic;
}

export interface RuleSet {
  rules: Rule[];
  cross_logic: RuleLogic;
}

export interface RuleMatchRow {
  symbol: string;
  company?: string | null;
  last_price?: number | null;
  change_pct?: number | null;
  rules_passed: string[];
  rules_failed: string[];
  pass_count: number;
}

// ── Settings ───────────────────────────────────────
export interface AppSettings {
  refresh_interval_sec: number;
  default_universe: string;
  max_parallel_workers: number;
  screener_csrf?: string | null;
  screener_session?: string | null;
  screener_cache_ttl_hours: number;
  market_cache_ttl_min: number;
  universe_cache_ttl_hours: number;
}
