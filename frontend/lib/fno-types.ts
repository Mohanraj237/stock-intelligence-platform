/**
 * F&O TypeScript types — mirrors the Python fno_data_service / greeks_calculator data shapes.
 * All monetary values in ₹.
 */

// ── Option chain ──────────────────────────────────────────────────────────────

export interface OptionSide {
  oi: number;
  oi_chg: number;
  oi_chg_pct: number;
  vol: number;
  iv: number;         // percentage, e.g. 15.5
  ltp: number;
  chg: number;
  chg_pct: number;
  bid_qty: number;
  bid: number;
  ask_qty: number;
  ask: number;
  // Computed Greeks (added client-side via greeks.ts)
  delta?: number;
  gamma?: number;
  theta?: number;
  vega?: number;
}

export interface OptionChainRow {
  strike: number;
  expiry: string;
  CE: Partial<OptionSide>;
  PE: Partial<OptionSide>;
}

export interface OptionChainMeta {
  expiry_dates: string[];
  strike_prices: number[];
  underlying: number;       // spot price
  timestamp: string;
  total_ce_oi: number;
  total_pe_oi: number;
  total_ce_vol: number;
  total_pe_vol: number;
  synthetic?: boolean;      // true = Black-Scholes theoretical prices (real NSE chain unavailable)
  cached?: boolean;         // true = last session closing data (NSE chain unavailable right now)
  vix?: number;             // India VIX used for synthetic pricing
}

export interface OptionChainResponse {
  rows: OptionChainRow[];
  meta: OptionChainMeta;
}

// ── Index Futures ─────────────────────────────────────────────────────────────

export interface IndexFuture {
  symbol: string;
  index_name: string;
  spot: number;
  futures_ltp: number;
  basis: number;
  basis_pct: number;
  change: number;
  change_pct: number;
  oi: number;
  vol: number;
  expiry: string;
  synthetic?: boolean;
  cached?: boolean;
}

// ── OI Analytics ─────────────────────────────────────────────────────────────

export interface OISpurtRow {
  symbol: string;
  oi_current: number;
  oi_prev: number;
  oi_change: number;
  oi_change_pct: number;
  ltp: number;
  price_chg_pct: number;
}

export type BuildupType = "Long Buildup" | "Short Buildup" | "Long Unwinding" | "Short Covering" | "Neutral";

export interface OIBuildupRow extends OISpurtRow {
  classification: BuildupType;
}

// ── VIX ───────────────────────────────────────────────────────────────────────

export interface VixData {
  vix: number | null;
  change: number | null;
  change_pct: number | null;
  open: number | null;
  high: number | null;
  low: number | null;
  prev_close: number | null;
}

// ── PCR ───────────────────────────────────────────────────────────────────────

export interface PcrData {
  symbol: string;
  pcr_oi: number;
  pcr_vol: number;
  total_ce_oi: number;
  total_pe_oi: number;
  total_ce_vol: number;
  total_pe_vol: number;
}

export type SentimentLabel =
  | "Extremely Bullish" | "Bullish" | "Neutral" | "Bearish" | "Extremely Bearish";

// ── Greeks ────────────────────────────────────────────────────────────────────

export interface GreeksResult {
  delta: number;
  gamma: number;
  theta: number;     // per calendar day
  vega: number;      // per 1% IV move
  rho: number;
  d1: number;
  d2: number;
  bs_price: number;
  intrinsic: number;
  time_value: number;
}

// ── Strategy Builder ──────────────────────────────────────────────────────────

export type OptionType = "CE" | "PE" | "FUT";
export type LegAction = "BUY" | "SELL";

export interface StrategyLeg {
  symbol: string;
  expiry: string;
  strike: number;
  option_type: OptionType;
  action: LegAction;
  lots: number;
  lot_size: number;
  ltp: number;
  iv?: number;        // annualised, 0–1
  dte?: number;
}

export interface StrategyResult {
  max_profit: number;
  max_loss: number;
  net_premium: number;
  is_debit: boolean;
  unlimited_profit: boolean;
  unlimited_loss: boolean;
  breakevens: number[];
  net_delta: number;
  net_gamma: number;
  net_theta: number;
  net_vega: number;
  margin_estimate: number;
  payoff_prices: number[];
  payoff_pnl: number[];
}

export interface SavedStrategy {
  name: string;
  legs: StrategyLeg[];
  saved_at: string;
}

// ── Lot sizes ─────────────────────────────────────────────────────────────────

