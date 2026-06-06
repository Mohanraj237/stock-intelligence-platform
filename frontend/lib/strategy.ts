/**
 * Strategy payoff calculator — pure TypeScript, mirrors strategy_calculator.py.
 * All monetary values in ₹.
 */

import { calculateGreeks, RISK_FREE_RATE } from "./greeks";
import type { StrategyLeg } from "./fno-types";

// ── Leg helpers ───────────────────────────────────────────────────────────────

export function legSign(leg: StrategyLeg): number {
  return leg.action === "BUY" ? 1 : -1;
}

export function legQty(leg: StrategyLeg): number {
  return leg.lots * leg.lot_size;
}

/** P&L of one leg at a given spot price at expiry. */
function legPnl(leg: StrategyLeg, spot: number): number {
  const { option_type, strike, ltp } = leg;
  let intrinsic = 0;
  if (option_type === "CE") intrinsic = Math.max(spot - strike, 0);
  else if (option_type === "PE") intrinsic = Math.max(strike - spot, 0);
  else intrinsic = spot - strike; // FUT — long basis only

  const premium = ltp; // cost/credit per unit
  return (intrinsic - premium) * legSign(leg) * legQty(leg);
}

// ── Payoff diagram ────────────────────────────────────────────────────────────

export function calculatePayoff(
  legs: StrategyLeg[],
  spot: number,
  spotRangePct = 0.10,
  nPoints = 200
): { prices: number[]; pnl: number[] } {
  const lo = spot * (1 - spotRangePct);
  const hi = spot * (1 + spotRangePct);
  const step = (hi - lo) / (nPoints - 1);

  const prices: number[] = [];
  const pnl: number[] = [];

  for (let i = 0; i < nPoints; i++) {
    const p = lo + i * step;
    prices.push(+p.toFixed(2));
    pnl.push(+legs.reduce((acc, leg) => acc + legPnl(leg, p), 0).toFixed(2));
  }
  return { prices, pnl };
}

// ── Max profit / loss ─────────────────────────────────────────────────────────

export function calculateMaxProfitLoss(
  legs: StrategyLeg[],
  spot: number,
  spotRangePct = 0.30
): {
  maxProfit: number;
  maxLoss: number;
  netPremium: number;
  isDebit: boolean;
  unlimitedProfit: boolean;
  unlimitedLoss: boolean;
} {
  const netPremium = legs.reduce(
    (acc, leg) => acc + legSign(leg) * leg.ltp * legQty(leg),
    0
  );

  const hasLongCall  = legs.some((l) => l.option_type === "CE" && l.action === "BUY");
  const hasShortCall = legs.some((l) => l.option_type === "CE" && l.action === "SELL");
  const hasLongPut   = legs.some((l) => l.option_type === "PE" && l.action === "BUY");
  const hasShortPut  = legs.some((l) => l.option_type === "PE" && l.action === "SELL");
  const hasLongFut   = legs.some((l) => l.option_type === "FUT" && l.action === "BUY");
  const hasShortFut  = legs.some((l) => l.option_type === "FUT" && l.action === "SELL");

  const unlimitedProfit = hasLongCall || hasLongFut;
  const unlimitedLoss   = hasShortCall || hasLongPut || hasShortFut;

  const { prices, pnl } = calculatePayoff(legs, spot, spotRangePct, 500);
  const maxProfit = Math.max(...pnl);
  const maxLoss   = Math.min(...pnl);

  // Suppress unused-var warnings — we reference them for semantic clarity
  void hasShortCall; void hasLongPut; void hasShortPut;

  return {
    maxProfit: +maxProfit.toFixed(2),
    maxLoss:   +maxLoss.toFixed(2),
    netPremium: +netPremium.toFixed(2),
    isDebit:   netPremium > 0,
    unlimitedProfit,
    unlimitedLoss,
  };
}

// ── Breakevens ────────────────────────────────────────────────────────────────

