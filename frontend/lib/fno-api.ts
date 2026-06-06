/**
 * Typed F&O API client — calls FastAPI /api/fno/* endpoints.
 * FastAPI uses Python requests.Session() which handles NSE cookies correctly.
 */

import type {
  OptionChainResponse,
  OptionChainRow,
  IndexFuture,
  OISpurtRow,
  OIBuildupRow,
  VixData,
  PcrData,
  GreeksRow,
  FoScanRow,
  FoScanType,
  SavedStrategy,
  StrategyLeg,
  FNOSuggestion,
  PaperTrade,
  PortfolioSummary,
} from "@/lib/fno-types";

import {
  calculateGreeks,
  calculateMaxPain,
  calculateGex,
} from "@/lib/greeks";

import { daysToExpiry, getLotSize, INDEX_SYMBOLS } from "@/lib/fno-types";

// ── Base fetcher — goes through existing /api rewrite to FastAPI :8000 ───────

const API_BASE =
  typeof window === "undefined"
    ? (process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000")
    : "";

async function apiGet<T>(path: string, params?: Record<string, string>): Promise<T> {
  const qs = params ? "?" + new URLSearchParams(params).toString() : "";
  const res = await fetch(`${API_BASE}${path}${qs}`, { cache: "no-store" });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`${path} → ${res.status}${text ? `: ${text.slice(0, 200)}` : ""}`);
  }
  return res.json() as Promise<T>;
}

async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`POST ${path} → ${res.status}`);
  return res.json() as Promise<T>;
}

// ── Direct FastAPI fetcher — bypasses the NSE proxy catch-all route ───────────
// Used for AI suggestions and paper trades which live in FastAPI, not NSE.
// CORS allows all origins (cors_origin_regex = ".*") so cross-origin calls work.

const FASTAPI_DIRECT = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

async function faGet<T>(path: string, params?: Record<string, string>): Promise<T> {
  const qs = params ? "?" + new URLSearchParams(params).toString() : "";
  const res = await fetch(`${FASTAPI_DIRECT}${path}${qs}`, { cache: "no-store" });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`${path} → ${res.status}${text ? `: ${text.slice(0, 200)}` : ""}`);
  }
  return res.json() as Promise<T>;
}

async function faPost<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${FASTAPI_DIRECT}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`POST ${path} → ${res.status}${text ? `: ${text.slice(0, 200)}` : ""}`);
  }
  return res.json() as Promise<T>;
}

// ── Option Chain ──────────────────────────────────────────────────────────────

interface FastAPIChainRow {
  strike: number;
  expiry: string;
  CE_oi?: number;         CE_oi_chg?: number;    CE_oi_chg_pct?: number;
  CE_vol?: number;        CE_iv?: number;         CE_ltp?: number;
  CE_chg?: number;        CE_chg_pct?: number;   CE_bid_qty?: number;
  CE_bid?: number;        CE_ask_qty?: number;    CE_ask?: number;
  PE_oi?: number;         PE_oi_chg?: number;    PE_oi_chg_pct?: number;
  PE_vol?: number;        PE_iv?: number;         PE_ltp?: number;
  PE_chg?: number;        PE_chg_pct?: number;   PE_bid_qty?: number;
  PE_bid?: number;        PE_ask_qty?: number;    PE_ask?: number;
}

interface FastAPIMeta {
  expiry_dates?: string[];
  strike_prices?: number[];
  underlying?: number;
  timestamp?: string;
  total_ce_oi?: number;
  total_pe_oi?: number;
  total_ce_vol?: number;
  total_pe_vol?: number;
  synthetic?: boolean;
  vix?: number;
}