export const LOT_SIZES: Record<string, number> = {
  NIFTY: 75, BANKNIFTY: 15, FINNIFTY: 40, MIDCPNIFTY: 75,
  SENSEX: 10, BANKEX: 15,
  RELIANCE: 250, TCS: 150, INFY: 400, HDFCBANK: 550, ICICIBANK: 700,
  AXISBANK: 1200, KOTAKBANK: 400, SBIN: 1500, BAJFINANCE: 125, BAJAJFINSV: 500,
  WIPRO: 1500, LT: 175, MARUTI: 100, TATAMOTORS: 1425, TATASTEEL: 5500,
  SUNPHARMA: 700, DRREDDY: 125, CIPLA: 650, DIVISLAB: 200, HCLTECH: 700,
  TECHM: 600, NTPC: 2250, POWERGRID: 2700, ONGC: 1975, BPCL: 1800,
  COALINDIA: 2100, NESTLEIND: 50, ASIANPAINT: 200, HINDUNILVR: 300,
  TITAN: 375, ULTRACEMCO: 100, GRASIM: 375, HEROMOTOCO: 150, EICHERMOT: 175,
  APOLLOHOSP: 250, ADANIENT: 625, ADANIPORTS: 625, JSWSTEEL: 600,
  "M&M": 700, BHARTIARTL: 950, INDUSINDBK: 500, HINDPETRO: 1000,
  IOC: 5250, VEDL: 2000, SAIL: 6700, PNB: 8000, BANKBARODA: 3350,
  CANBK: 3250, IDFCFIRSTB: 5500, FEDERALBNK: 5000, ZOMATO: 4500,
  HAL: 150, BEL: 3700, BHEL: 4350, HDFCLIFE: 1100, SBILIFE: 750, ITC: 3200,
  IRCTC: 1375, LICI: 700, DMART: 450, TATACONSUM: 1100, BRITANNIA: 200,
  UPL: 1300, "BAJAJ-AUTO": 250,
  // Additional live-scanner equities
  RBLBANK: 3175, AUBANK: 1000, ABCAPITAL: 6000, MFSL: 4000,
  PERSISTENT: 125, "360ONE": 1000, POLICYBZR: 2000, NAUKRI: 200,
  PIIND: 500, DEEPAKNTR: 500, AARTIIND: 1500, ASTRAL: 700,
  TATAPOWER: 4000, NHPC: 8000, RECLTD: 2250, PFC: 2700,
  RVNL: 3000, IRFC: 6000, APLAPOLLO: 500,
};

export const INDEX_SYMBOLS = ["NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "SENSEX", "BANKEX"];

// ── Paper Trading ─────────────────────────────────────────────────────────────

export type TradeStatus = "OPEN" | "CLOSED" | "CANCELLED";
export type TradeSource = "MANUAL" | "AI";

/** How the current_price was last set. */
export type PriceSource = "live" | "cached" | "manual" | "none";

export interface PaperTrade {
  trade_id: string;
  symbol: string;
  instrument_type: "CE" | "PE" | "FUT";
  strike: number;
  expiry: string;
  action: "BUY" | "SELL";
  lots: number;
  lot_size: number;
  entry_price: number;
  current_price: number;
  target_price: number;
  stop_loss: number;
  entry_time: string;
  exit_time: string | null;
  exit_price: number | null;
  exit_reason: string | null;
  status: TradeStatus;
  pnl_rs: number;
  pnl_pct: number;
  margin_used: number;
  source: TradeSource;
  ai_confidence: string;
  strategy_name: string;
  /** How current_price was last obtained. Absent on trades added before this field existed. */
  price_source?: PriceSource;
}

export interface PortfolioSummary {
  initial_capital: number;
  available_capital: number;
  deployed_capital: number;
  total_equity: number;
  open_pnl: number;
  closed_pnl: number;
  total_pnl: number;
  total_pnl_pct: number;
  open_trades_count: number;
  closed_trades_count: number;
  win_rate: number;
  profit_factor: number;
}

// ── F&O History ───────────────────────────────────────────────────────────────

export interface FnoHistoryPcrEntry {
  date: string;
  nifty_pcr: number;
  banknifty_pcr: number;
}

export interface FnoHistoryVixEntry {
  date: string;
  vix: number;
}

export interface FnoHistory {
  pcr: FnoHistoryPcrEntry[];
  vix: FnoHistoryVixEntry[];
}

/** Returned by POST /api/fno/paper-trades/refresh-prices — one entry per open trade. */
export interface PriceRefreshResult {
  trade_id: string;
  symbol: string;
  /** null when no real market price could be obtained. */
  current_price: number | null;
  /** null when no real market price could be obtained. */
  pnl_rs: number | null;
  price_source: PriceSource;
  sl_hit: boolean;
  tp_hit: boolean;
  /** Present when price_source is "none" — human-readable explanation. */
  error?: string;
}

export function getLotSize(symbol: string): number {
  return LOT_SIZES[symbol.toUpperCase()] ?? 1;
}

export function parseExpiryDate(expiry: string): Date | null {
  // "27-Mar-2025" format
  const d = new Date(expiry.replace(/-/g, " "));
  return isNaN(d.getTime()) ? null : d;
}

export function daysToExpiry(expiry: string): number {
  const d = parseExpiryDate(expiry);
  if (!d) return 0;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return Math.max(0, Math.floor((d.getTime() - today.getTime()) / 86_400_000));
}

export function findAtmStrike(strikes: number[], spot: number): number {
  if (!strikes.length || spot <= 0) return 0;
  return strikes.reduce((prev, curr) =>
    Math.abs(curr - spot) < Math.abs(prev - spot) ? curr : prev
  );
}