export function calculateBreakevens(
  legs: StrategyLeg[],
  spot: number,
  spotRangePct = 0.20,
  nPoints = 2000
): number[] {
  const { prices, pnl } = calculatePayoff(legs, spot, spotRangePct, nPoints);
  const breakevens: number[] = [];

  for (let i = 1; i < pnl.length; i++) {
    if (pnl[i - 1] * pnl[i] < 0) {
      // Linear interpolation
      const t = -pnl[i - 1] / (pnl[i] - pnl[i - 1]);
      const be = prices[i - 1] + t * (prices[i] - prices[i - 1]);
      breakevens.push(+be.toFixed(2));
    }
  }
  return breakevens;
}

// ── Position Greeks ───────────────────────────────────────────────────────────

export function calculatePositionGreeks(
  legs: StrategyLeg[],
  spot: number,
  r = RISK_FREE_RATE
): { delta: number; gamma: number; theta: number; vega: number } {
  let delta = 0, gamma = 0, theta = 0, vega = 0;

  for (const leg of legs) {
    if (leg.option_type === "FUT") {
      delta += legSign(leg) * legQty(leg);
      continue;
    }

    const T  = Math.max(leg.dte ?? 1, 1) / 365;
    const iv = (leg.iv ?? 0.15) > 1 ? (leg.iv ?? 0.15) / 100 : (leg.iv ?? 0.15);
    const g  = calculateGreeks(spot, leg.strike, T, iv, leg.option_type as "CE" | "PE", r);
    const qty = legSign(leg) * legQty(leg);

    delta += g.delta * qty;
    gamma += g.gamma * qty;
    theta += g.theta * qty;
    vega  += g.vega  * qty;
  }

  return {
    delta: +delta.toFixed(4),
    gamma: +gamma.toFixed(6),
    theta: +theta.toFixed(2),
    vega:  +vega.toFixed(2),
  };
}

// ── Margin estimate ───────────────────────────────────────────────────────────

export function estimateMargin(
  legs: StrategyLeg[],
  spot: number
): {
  spanMargin: number;
  exposureMargin: number;
  totalMargin: number;
  premiumPaid: number;
  premiumReceived: number;
} {
  let spanMargin = 0;
  let premiumPaid = 0;
  let premiumReceived = 0;

  const SPAN_PCT = 0.065;   // ~6.5% SPAN approximation
  const EXP_PCT  = 0.03;    // ~3% exposure margin

  for (const leg of legs) {
    const qty = legQty(leg);
    const notional = spot * qty;
    const premium  = leg.ltp * qty;

    if (leg.action === "SELL") {
      spanMargin     += notional * SPAN_PCT;
      premiumReceived += premium;
    } else {
      premiumPaid += premium;
    }
  }

  // Hedge credit: if there are both long and short options of same type,
  // reduce SPAN by 50% (simplified NSE hedge margin benefit).
  const hasHedge =
    legs.some((l) => l.option_type === "CE" && l.action === "BUY") &&
    legs.some((l) => l.option_type === "CE" && l.action === "SELL");
  const hasPutHedge =
    legs.some((l) => l.option_type === "PE" && l.action === "BUY") &&
    legs.some((l) => l.option_type === "PE" && l.action === "SELL");

  if (hasHedge || hasPutHedge) spanMargin *= 0.5;

  const exposureMargin = spanMargin * (EXP_PCT / SPAN_PCT);

  return {
    spanMargin:     +spanMargin.toFixed(2),
    exposureMargin: +exposureMargin.toFixed(2),
    totalMargin:    +(spanMargin + exposureMargin).toFixed(2),
    premiumPaid:    +premiumPaid.toFixed(2),
    premiumReceived: +premiumReceived.toFixed(2),
  };
}

// ── Strategy templates ────────────────────────────────────────────────────────

export interface TemplateLeg {
  option_type: "CE" | "PE" | "FUT";
  action: "BUY" | "SELL";
  strike_offset: number; // index offset from ATM
}