function normaliseChain(rows: FastAPIChainRow[], meta: FastAPIMeta): OptionChainResponse {
  return {
    rows: rows.map((r) => ({
      strike: r.strike,
      expiry: r.expiry,
      CE: {
        oi: r.CE_oi ?? 0,
        oi_chg: r.CE_oi_chg ?? 0,
        oi_chg_pct: r.CE_oi_chg_pct ?? 0,
        vol: r.CE_vol ?? 0,
        iv: r.CE_iv ?? 0,
        ltp: r.CE_ltp ?? 0,
        chg: r.CE_chg ?? 0,
        chg_pct: r.CE_chg_pct ?? 0,
        bid_qty: r.CE_bid_qty ?? 0,
        bid: r.CE_bid ?? 0,
        ask_qty: r.CE_ask_qty ?? 0,
        ask: r.CE_ask ?? 0,
      },
      PE: {
        oi: r.PE_oi ?? 0,
        oi_chg: r.PE_oi_chg ?? 0,
        oi_chg_pct: r.PE_oi_chg_pct ?? 0,
        vol: r.PE_vol ?? 0,
        iv: r.PE_iv ?? 0,
        ltp: r.PE_ltp ?? 0,
        chg: r.PE_chg ?? 0,
        chg_pct: r.PE_chg_pct ?? 0,
        bid_qty: r.PE_bid_qty ?? 0,
        bid: r.PE_bid ?? 0,
        ask_qty: r.PE_ask_qty ?? 0,
        ask: r.PE_ask ?? 0,
      },
    })),
    meta: {
      expiry_dates: meta.expiry_dates ?? [],
      strike_prices: meta.strike_prices ?? [],
      underlying: meta.underlying ?? 0,
      timestamp: meta.timestamp ?? new Date().toISOString(),
      total_ce_oi: meta.total_ce_oi ?? 0,
      total_pe_oi: meta.total_pe_oi ?? 0,
      total_ce_vol: meta.total_ce_vol ?? 0,
      total_pe_vol: meta.total_pe_vol ?? 0,
      synthetic: meta.synthetic ?? false,
      vix: meta.vix,
    },
  };
}

export async function getOptionChain(symbol: string): Promise<OptionChainResponse> {
  const raw = await apiGet<{ rows: FastAPIChainRow[]; meta: FastAPIMeta }>(
    `/api/fno/option-chain`,
    { symbol }
  );
  return normaliseChain(raw.rows ?? [], raw.meta ?? {});
}

// ── Greeks enrichment ─────────────────────────────────────────────────────────

export function enrichChainWithGreeks(
  chain: OptionChainResponse,
  expiry?: string
): OptionChainResponse {
  const spot = chain.meta.underlying;
  const rows = chain.rows
    .filter((r) => !expiry || r.expiry === expiry)
    .map((row) => {
      const dte = daysToExpiry(row.expiry);
      const T = Math.max(dte, 1) / 365;

      const ceIv = row.CE.iv ? (row.CE.iv > 1 ? row.CE.iv / 100 : row.CE.iv) : 0.15;
      const peIv = row.PE.iv ? (row.PE.iv > 1 ? row.PE.iv / 100 : row.PE.iv) : 0.15;

      const ceG = calculateGreeks(spot, row.strike, T, ceIv, "CE");
      const peG = calculateGreeks(spot, row.strike, T, peIv, "PE");

      return {
        ...row,
        CE: { ...row.CE, delta: ceG.delta, gamma: ceG.gamma, theta: ceG.theta, vega: ceG.vega },
        PE: { ...row.PE, delta: peG.delta, gamma: peG.gamma, theta: peG.theta, vega: peG.vega },
      };
    });

  return { ...chain, rows };
}

// ── Max Pain ──────────────────────────────────────────────────────────────────

export function getMaxPain(chain: OptionChainResponse, expiry?: string): number {
  const rows = chain.rows
    .filter((r) => !expiry || r.expiry === expiry)
    .map((r) => ({ strike: r.strike, CE_oi: r.CE.oi ?? 0, PE_oi: r.PE.oi ?? 0 }));
  return calculateMaxPain(rows);
}

// ── GEX ───────────────────────────────────────────────────────────────────────

export function getGex(chain: OptionChainResponse, symbol: string, expiry?: string) {
  const spot = chain.meta.underlying;
  const rows = chain.rows
    .filter((r) => !expiry || r.expiry === expiry)
    .map((r) => ({
      strike: r.strike,
      gex_cr: 0,
      CE_oi: r.CE.oi ?? 0,
      PE_oi: r.PE.oi ?? 0,
      CE_iv: r.CE.iv ?? 15,
      PE_iv: r.PE.iv ?? 15,
    }));
  const dte = expiry ? daysToExpiry(expiry) : 30;
  return calculateGex(rows, spot, dte, getLotSize(symbol));
}

