"""
Black-Scholes options Greeks calculator.
India risk-free rate = 6.5% (RBI repo rate).
Uses scipy for IV solving via Brent's method.
"""
from __future__ import annotations

import math
import logging
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# India risk-free rate (RBI repo rate)
RISK_FREE_RATE = 0.065

try:
    from scipy.stats import norm
    from scipy.optimize import brentq
    _SCIPY_OK = True
except ImportError:
    _SCIPY_OK = False
    logger.warning("scipy not installed — IV calculation will use approximation")


# ── Black-Scholes core ────────────────────────────────────────────────────────

def _bs_price(S: float, K: float, T: float, r: float, sigma: float, option_type: str) -> float:
    """Black-Scholes option price.  option_type: 'CE' or 'PE'."""
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return max(0.0, (S - K) if option_type == "CE" else (K - S))

    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)

    if _SCIPY_OK:
        N = norm.cdf
    else:
        def N(x):
            return 0.5 * (1 + math.erf(x / math.sqrt(2)))

    if option_type.upper() in ("CE", "CALL", "C"):
        return S * N(d1) - K * math.exp(-r * T) * N(d2)
    else:
        return K * math.exp(-r * T) * N(-d2) - S * N(-d1)


def _bs_vega(S: float, K: float, T: float, r: float, sigma: float) -> float:
    """Vega (for IV Newton-Raphson fallback)."""
    if T <= 0 or sigma <= 0 or S <= 0:
        return 0.0
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    if _SCIPY_OK:
        nprime_d1 = norm.pdf(d1)
    else:
        nprime_d1 = math.exp(-0.5 * d1 ** 2) / math.sqrt(2 * math.pi)
    return S * nprime_d1 * math.sqrt(T)


# ── Implied Volatility ────────────────────────────────────────────────────────

def calculate_iv(
    option_price: float,
    S: float,
    K: float,
    T: float,
    option_type: str,
    r: float = RISK_FREE_RATE,
) -> float:
    """
    Solve for implied volatility using Brent's method (scipy) or
    Newton-Raphson fallback.

    Returns annualised IV (0-5 range, i.e. 0% – 500%).
    Returns 0.0 on failure.
    """
    if option_price <= 0 or T <= 0 or S <= 0 or K <= 0:
        return 0.0

    intrinsic = max(0.0, (S - K) if option_type.upper() in ("CE", "C") else (K - S))
    if option_price < intrinsic:
        return 0.0

    def objective(sigma):
        return _bs_price(S, K, T, r, sigma, option_type) - option_price

    if _SCIPY_OK:
        try:
            iv = brentq(objective, 1e-6, 5.0, xtol=1e-6, maxiter=100)
            return round(iv, 6)
        except Exception:
            pass

    # Newton-Raphson fallback
    sigma = 0.20
    for _ in range(50):
        price = _bs_price(S, K, T, r, sigma, option_type)
        vega  = _bs_vega(S, K, T, r, sigma)
        diff  = price - option_price
        if abs(diff) < 1e-5:
            break
        if abs(vega) < 1e-10:
            break
        sigma -= diff / vega
        sigma = max(1e-6, min(sigma, 5.0))

    return round(sigma, 6)


# ── Greeks ────────────────────────────────────────────────────────────────────

