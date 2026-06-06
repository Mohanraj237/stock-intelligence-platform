/**
 * Black-Scholes options Greeks calculator — pure TypeScript, zero dependencies.
 * Abramowitz & Stegun normal CDF approximation (accuracy ~7 decimal places).
 * India risk-free rate = 6.5% (RBI repo rate).
 */

export const RISK_FREE_RATE = 0.065;

// ── Normal distribution ───────────────────────────────────────────────────────

function normalCDF(x: number): number {
  const a1 =  0.254829592;
  const a2 = -0.284496736;
  const a3 =  1.421413741;
  const a4 = -1.453152027;
  const a5 =  1.061405429;
  const p  =  0.3275911;
  const sign = x < 0 ? -1 : 1;
  const ax = Math.abs(x) / Math.sqrt(2);
  const t = 1 / (1 + p * ax);
  const y = 1 - (((((a5 * t + a4) * t + a3) * t + a2) * t + a1) * t * Math.exp(-ax * ax));
  return 0.5 * (1 + sign * y);
}

function normalPDF(x: number): number {
  return Math.exp(-0.5 * x * x) / Math.sqrt(2 * Math.PI);
}

// ── Black-Scholes price ───────────────────────────────────────────────────────

export function bsPrice(
  S: number, K: number, T: number, r: number, sigma: number, type: "CE" | "PE"
): number {
  if (T <= 0 || sigma <= 0 || S <= 0 || K <= 0) {
    return Math.max(0, type === "CE" ? S - K : K - S);
  }
  const d1 = (Math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * Math.sqrt(T));
  const d2 = d1 - sigma * Math.sqrt(T);
  if (type === "CE") {
    return S * normalCDF(d1) - K * Math.exp(-r * T) * normalCDF(d2);
  }
  return K * Math.exp(-r * T) * normalCDF(-d2) - S * normalCDF(-d1);
}

// ── Implied Volatility (Brent-like bisection) ─────────────────────────────────

export function calculateIV(
  optionPrice: number, S: number, K: number, T: number, type: "CE" | "PE",
  r = RISK_FREE_RATE
): number {
  if (optionPrice <= 0 || T <= 0 || S <= 0 || K <= 0) return 0;
  const intrinsic = Math.max(0, type === "CE" ? S - K : K - S);
  if (optionPrice < intrinsic) return 0;

  let lo = 1e-6, hi = 5.0;
  for (let i = 0; i < 100; i++) {
    const mid = (lo + hi) / 2;
    const price = bsPrice(S, K, T, r, mid, type);
    if (Math.abs(price - optionPrice) < 1e-5) return mid;
    if (price < optionPrice) lo = mid; else hi = mid;
  }
  return (lo + hi) / 2;
}

// ── Greeks ────────────────────────────────────────────────────────────────────

export interface GreeksResult {
  delta: number; gamma: number; theta: number; vega: number; rho: number;
  d1: number; d2: number; bsPrice: number; intrinsic: number; timeValue: number;
}

export function calculateGreeks(
  S: number, K: number, T: number, iv: number, type: "CE" | "PE",
  r = RISK_FREE_RATE
): GreeksResult {
  const zero: GreeksResult = {
    delta: 0, gamma: 0, theta: 0, vega: 0, rho: 0,
    d1: 0, d2: 0, bsPrice: 0, intrinsic: 0, timeValue: 0,
  };

  if (T <= 0 || iv <= 0 || S <= 0 || K <= 0) {
    const intrinsic = Math.max(0, type === "CE" ? S - K : K - S);
    return { ...zero, intrinsic, bsPrice: intrinsic };
  }

  const sqrtT = Math.sqrt(T);
  const d1 = (Math.log(S / K) + (r + 0.5 * iv * iv) * T) / (iv * sqrtT);
  const d2 = d1 - iv * sqrtT;
  const disc = Math.exp(-r * T);
  const isCall = type === "CE";

  const delta = isCall ? normalCDF(d1) : normalCDF(d1) - 1;
  const gamma = normalPDF(d1) / (S * iv * sqrtT);

  const thetaCall = (-S * normalPDF(d1) * iv / (2 * sqrtT) - r * K * disc * normalCDF(d2)) / 365;
  const thetaPut  = (-S * normalPDF(d1) * iv / (2 * sqrtT) + r * K * disc * normalCDF(-d2)) / 365;
  const theta = isCall ? thetaCall : thetaPut;

  const vega = S * normalPDF(d1) * sqrtT / 100;

  const rhoCall =  K * T * disc * normalCDF(d2)  / 100;
  const rhoPut  = -K * T * disc * normalCDF(-d2) / 100;
  const rho = isCall ? rhoCall : rhoPut;

  const price     = bsPrice(S, K, T, r, iv, type);
  const intrinsic = Math.max(0, isCall ? S - K : K - S);

  return {
    delta:     +delta.toFixed(4),
    gamma:     +gamma.toFixed(6),
    theta:     +theta.toFixed(4),
    vega:      +vega.toFixed(4),
    rho:       +rho.toFixed(4),
    d1:        +d1.toFixed(4),
    d2:        +d2.toFixed(4),
    bsPrice:   +price.toFixed(2),
    intrinsic: +intrinsic.toFixed(2),
    timeValue: +Math.max(0, price - intrinsic).toFixed(2),
  };
}

// ── Max Pain ──────────────────────────────────────────────────────────────────

export interface MaxPainRow { strike: number; CE_oi: number; PE_oi: number }

export function calculateMaxPain(rows: MaxPainRow[]): number {
  const strikes = rows.map((r) => r.strike);
  if (!strikes.length) return 0;

  let minPain = Infinity;
  let maxPainStrike = 0;

  for (const test of strikes) {
    let pain = 0;
    for (const { strike, CE_oi, PE_oi } of rows) {
      pain += (CE_oi ?? 0) * Math.max(test - strike, 0);
      pain += (PE_oi ?? 0) * Math.max(strike - test, 0);
    }
    if (pain < minPain) { minPain = pain; maxPainStrike = test; }
  }
  return maxPainStrike;
}

// ── GEX per strike ────────────────────────────────────────────────────────────

export interface GexRow { strike: number; gex_cr: number; CE_oi: number; PE_oi: number; CE_iv: number; PE_iv: number }

export function calculateGex(
  rows: GexRow[], spot: number, dte: number, lotSize: number, r = RISK_FREE_RATE
): (GexRow & { gex_cr: number })[] {
  const T = Math.max(dte, 1) / 365;
  return rows.map((row) => {
    const K    = row.strike;
    const ceIv = (row.CE_iv > 1 ? row.CE_iv / 100 : row.CE_iv) || 0.15;
    const peIv = (row.PE_iv > 1 ? row.PE_iv / 100 : row.PE_iv) || 0.15;
    const ceG  = calculateGreeks(spot, K, T, ceIv, "CE", r);
    const peG  = calculateGreeks(spot, K, T, peIv, "PE", r);
    const gex  = ((row.CE_oi ?? 0) * ceG.gamma - (row.PE_oi ?? 0) * peG.gamma) * lotSize * spot * spot / 100;
    return { ...row, gex_cr: +(gex / 1e7).toFixed(2) };
  });
}