// ── Greeks table rows ─────────────────────────────────────────────────────────

export function buildGreeksRows(
  chain: OptionChainResponse,
  symbol: string,
  expiry?: string
): GreeksRow[] {
  const spot = chain.meta.underlying;
  const dte  = expiry ? daysToExpiry(expiry) : 30;
  const T    = Math.max(dte, 1) / 365;

  return chain.rows
    .filter((r) => !expiry || r.expiry === expiry)
    .map((row) => {
      const ceIv = row.CE.iv ? (row.CE.iv > 1 ? row.CE.iv / 100 : row.CE.iv) : 0.15;
      const peIv = row.PE.iv ? (row.PE.iv > 1 ? row.PE.iv / 100 : row.PE.iv) : 0.15;
      const ceG  = calculateGreeks(spot, row.strike, T, ceIv, "CE");
      const peG  = calculateGreeks(spot, row.strike, T, peIv, "PE");

      return {
        strike:   row.strike,
        CE_iv:    row.CE.iv ?? 0,
        CE_ltp:   row.CE.ltp ?? 0,
        CE_oi:    row.CE.oi ?? 0,
        CE_delta: ceG.delta,
        CE_gamma: ceG.gamma,
        CE_theta: ceG.theta,
        CE_vega:  ceG.vega,
        PE_delta: peG.delta,
        PE_gamma: peG.gamma,
        PE_theta: peG.theta,
        PE_vega:  peG.vega,
        PE_ltp:   row.PE.ltp ?? 0,
        PE_oi:    row.PE.oi ?? 0,
        PE_iv:    row.PE.iv ?? 0,
      };
    });
}

// ── Index Futures ─────────────────────────────────────────────────────────────

export async function getIndexFutures(): Promise<IndexFuture[]> {
  return apiGet<IndexFuture[]>("/api/fno/index-futures");
}

// ── VIX ───────────────────────────────────────────────────────────────────────

interface FastAPIVix {
  vix?: number | null;
  change?: number | null;
  change_pct?: number | null;
  open?: number | null;
  high?: number | null;
  low?: number | null;
  prev_close?: number | null;
}

export async function getVix(): Promise<VixData> {
  const raw = await apiGet<FastAPIVix>("/api/fno/vix");
  return {
    vix: raw.vix ?? null,
    change: raw.change ?? null,
    change_pct: raw.change_pct ?? null,
    open: raw.open ?? null,
    high: raw.high ?? null,
    low: raw.low ?? null,
    prev_close: raw.prev_close ?? null,
  };
}

// ── PCR ───────────────────────────────────────────────────────────────────────

export async function getPcr(symbol: string): Promise<PcrData> {
  const raw = await apiGet<Partial<PcrData>>("/api/fno/pcr", { symbol });
  return {
    symbol: raw.symbol ?? symbol,
    pcr_oi: raw.pcr_oi ?? 0,
    pcr_vol: raw.pcr_vol ?? 0,
    total_ce_oi: raw.total_ce_oi ?? 0,
    total_pe_oi: raw.total_pe_oi ?? 0,
    total_ce_vol: raw.total_ce_vol ?? 0,
    total_pe_vol: raw.total_pe_vol ?? 0,
  };
}

// ── OI Analytics ─────────────────────────────────────────────────────────────

interface FastAPIOIRow {
  symbol?: string;
  oi_current?: number;
  oi?: number;
  oi_prev?: number;
  prev_OI?: number;
  oi_change?: number;
  oi_change_pct?: number;
  ltp?: number;
  lastPrice?: number;
  price_chg_pct?: number;
  pChange?: number;
}

export async function getOiSpurts(): Promise<OISpurtRow[]> {
  const raw = await apiGet<FastAPIOIRow[]>("/api/fno/oi-spurts");
  return (raw ?? []).map((r) => ({
    symbol: r.symbol ?? "",
    oi_current: r.oi_current ?? r.oi ?? 0,
    oi_prev: r.oi_prev ?? r.prev_OI ?? 0,
    oi_change: r.oi_change ?? 0,
    oi_change_pct: r.oi_change_pct ?? 0,
    ltp: r.ltp ?? r.lastPrice ?? 0,
    price_chg_pct: r.price_chg_pct ?? r.pChange ?? 0,
  }));
}

