/**
 * Typed API client. Routes go through Next.js rewrite (/api/* -> 127.0.0.1:8000/api/*),
 * so we can call relative URLs from both server and client components.
 */
import type {
  MarketStatus, IndexPerf, SectorPerf, FIIDIIRow, UniverseRow,
  OHLCVResponse, Indicators, Fundamentals, AIVerdict, ChartAnalysis,
  QuarterlyRow,
  PatternHit, MultiTFBreakout, PatternScanRequest, PatternScanResult,
  ScanRequest, ScanResult,
  NewsItem, AnnouncementItem,
  UpcomingResult, EarningsItem,
  PortfolioSummary, WatchlistRow, AppSettings, ScoringConfig,
  Rule, RuleSet, RuleMatchRow,
  Timeframe,
} from "@/lib/types";

// Always hit FastAPI directly — bypasses Next.js dev-server rewrite proxy,
// which has a hardcoded ~60s upstream timeout that breaks long-running scans.
// CORS is configured on the backend for http://localhost:3001.
const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ||
  process.env.API_URL ||
  "http://127.0.0.1:8000";

function url(path: string): string {
  return `${API_BASE}${path}`;
}

async function get<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url(path), { cache: "no-store", ...init });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`GET ${path} → ${res.status}${text ? `: ${text.slice(0, 200)}` : ""}`);
  }
  return res.json() as Promise<T>;
}

async function post<T>(path: string, body: unknown, init?: RequestInit): Promise<T> {
  const res = await fetch(url(path), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
    ...init,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`POST ${path} → ${res.status}${text ? `: ${text.slice(0, 200)}` : ""}`);
  }
  return res.json() as Promise<T>;
}

async function del<T>(path: string): Promise<T> {
  const res = await fetch(url(path), { method: "DELETE" });
  if (!res.ok) throw new Error(`DELETE ${path} → ${res.status}`);
  return res.json() as Promise<T>;
}

async function patch<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(url(path), {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`PATCH ${path} → ${res.status}`);
  return res.json() as Promise<T>;
}

export type Region = "IN" | "US";

function r(region: Region) {
  return `region=${region}`;
}
function q(region: Region, extra?: string) {
  return `?${r(region)}${extra ? `&${extra}` : ""}`;
}