def calculate_greeks(
    S: float,
    K: float,
    T: float,
    iv: float,
    option_type: str,
    r: float = RISK_FREE_RATE,
) -> dict:
    """
    Calculate option Greeks.

    Returns:
        delta, gamma, theta (per day), vega (per 1% IV move),
        rho, d1, d2, bs_price, intrinsic, time_value
    """
    result = {
        "delta": 0.0, "gamma": 0.0, "theta": 0.0,
        "vega": 0.0, "rho": 0.0,
        "d1": 0.0, "d2": 0.0,
        "bs_price": 0.0, "intrinsic": 0.0, "time_value": 0.0,
    }

    if T <= 0 or iv <= 0 or S <= 0 or K <= 0:
        if T <= 0:
            intrinsic = max(0.0, (S - K) if option_type.upper() in ("CE", "C") else (K - S))
            result["intrinsic"] = intrinsic
            result["bs_price"]  = intrinsic
            result["delta"]     = 1.0 if (S > K and option_type.upper() in ("CE", "C")) else 0.0
        return result

    sigma = iv
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)

    if _SCIPY_OK:
        N  = norm.cdf
        Np = norm.pdf
    else:
        def N(x):
            return 0.5 * (1 + math.erf(x / math.sqrt(2)))
        def Np(x):
            return math.exp(-0.5 * x * x) / math.sqrt(2 * math.pi)

    disc = math.exp(-r * T)
    sqrt_T = math.sqrt(T)

    is_call = option_type.upper() in ("CE", "CALL", "C")

    # Delta
    delta = N(d1) if is_call else N(d1) - 1

    # Gamma
    gamma = Np(d1) / (S * sigma * sqrt_T)

    # Theta (per calendar day, in ₹)
    theta_call = (
        -S * Np(d1) * sigma / (2 * sqrt_T)
        - r * K * disc * N(d2)
    ) / 365
    theta_put  = (
        -S * Np(d1) * sigma / (2 * sqrt_T)
        + r * K * disc * N(-d2)
    ) / 365
    theta = theta_call if is_call else theta_put

    # Vega (per 1% move in IV, in ₹)
    vega = S * Np(d1) * sqrt_T / 100

    # Rho (per 1% move in r)
    rho_call =  K * T * disc * N(d2)  / 100
    rho_put  = -K * T * disc * N(-d2) / 100
    rho = rho_call if is_call else rho_put

    # Price components
    bs_price  = _bs_price(S, K, T, r, sigma, option_type)
    intrinsic = max(0.0, (S - K) if is_call else (K - S))
    time_value = max(0.0, bs_price - intrinsic)

    result.update({
        "delta":      round(delta, 4),
        "gamma":      round(gamma, 6),
        "theta":      round(theta, 4),
        "vega":       round(vega, 4),
        "rho":        round(rho, 4),
        "d1":         round(d1, 4),
        "d2":         round(d2, 4),
        "bs_price":   round(bs_price, 2),
        "intrinsic":  round(intrinsic, 2),
        "time_value": round(time_value, 2),
    })
    return result


# ── Enrich option chain DataFrame with Greeks ─────────────────────────────────

def enrich_chain_with_greeks(df: "pd.DataFrame", spot: float, dte: int) -> "pd.DataFrame":
    """
    Add Greeks columns to an option chain DataFrame.
    DTE = days to expiry (calendar days).
    """
    import pandas as pd

    if df.empty or spot <= 0:
        return df

    T = max(dte, 1) / 365.0

    ce_greeks = []
    pe_greeks = []

    for _, row in df.iterrows():
        K = row.get("strike", 0)

        ce_iv  = row.get("CE_iv", 0) / 100 if row.get("CE_iv", 0) else 0
        ce_ltp = row.get("CE_ltp", 0)
        if ce_iv <= 0 and ce_ltp > 0:
            ce_iv = calculate_iv(ce_ltp, spot, K, T, "CE")
        cg = calculate_greeks(spot, K, T, ce_iv, "CE") if ce_iv > 0 else {}
        ce_greeks.append(cg)

        pe_iv  = row.get("PE_iv", 0) / 100 if row.get("PE_iv", 0) else 0
        pe_ltp = row.get("PE_ltp", 0)
        if pe_iv <= 0 and pe_ltp > 0:
            pe_iv = calculate_iv(pe_ltp, spot, K, T, "PE")
        pg = calculate_greeks(spot, K, T, pe_iv, "PE") if pe_iv > 0 else {}
        pe_greeks.append(pg)

    # Flatten dicts into columns
    for greek in ["delta", "gamma", "theta", "vega"]:
        df[f"CE_{greek}"] = [g.get(greek, 0) for g in ce_greeks]
        df[f"PE_{greek}"] = [g.get(greek, 0) for g in pe_greeks]

    df["CE_iv_calc"] = [g.get("d1", 0) for g in ce_greeks]   # keep d1 for ref
    df["PE_iv_calc"] = [g.get("d1", 0) for g in pe_greeks]

    return df