export async function getOiBuildup(): Promise<OIBuildupRow[]> {
  const rows = await getOiSpurts();
  return rows.map((r) => {
    let classification: OIBuildupRow["classification"] = "Neutral";
    if (r.oi_change_pct > 5 && r.price_chg_pct > 0)  classification = "Long Buildup";
    if (r.oi_change_pct > 5 && r.price_chg_pct < 0)  classification = "Short Buildup";
    if (r.oi_change_pct < -5 && r.price_chg_pct > 0) classification = "Short Covering";
    if (r.oi_change_pct < -5 && r.price_chg_pct < 0) classification = "Long Unwinding";
    return { ...r, classification };
  });
}

// ── F&O Symbols ───────────────────────────────────────────────────────────────

export async function getFnoSymbols(): Promise<string[]> {
  try {
    return await faGet<string[]>("/api/fno/symbols");
  } catch {
    return [];
  }
}

export function getAllSymbols(): string[] {
  return [...INDEX_SYMBOLS];
}

// ── AI Suggestions ────────────────────────────────────────────────────────────

export async function getFnoAiSuggestion(symbol: string): Promise<FNOSuggestion> {
  return faGet<FNOSuggestion>("/api/fno/ai-suggest", { symbol });
}

// ── Paper Trades ──────────────────────────────────────────────────────────────

export async function getOpenTrades(): Promise<PaperTrade[]> {
  return faGet<PaperTrade[]>("/api/fno/paper-trades/open");
}

export async function getClosedTrades(): Promise<PaperTrade[]> {
  return faGet<PaperTrade[]>("/api/fno/paper-trades/closed");
}

export async function addPaperTrade(trade: {
  symbol: string; instrument_type: string; strike: number; expiry: string;
  action: string; lots: number; lot_size: number; entry_price: number;
  target_price: number; stop_loss: number; source?: string;
  ai_confidence?: string; strategy_name?: string;
}): Promise<{ ok: boolean; message: string }> {
  return faPost("/api/fno/paper-trades", trade);
}

export async function closePaperTrade(
  tradeId: string,
  exitPrice: number,
  exitReason = "MANUAL",
): Promise<{ ok: boolean; message: string }> {
  return faPost(`/api/fno/paper-trades/${tradeId}/close`, {
    exit_price: exitPrice,
    exit_reason: exitReason,
  });
}

export async function getPortfolioSummary(): Promise<PortfolioSummary> {
  return faGet<PortfolioSummary>("/api/fno/paper-trades/portfolio");
}

export async function getEquityCurve(): Promise<{ date: string; cumulative_pnl: number; trade_pnl: number; symbol: string }[]> {
  return faGet<{ date: string; cumulative_pnl: number; trade_pnl: number; symbol: string }[]>("/api/fno/paper-trades/equity-curve");
}

export async function resetPortfolio(initialCapital = 500_000): Promise<{ ok: boolean }> {
  return faPost("/api/fno/paper-trades/reset", { initial_capital: initialCapital });
}

// ── Saved Strategies (server-side via FastAPI) ────────────────────────────────

export async function getSavedStrategies(): Promise<SavedStrategy[]> {
  try {
    return await apiGet<SavedStrategy[]>("/api/fno/strategies");
  } catch {
    return [];
  }
}

export async function saveStrategy(name: string, legs: StrategyLeg[]): Promise<void> {
  await apiPost("/api/fno/strategies", { name, legs });
}