export const STRATEGY_TEMPLATES: Record<string, TemplateLeg[]> = {
  "Long Call":        [{ option_type: "CE", action: "BUY",  strike_offset: 0 }],
  "Long Put":         [{ option_type: "PE", action: "BUY",  strike_offset: 0 }],
  "Short Call":       [{ option_type: "CE", action: "SELL", strike_offset: 0 }],
  "Short Put":        [{ option_type: "PE", action: "SELL", strike_offset: 0 }],

  "Bull Call Spread": [
    { option_type: "CE", action: "BUY",  strike_offset: 0 },
    { option_type: "CE", action: "SELL", strike_offset: 2 },
  ],
  "Bear Put Spread": [
    { option_type: "PE", action: "BUY",  strike_offset: 0 },
    { option_type: "PE", action: "SELL", strike_offset: -2 },
  ],
  "Bull Put Spread": [
    { option_type: "PE", action: "SELL", strike_offset: 0 },
    { option_type: "PE", action: "BUY",  strike_offset: -2 },
  ],
  "Bear Call Spread": [
    { option_type: "CE", action: "SELL", strike_offset: 0 },
    { option_type: "CE", action: "BUY",  strike_offset: 2 },
  ],

  "Long Straddle": [
    { option_type: "CE", action: "BUY", strike_offset: 0 },
    { option_type: "PE", action: "BUY", strike_offset: 0 },
  ],
  "Short Straddle": [
    { option_type: "CE", action: "SELL", strike_offset: 0 },
    { option_type: "PE", action: "SELL", strike_offset: 0 },
  ],
  "Long Strangle": [
    { option_type: "CE", action: "BUY", strike_offset: 2  },
    { option_type: "PE", action: "BUY", strike_offset: -2 },
  ],
  "Short Strangle": [
    { option_type: "CE", action: "SELL", strike_offset: 2  },
    { option_type: "PE", action: "SELL", strike_offset: -2 },
  ],

  "Iron Condor": [
    { option_type: "PE", action: "BUY",  strike_offset: -4 },
    { option_type: "PE", action: "SELL", strike_offset: -2 },
    { option_type: "CE", action: "SELL", strike_offset: 2  },
    { option_type: "CE", action: "BUY",  strike_offset: 4  },
  ],
  "Iron Butterfly": [
    { option_type: "PE", action: "BUY",  strike_offset: -2 },
    { option_type: "PE", action: "SELL", strike_offset: 0  },
    { option_type: "CE", action: "SELL", strike_offset: 0  },
    { option_type: "CE", action: "BUY",  strike_offset: 2  },
  ],

  "Covered Call": [
    { option_type: "FUT", action: "BUY",  strike_offset: 0 },
    { option_type: "CE",  action: "SELL", strike_offset: 2 },
  ],
  "Protective Put": [
    { option_type: "FUT", action: "BUY",  strike_offset: 0 },
    { option_type: "PE",  action: "BUY",  strike_offset: -2 },
  ],
};

/** Build `strikes` index → actual strike using ATM index + offset. */
export function templateToLegs(
  templateName: string,
  symbol: string,
  expiry: string,
  dte: number,
  lotSize: number,
  strikes: number[],
  atmStrike: number,
  getLtp: (strike: number, type: "CE" | "PE" | "FUT") => number,
  getIv: (strike: number, type: "CE" | "PE" | "FUT") => number,
  spot: number
): StrategyLeg[] {
  const tpl = STRATEGY_TEMPLATES[templateName];
  if (!tpl || !strikes.length) return [];

  const atmIdx = strikes.indexOf(atmStrike);
  if (atmIdx === -1) return [];

  return tpl.map((td) => {
    const idx    = Math.max(0, Math.min(atmIdx + td.strike_offset, strikes.length - 1));
    const strike = strikes[idx];
    const ltp    = td.option_type === "FUT" ? spot : getLtp(strike, td.option_type);
    const iv     = td.option_type === "FUT" ? 0    : getIv(strike, td.option_type);

    return {
      symbol,
      expiry,
      strike,
      option_type: td.option_type,
      action: td.action,
      lots: 1,
      lot_size: lotSize,
      ltp,
      iv: iv > 1 ? iv / 100 : iv,
      dte,
    };
  });
}