# ── Max Pain ─────────────────────────────────────────────────────────────────

def calculate_max_pain(df: "pd.DataFrame") -> float:
    """
    Calculate max pain strike — the strike at which total options writer profit is maximised
    (i.e., where total buyer pain is maximised).

    df must have columns: strike, CE_oi, PE_oi
    Returns max pain strike price (float).
    """
    import pandas as pd

    if df.empty:
        return 0.0

    strikes = sorted(df["strike"].unique())
    if not strikes:
        return 0.0

    pain_per_strike = {}
    for test_strike in strikes:
        total_pain = 0.0
        for _, row in df.iterrows():
            k = row["strike"]
            ce_oi = row.get("CE_oi", 0) or 0
            pe_oi = row.get("PE_oi", 0) or 0
            # Call buyers lose if test_strike < K → 0 pain for call OI at K
            # Call OI pain = CE_OI * max(test_strike - K, 0)  (in-the-money calls)
            # Put OI pain  = PE_OI * max(K - test_strike, 0)
            total_pain += ce_oi * max(test_strike - k, 0)
            total_pain += pe_oi * max(k - test_strike, 0)
        pain_per_strike[test_strike] = total_pain

    if not pain_per_strike:
        return 0.0
    return min(pain_per_strike, key=pain_per_strike.get)


# ── Gamma Exposure (GEX) ──────────────────────────────────────────────────────

def calculate_gex(df: "pd.DataFrame", spot: float, dte: int, lot_size: int = 1) -> "pd.DataFrame":
    """
    Calculate dealer Gamma Exposure (GEX) per strike.

    Dealers are assumed short calls and long puts (simplification).
    GEX per strike = (CE_gamma * CE_oi - PE_gamma * PE_oi) * lot_size * spot²  / 100

    Returns df with 'gex' column added, sorted by strike.
    """
    import pandas as pd

    if df.empty or spot <= 0:
        return df

    T = max(dte, 1) / 365.0
    gex_values = []

    for _, row in df.iterrows():
        K    = row.get("strike", 0)
        ce_iv = row.get("CE_iv", 0) / 100 if row.get("CE_iv", 0) else 0.15
        pe_iv = row.get("PE_iv", 0) / 100 if row.get("PE_iv", 0) else 0.15

        cg = calculate_greeks(spot, K, T, ce_iv, "CE")
        pg = calculate_greeks(spot, K, T, pe_iv, "PE")

        ce_oi = row.get("CE_oi", 0) or 0
        pe_oi = row.get("PE_oi", 0) or 0

        # Dealer GEX: long gamma from puts they bought, short gamma from calls they sold
        gex = (ce_oi * cg["gamma"] - pe_oi * pg["gamma"]) * lot_size * spot * spot / 100
        gex_values.append(round(gex, 2))

    df = df.copy()
    df["gex"] = gex_values
    return df


# ── IV Percentile ─────────────────────────────────────────────────────────────

def iv_percentile(current_iv: float, iv_history: list[float]) -> float:
    """
    Returns IV percentile (0-100): how high current IV is relative to history.
    """
    if not iv_history or current_iv <= 0:
        return 50.0
    below = sum(1 for iv in iv_history if iv < current_iv)
    return round(below / len(iv_history) * 100, 1)


# ── ATM Strike Finder ─────────────────────────────────────────────────────────

def find_atm_strike(strikes: list[float], spot: float) -> float:
    """Return the strike closest to spot."""
    if not strikes or spot <= 0:
        return 0.0
    return min(strikes, key=lambda k: abs(k - spot))