export async function deleteStrategy(name: string): Promise<void> {
  const base = typeof window === "undefined"
    ? (process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000")
    : "";
  await fetch(`${base}/api/fno/strategies/${encodeURIComponent(name)}`, {
    method: "DELETE",
  });
}

// ── F&O Scanner (client-side, computed from option chain data) ────────────────

export async function runFoScan(
  scanType: FoScanType,
  symbols: string[],
  maxWorkers = 4
): Promise<FoScanRow[]> {
  const results: FoScanRow[] = [];

  for (let i = 0; i < symbols.length; i += maxWorkers) {
    const chunk = symbols.slice(i, i + maxWorkers);
    const settled = await Promise.allSettled(chunk.map((sym) => _scanSymbol(sym, scanType)));
    for (const s of settled) {
      if (s.status === "fulfilled" && s.value) results.push(s.value);
    }
  }

  return results.sort((a, b) => b.strength - a.strength);
}

async function _scanSymbol(symbol: string, scanType: FoScanType): Promise<FoScanRow | null> {
  try {
    const chain = await getOptionChain(symbol);
    const spot  = chain.meta.underlying;
    const exp   = chain.meta.expiry_dates[0] ?? "";
    const dte   = daysToExpiry(exp);
    const rows  = chain.rows.filter((r) => r.expiry === exp);

    switch (scanType) {
      case "High OI Buildup": {
        const totalOi = rows.reduce((a, r) => a + (r.CE.oi ?? 0) + (r.PE.oi ?? 0), 0);
        if (totalOi < 100_000) return null;
        return { symbol, signal_type: scanType, metric: `OI ${(totalOi / 1e5).toFixed(1)}L`, direction: "Neutral", strength: Math.min(99, Math.round(totalOi / 1e6)), expiry: exp, dte };
      }
      case "PCR Extremes": {
        const ceOi = rows.reduce((a, r) => a + (r.CE.oi ?? 0), 0);
        const peOi = rows.reduce((a, r) => a + (r.PE.oi ?? 0), 0);
        if (!ceOi) return null;
        const pcr = peOi / ceOi;
        const direction = pcr > 1.2 ? "Bullish" : pcr < 0.8 ? "Bearish" : "Neutral";
        if (direction === "Neutral") return null;
        return { symbol, signal_type: scanType, metric: `PCR ${pcr.toFixed(2)}`, direction, strength: Math.min(99, Math.round(Math.abs(pcr - 1) * 100)), expiry: exp, dte };
      }
      case "Max Pain Divergence": {
        const mp   = calculateMaxPain(rows.map((r) => ({ strike: r.strike, CE_oi: r.CE.oi ?? 0, PE_oi: r.PE.oi ?? 0 })));
        const diff = Math.abs(spot - mp);
        const pct  = spot ? (diff / spot) * 100 : 0;
        if (pct < 0.5) return null;
        return { symbol, signal_type: scanType, metric: `MaxPain ₹${mp.toFixed(0)} (${pct.toFixed(1)}% away)`, direction: spot > mp ? "Bearish" : "Bullish", strength: Math.min(99, Math.round(pct * 10)), expiry: exp, dte };
      }
      case "Unusual Volume": {
        const ceVol = rows.reduce((a, r) => a + (r.CE.vol ?? 0), 0);
        const peVol = rows.reduce((a, r) => a + (r.PE.vol ?? 0), 0);
        const totalVol = ceVol + peVol;
        const ceOi = rows.reduce((a, r) => a + (r.CE.oi ?? 0), 0);
        if (!ceOi || totalVol < 1000) return null;
        const ratio = totalVol / ceOi;
        if (ratio < 0.3) return null;
        return { symbol, signal_type: scanType, metric: `Vol/OI ${ratio.toFixed(2)}`, direction: ceVol > peVol ? "Bullish" : "Bearish", strength: Math.min(99, Math.round(ratio * 50)), expiry: exp, dte };
      }
      case "IV Crush Candidates": {
        const ivs = rows.flatMap((r) => [r.CE.iv ?? 0, r.PE.iv ?? 0]).filter(Boolean);
        if (!ivs.length) return null;
        const avgIv = ivs.reduce((a, v) => a + v, 0) / ivs.length;
        if (avgIv < 20) return null;
        return { symbol, signal_type: scanType, metric: `Avg IV ${avgIv.toFixed(1)}%`, direction: "Neutral", strength: Math.min(99, Math.round(avgIv)), expiry: exp, dte };
      }
      default:
        return null;
    }
  } catch {
    return null;
  }
}
