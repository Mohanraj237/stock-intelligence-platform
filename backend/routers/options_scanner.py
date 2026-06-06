"""Options Buying Scanner — FastAPI router.

Endpoints:
  GET /api/options-scanner/scan          — Run full universe scan
  GET /api/options-scanner/deep-dive     — Single-symbol full MTF analysis
  GET /api/options-scanner/market-context— VIX, PCR, index trends
  GET /api/options-scanner/backtest      — Walk-forward backtest
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from backend.deps import run_sync

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/options-scanner", tags=["options-scanner"])

ROOT          = Path(__file__).resolve().parents[2]
UNIVERSE_DIR  = ROOT / "storage" / "universe"


# ── Universe helper ────────────────────────────────────────────────────────────

def _load_json_universe(filename: str) -> list[str]:
    try:
        path = UNIVERSE_DIR / filename
        if not path.exists():
            return []
        items = json.loads(path.read_text(encoding="utf-8"))
        out = []
        for item in items:
            sym = item.get("symbol") or item.get("ticker") or item.get("Symbol") or ""
            if sym:
                out.append(sym.strip().upper())
        return out
    except Exception:
        return []


def _get_universe(universe_filter: str) -> list[str]:
    indices = ["NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY"]

    if universe_filter == "indices_only":
        return indices

    # Load equities (may be large — cap at reasonable limit)
    from services.fno_data_service import get_fno_stocks
    try:
        fno_stocks  = get_fno_stocks()
        all_equities = [s["symbol"] for s in fno_stocks if s.get("symbol")]
    except Exception:
        all_equities = []

    universe_map: dict[str, tuple[list[str], str, int]] = {
        "nifty_50":   (["NIFTY"],              "NIFTY_50.json",        50),
        "nifty_100":  (["NIFTY","BANKNIFTY"],  "NIFTY_100.json",       100),
        "nifty_200":  (["NIFTY","BANKNIFTY"],  "NIFTY_200.json",       150),
        "nifty_bank": (["BANKNIFTY"],           "NIFTY_BANK.json",      30),
        "nifty_it":   ([],                      "NIFTY_IT.json",        20),
        "nifty_midcap": ([],                    "NIFTY_MIDCAP_150.json", 50),
    }

    if universe_filter in universe_map:
        forced_idx, fname, cap = universe_map[universe_filter]
        equities = _load_json_universe(fname)[:cap]
        combined = forced_idx + [e for e in equities if e not in forced_idx]
        return combined if combined else indices + all_equities[:cap]

    # Default: all — cap at 80 symbols to avoid timeout
    return indices + all_equities[:80]


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("/scan")
async def run_scan(
    universe:      str   = Query("nifty_50"),
    signal_filter: str   = Query("all"),          # all | ce_only | pe_only
    min_score:     int   = Query(70, ge=0, le=100),
    min_dte:       int   = Query(5, ge=1),
    max_iv_pct:    float = Query(60.0, ge=0, le=100),
    max_results:   int   = Query(30, ge=1, le=100),
) -> dict:
    """Run options buying scan across the selected universe."""

    def _run():
        sym_list = _get_universe(universe)
        if not sym_list:
            return {"results": [], "count": 0, "universe": universe, "scanned": 0}

        from services.options_buying_scanner import run_options_scan
        market_ctx = {"min_dte": min_dte, "max_iv_pct": max_iv_pct}

        results = run_options_scan(
            universe=sym_list,
            market_context=market_ctx,
            min_score=min_score,
            signal_filter=signal_filter,
            max_workers=3,
        )
        return {
            "results": results[:max_results],
            "count":   len(results),
            "scanned": len(sym_list),
            "universe": universe,
        }

    return await run_sync(_run)


@router.get("/deep-dive")
async def deep_dive(symbol: str = Query(...)) -> dict:
    """Full MTF deep-dive for a single symbol: MTF analysis + both CE/PE setups."""

    def _run():
        import math
        from services.mtf_analyzer import analyze_symbol_mtf
        from services.fno_data_service import (
            get_option_chain, get_fno_quote,
            get_synthetic_option_chain, LOT_SIZES, days_to_expiry,
        )
        from services.greeks_calculator import calculate_max_pain
        from services.options_buying_scanner import build_options_setup, result_to_dict

        sym   = symbol.upper()
        quote = get_fno_quote(sym)
        spot  = float(quote.get("ltp", 0) or quote.get("last", 0) or 0)

        try:
            df_chain, meta = get_option_chain(sym)
            if df_chain is None or df_chain.empty:
                df_chain, meta = get_synthetic_option_chain(sym)
        except Exception:
            df_chain, meta = get_synthetic_option_chain(sym)

        mtf = analyze_symbol_mtf(sym)

        def tf_dict(tf):
            if tf is None:
                return None
            return {
                "trend":          tf.trend,
                "ema20":          tf.ema20,
                "ema50":          tf.ema50,
                "ema200":         getattr(tf, "ema200", 0.0),
                "last_close":     tf.last_close,
                "adx":            tf.adx,
                "ema_aligned":    tf.ema_aligned,
                "ema_full_bull":  getattr(tf, "ema_full_bull", False),
                "ema_full_bear":  getattr(tf, "ema_full_bear", False),
                "structure":      tf.structure,
                "rsi":            tf.rsi,
                "obv_trend":      tf.obv_trend,
                "volume_signal":  tf.volume_signal,
                "patterns": [
                    {"name": p.name, "direction": p.direction,
                     "strength": p.strength, "description": p.description}
                    for p in (tf.patterns or [])
                ],
                "key_levels": [
                    {"price": kl.price, "type": kl.level_type,
                     "significance": kl.significance, "description": kl.description}
                    for kl in (tf.key_levels or [])
                ],
                "cpr": (
                    {"pivot": tf.cpr.pivot, "bc": tf.cpr.bc, "tc": tf.cpr.tc,
                     "width_pct": tf.cpr.width_pct,
                     "is_narrow": tf.cpr.is_narrow, "is_wide": tf.cpr.is_wide}
                    if tf.cpr else None
                ),
            }

        market_ctx = {"min_dte": 5, "max_iv_pct": 60.0}
        ce_setup = result_to_dict(build_options_setup(sym, spot, mtf, df_chain, market_ctx, "CE"))
        pe_setup = result_to_dict(build_options_setup(sym, spot, mtf, df_chain, market_ctx, "PE"))

        # Nearby option-chain rows for the UI
        oc_rows = []
        if df_chain is not None and not df_chain.empty and spot > 0:
            try:
                expiries = sorted(df_chain["expiry"].unique())
                if expiries:
                    near = df_chain[df_chain["expiry"] == expiries[0]]
                    strikes = sorted(near["strike"].unique())
                    atm = min(strikes, key=lambda s: abs(s - spot))
                    atm_idx = strikes.index(atm)
                    for s in strikes[max(0, atm_idx-3):atm_idx+4]:
                        row = near[near["strike"] == s].iloc[0]
                        oc_rows.append({
                            "strike":  s,
                            "ce_ltp":  _clean(row.get("CE_ltp", 0)),
                            "ce_iv":   _clean(row.get("CE_iv", 0)),
                            "ce_oi":   _clean(row.get("CE_oi", 0)),
                            "ce_vol":  _clean(row.get("CE_vol", 0)),
                            "pe_ltp":  _clean(row.get("PE_ltp", 0)),
                            "pe_iv":   _clean(row.get("PE_iv", 0)),
                            "pe_oi":   _clean(row.get("PE_oi", 0)),
                            "pe_vol":  _clean(row.get("PE_vol", 0)),
                        })
            except Exception:
                pass

        max_pain = 0
        try:
            if df_chain is not None and not df_chain.empty:
                expiries = sorted(df_chain["expiry"].unique())
                if expiries:
                    near = df_chain[df_chain["expiry"] == expiries[0]]
                    max_pain = calculate_max_pain(near)
        except Exception:
            pass

        pcr = {}
        try:
            from services.fno_data_service import get_pcr
            pcr = get_pcr(sym)
        except Exception:
            pass

        return {
            "symbol":    sym,
            "spot":      spot,
            "lot_size":  LOT_SIZES.get(sym, 50),
            "mtf": {
                "monthly":         tf_dict(mtf.monthly),
                "weekly":          tf_dict(mtf.weekly),
                "daily":           tf_dict(mtf.daily),
                "hourly":          tf_dict(mtf.hourly),
                "overall_trend":   mtf.overall_trend,
                "alignment_count": mtf.alignment_count,
            },
            "ce_setup":              ce_setup,
            "pe_setup":              pe_setup,
            "option_chain_summary":  oc_rows,
            "pcr":                   pcr,
            "max_pain":              max_pain,
            "timestamp":             mtf.timestamp,
        }

    return await run_sync(_run)


def _clean(v):
    import math
    if v is None:
        return 0
    try:
        f = float(v)
        return 0 if math.isnan(f) or math.isinf(f) else f
    except Exception:
        return 0


@router.get("/market-context")
async def market_context() -> dict:
    """VIX, PCR, NIFTY/BANKNIFTY spot + trend snapshot."""

    def _run():
        from services.fno_data_service import get_vix, get_pcr, _api_get

        vix = 0.0
        try:
            vd  = get_vix()
            vix = float(vd.get("vix", 0) or 0)
        except Exception:
            pass

        nifty_pcr = {}
        bank_pcr  = {}
        try:
            nifty_pcr = get_pcr("NIFTY")
        except Exception:
            pass
        try:
            bank_pcr = get_pcr("BANKNIFTY")
        except Exception:
            pass

        index_data: dict[str, dict] = {}
        try:
            raw = _api_get("/api/allIndices")
            if raw:
                for d in raw.get("data", []):
                    idx = d.get("index", "")
                    if idx == "NIFTY 50":
                        index_data["NIFTY"] = {
                            "spot": _clean(d.get("last")),
                            "change_pct": _clean(d.get("percentChange")),
                        }
                    elif idx == "NIFTY BANK":
                        index_data["BANKNIFTY"] = {
                            "spot": _clean(d.get("last")),
                            "change_pct": _clean(d.get("percentChange")),
                        }
        except Exception:
            pass

        vix_level = "low" if vix < 13 else ("high" if vix > 18 else "moderate")

        nifty_pcr_oi = _clean(nifty_pcr.get("pcr_oi", 0))
        bank_pcr_oi  = _clean(bank_pcr.get("pcr_oi", 0))

        return {
            "vix":       round(vix, 2),
            "vix_level": vix_level,
            "nifty": {
                "spot":       (index_data.get("NIFTY") or {}).get("spot", 0),
                "change_pct": (index_data.get("NIFTY") or {}).get("change_pct", 0),
                "pcr_oi":     nifty_pcr_oi,
                "pcr_signal": ("bullish" if nifty_pcr_oi < 0.8 else "bearish" if nifty_pcr_oi > 1.2 else "neutral"),
            },
            "banknifty": {
                "spot":       (index_data.get("BANKNIFTY") or {}).get("spot", 0),
                "change_pct": (index_data.get("BANKNIFTY") or {}).get("change_pct", 0),
                "pcr_oi":     bank_pcr_oi,
                "pcr_signal": ("bullish" if bank_pcr_oi < 0.8 else "bearish" if bank_pcr_oi > 1.2 else "neutral"),
            },
        }

    return await run_sync(_run)


@router.get("/backtest")
async def backtest_endpoint(
    symbol:        str = Query("NIFTY"),
    lookback_days: int = Query(90, ge=30, le=365),
    min_score:     int = Query(70, ge=50, le=100),
) -> dict:
    """Walk-forward backtest of the MT options buying strategy."""

    def _run():
        from services.options_backtest_mt import backtest_mt_strategy
        return backtest_mt_strategy(symbol.upper(), lookback_days, min_score)

    try:
        return await run_sync(_run)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