// ── Domain helpers ──────────────────────────────────────────
export const api = {
  health:           () => get<{ status: string; version: string }>("/api/health"),

  // Market
  marketStatus:     (region: Region = "IN") => get<MarketStatus>(`/api/market/status${q(region)}`),
  indices:          (region: Region = "IN") => get<IndexPerf[]>(`/api/market/indices${q(region)}`),
  sectors:          (region: Region = "IN") => get<SectorPerf[]>(`/api/market/sectors${q(region)}`),
  fiiDii:           () => get<FIIDIIRow[]>("/api/market/fii-dii"),
  universeQuotes:   (name: string, region: Region = "IN") => get<UniverseRow[]>(`/api/market/universe/${encodeURIComponent(name)}/quotes${q(region)}`),

  // Universe
  listUniverses:    (region: Region = "IN") => get<Record<string, string>>(`/api/universe/list${q(region)}`),
  universeSymbols:  (name: string, region: Region = "IN", limit?: number) =>
    get<string[]>(`/api/universe/${encodeURIComponent(name)}/symbols${q(region, limit ? `limit=${limit}` : undefined)}`),
  syncUniverse:     (name: string, region: Region = "IN") => post<unknown>(`/api/universe/${encodeURIComponent(name)}/sync${q(region)}`, {}),

  // Stocks
  ohlcv:            (symbol: string, tf: Timeframe = "1D", region: Region = "IN", period?: string) =>
    get<OHLCVResponse>(`/api/stocks/${encodeURIComponent(symbol)}/ohlcv${q(region, `timeframe=${tf}${period ? `&period=${period}` : ""}`)}`),
  indicators:       (symbol: string, tf: Timeframe = "1D", region: Region = "IN") =>
    get<Indicators>(`/api/stocks/${encodeURIComponent(symbol)}/indicators${q(region, `timeframe=${tf}`)}`),
  fundamentals:     (symbol: string, region: Region = "IN") => get<Fundamentals>(`/api/stocks/${encodeURIComponent(symbol)}/fundamentals${q(region)}`),
  quarterly:        (symbol: string, region: Region = "IN", n = 8) => get<QuarterlyRow[]>(`/api/stocks/${encodeURIComponent(symbol)}/quarterly${q(region, `n=${n}`)}`),
  balanceSheet:     (symbol: string, region: Region = "IN") => get<{ symbol: string; rows: Record<string, number | string | null>[] }>(`/api/stocks/${encodeURIComponent(symbol)}/balance-sheet${q(region)}`),
  cashFlow:         (symbol: string, region: Region = "IN") => get<{ symbol: string; rows: Record<string, number | string | null>[] }>(`/api/stocks/${encodeURIComponent(symbol)}/cash-flow${q(region)}`),
  ratiosHistory:    (symbol: string, region: Region = "IN") => get<{ symbol: string; rows: Record<string, number | string | null>[] }>(`/api/stocks/${encodeURIComponent(symbol)}/ratios-history${q(region)}`),
  shareholding:     (symbol: string, region: Region = "IN") => get<{ symbol: string; latest: Record<string, number | null>; history: Record<string, number | string | null>[] }>(`/api/stocks/${encodeURIComponent(symbol)}/shareholding${q(region)}`),
  peers:            (symbol: string, region: Region = "IN") => get<{
    symbol: string;
    sector: string | null;
    industry: string | null;
    source: string;
    peers: Record<string, string | number | null>[];
  }>(`/api/stocks/${encodeURIComponent(symbol)}/peers${q(region)}`),
  verdict:          (symbol: string, tf: Timeframe = "1D", region: Region = "IN") => get<AIVerdict>(`/api/stocks/${encodeURIComponent(symbol)}/verdict${q(region, `timeframe=${tf}`)}`),
  chartAnalysis:    (symbol: string, tf: Timeframe = "1D", region: Region = "IN") => get<ChartAnalysis>(`/api/stocks/${encodeURIComponent(symbol)}/chart-analysis${q(region, `timeframe=${tf}`)}`),
  snapshot:         (symbol: string, tf: Timeframe = "1D", region: Region = "IN") => get<unknown>(`/api/stocks/${encodeURIComponent(symbol)}/snapshot${q(region, `timeframe=${tf}`)}`),

  // Patterns
  patternLibrary:   () => get<{ name: string; category: string; direction: string; description: string; best_timeframes: string }[]>("/api/patterns/library"),
  patternExample:   (name: string) => get<{ name: string; bars: { time: number; open: number; high: number; low: number; close: number; volume: number }[] }>(`/api/patterns/library/${encodeURIComponent(name)}/example`),
  detectPatterns:   (symbol: string, tf: Timeframe = "1D", region: Region = "IN") => get<PatternHit[]>(`/api/patterns/detect/${encodeURIComponent(symbol)}${q(region, `timeframe=${tf}`)}`),
  multiTFBreakout:  (symbol: string, region: Region = "IN") => get<MultiTFBreakout>(`/api/patterns/multi-tf-breakout/${encodeURIComponent(symbol)}${q(region)}`),
  patternScan:      (req: PatternScanRequest) => post<PatternScanResult>("/api/patterns/scan", req),

  // Scans
  scanTypes:        (region: Region = "IN") => get<{ id: string; name: string; desc: string }[]>(`/api/scans/types${q(region)}`),
  runScan:          (req: ScanRequest) => post<ScanResult>("/api/scans/run", req),

  // News + earnings
  marketNews:       (region: Region = "IN", limit = 60) => get<NewsItem[]>(`/api/news/market${q(region, `limit=${limit}`)}`),
  stockNews:        (symbol: string, region: Region = "IN", limit = 20) => get<NewsItem[]>(`/api/news/stock/${encodeURIComponent(symbol)}${q(region, `limit=${limit}`)}`),
  announcements:    (symbol?: string) => get<AnnouncementItem[]>(`/api/news/announcements${symbol ? `?symbol=${encodeURIComponent(symbol)}` : ""}`),
  upcomingEarnings: (region: Region = "IN", days = 14) => get<UpcomingResult[]>(`/api/earnings/upcoming${q(region, `days_ahead=${days}`)}`),
  recentEarnings:   (symbol: string, region: Region = "IN", n = 4) => get<EarningsItem[]>(`/api/earnings/recent/${encodeURIComponent(symbol)}${q(region, `n=${n}`)}`),

  // Portfolio + watchlist
  portfolio:        () => get<PortfolioSummary>("/api/portfolio"),
  addHolding:       (h: { symbol: string; qty: number; buy_price: number; buy_date?: string }) => post<unknown>("/api/portfolio/add", h),
  removeHolding:    (symbol: string) => del<unknown>(`/api/portfolio/${encodeURIComponent(symbol)}`),
  watchlist:        () => get<WatchlistRow[]>("/api/watchlist"),
  addToWatchlist:   (symbol: string, note?: string) => post<unknown>("/api/watchlist/add", { symbol, note }),
  removeFromWatchlist: (symbol: string) => del<unknown>(`/api/watchlist/${encodeURIComponent(symbol)}`),

  // Rules
  listRules:        () => get<Rule[]>("/api/rules"),
  createRule:       (rule: Rule) => post<Rule>("/api/rules", rule),
  deleteRule:       (id: string) => del<unknown>(`/api/rules/${encodeURIComponent(id)}`),
  applyRules:       (req: { universe: string; ruleset: RuleSet; max_symbols?: number | null; region?: Region }) =>
    post<RuleMatchRow[]>("/api/rules/apply", req),

  // Backtests
  runBacktest:      (req: {
    universe: string; pattern_name: string; period: string;
    max_symbols: number; min_confidence: number;
    max_holding_bars: number; step_size: number; rolling_window: number;
  }) => post<{
    request: typeof req;
    win_rate: number; avg_return: number; expectancy: number;
    profit_factor: number; max_drawdown: number; avg_holding_days: number;
    avg_winner: number; avg_loser: number; best_winner: number; worst_loser: number;
    total_trades: number;
    equity_curve: number[];
    return_distribution: number[];
    trades: { symbol: string; entry_date: string; exit_date: string; entry_price: number; exit_price: number; return_pct: number; bars_held: number; exit_reason: string }[];
    verdict: string;
    audit_log: string[];
    duration_ms: number;
  }>("/api/backtests/run", req),

  // Settings + reports
  settings:         () => get<AppSettings>("/api/settings"),
  patchSettings:    (s: Partial<AppSettings>) => patch<AppSettings>("/api/settings", s),
  generateReport:   (symbol: string, timeframe: Timeframe = "1D", region: Region = "IN") => post<{ filename: string; path: string }>("/api/reports/generate", { symbol, timeframe, region }),
  listReports:      () => get<{ filename: string; size: number; mtime: number }[]>("/api/reports/list"),

  // Confluence scoring config
  scoringConfig:      () => get<ScoringConfig>("/api/scoring-config"),
  patchScoringConfig: (c: Partial<ScoringConfig>) => patch<ScoringConfig>("/api/scoring-config", c),
  resetScoringConfig: () => post<ScoringConfig>("/api/scoring-config/reset", {}),
};

export type ApiClient = typeof api;
