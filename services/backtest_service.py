"""
Pattern-based backtesting engine.

Strategy-first design: pick a chart pattern (e.g. "Cup & Handle"), the engine
scans historical OHLCV across the entire universe (or a subset), finds every
historical occurrence of that pattern, simulates a trade, and reports
aggregate stats — win rate, avg return, holding period, max drawdown,
equity curve.

Public API:
  - run_pattern_backtest(symbols, pattern_name, params) -> BacktestResult
  - PATTERN_CATEGORIES (re-exported)
  - ALL_PATTERN_NAMES (re-exported)
"""
from __future__ import annotations
import logging
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd

from engines.pattern_engine import detect_patterns, PATTERN_CATEGORIES, ALL_PATTERN_NAMES
from services.market_data_service import get_ohlcv_history

logger = logging.getLogger(__name__)


@dataclass
class Trade:
    symbol: str
    pattern: str
    direction: str            # bullish/bearish
    entry_date: str
    entry_price: float
    exit_date: str
    exit_price: float
    holding_days: int
    return_pct: float
    outcome: str              # WIN / LOSS / NEUTRAL
    confidence: int
    target: Optional[float]
    stop: Optional[float]
    exit_reason: str          # "target hit" / "stop hit" / "time stop" / "end of data"


@dataclass
class BacktestResult:
    pattern: str
    universe_size: int
    symbols_with_patterns: int
    total_trades: int
    winners: int
    losers: int
    neutrals: int
    win_rate: float
    avg_return_pct: float
    avg_winner_pct: float
    avg_loser_pct: float
    max_winner_pct: float
    max_loser_pct: float
    avg_holding_days: float
    expectancy: float          # (win_rate * avg_winner) + (loss_rate * avg_loser)
    profit_factor: float       # sum(wins) / |sum(losses)|
    max_drawdown_pct: float
    equity_curve: List[float]
    trades: List[Dict] = field(default_factory=list)
    audit: List[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        d = asdict(self)
        return d


# ─────────────────────────────────────────────────────────────────────────────
# Trade simulator
# ─────────────────────────────────────────────────────────────────────────────
def _simulate_trade(df_full: pd.DataFrame, entry_idx: int, pattern: dict,
                    max_holding: int = 60, default_target_pct: float = 8.0,
                    default_stop_pct: float = 4.0) -> Optional[Trade]:
    """
    Simulate one trade entered at the close of `entry_idx`.
    Exit conditions (whichever fires first):
      - target hit
      - stop hit
      - max_holding bars elapsed
      - end of data
    """
    if entry_idx >= len(df_full) - 1:
        return None

    # Engine emits 'Bullish' / 'Bearish' / 'Neutral' — normalise to lowercase.
    direction = (pattern.get("direction") or "bullish").strip().lower()
    entry_price = float(df_full["Close"].iloc[entry_idx])
    entry_date  = df_full.index[entry_idx]

    kl = pattern.get("key_levels") or {}
    target = kl.get("target")
    stop   = kl.get("stop")

    # Fallback levels if pattern didn't specify
    if direction == "bullish":
        if not target: target = entry_price * (1 + default_target_pct / 100)
        if not stop:   stop   = entry_price * (1 - default_stop_pct / 100)
    else:  # bearish — short trade simulated as inverse
        if not target: target = entry_price * (1 - default_target_pct / 100)
        if not stop:   stop   = entry_price * (1 + default_stop_pct / 100)

    exit_idx = None
    exit_price = None
    exit_reason = "end of data"

    for j in range(entry_idx + 1, min(entry_idx + 1 + max_holding, len(df_full))):
        hi = float(df_full["High"].iloc[j])
        lo = float(df_full["Low"].iloc[j])
        if direction == "bullish":
            if lo <= stop:
                exit_idx, exit_price, exit_reason = j, stop, "stop hit"
                break
            if hi >= target:
                exit_idx, exit_price, exit_reason = j, target, "target hit"
                break
        else:
            if hi >= stop:
                exit_idx, exit_price, exit_reason = j, stop, "stop hit"
                break
            if lo <= target:
                exit_idx, exit_price, exit_reason = j, target, "target hit"
                break
    if exit_idx is None:
        # Exit at end of holding window or end-of-data, whichever first
        exit_idx = min(entry_idx + max_holding, len(df_full) - 1)
        exit_price = float(df_full["Close"].iloc[exit_idx])
        exit_reason = "time stop" if exit_idx == entry_idx + max_holding else "end of data"

    holding = exit_idx - entry_idx
    if direction == "bullish":
        ret_pct = (exit_price - entry_price) / entry_price * 100
    else:
        ret_pct = (entry_price - exit_price) / entry_price * 100

    if ret_pct > 0.5:    outcome = "WIN"
    elif ret_pct < -0.5: outcome = "LOSS"
    else:                outcome = "NEUTRAL"

    return Trade(
        symbol=pattern.get("_symbol", "?"),
        pattern=pattern.get("name", "?"),
        direction=direction,
        entry_date=str(entry_date.date() if hasattr(entry_date, "date") else entry_date)[:10],
        entry_price=round(entry_price, 2),
        exit_date=str(df_full.index[exit_idx].date() if hasattr(df_full.index[exit_idx], "date") else df_full.index[exit_idx])[:10],
        exit_price=round(exit_price, 2),
        holding_days=holding,
        return_pct=round(ret_pct, 2),
        outcome=outcome,
        confidence=pattern.get("confidence", 0),
        target=round(target, 2),
        stop=round(stop, 2),
        exit_reason=exit_reason,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Per-symbol historical sweep
# ─────────────────────────────────────────────────────────────────────────────
def _scan_symbol(symbol: str, pattern_name: str, period: str,
                 window: int, step: int, min_confidence: int,
                 max_holding: int) -> List[Trade]:
    """
    Walk forward through historical OHLCV. Every `step` bars, run pattern
    detection on the trailing `window` bars; for each detected occurrence of
    `pattern_name`, simulate the trade.
    """
    df = get_ohlcv_history(symbol, period=period, interval="1d")
    if df is None or len(df) < window + 30:
        return []

    trades: List[Trade] = []
    seen_signatures = set()  # avoid double-counting overlapping detections

    for end_idx in range(window, len(df) - 1, step):
        sub = df.iloc[end_idx - window: end_idx]
        try:
            pats = detect_patterns(sub)
        except Exception:
            continue
        for p in pats:
            if p.get("name") != pattern_name:
                continue
            if p.get("confidence", 0) < min_confidence:
                continue
            # Signature = symbol + pattern + entry bar (rounded to step)
            sig = (symbol, p.get("name"), end_idx // step)
            if sig in seen_signatures:
                continue
            seen_signatures.add(sig)
            p["_symbol"] = symbol
            t = _simulate_trade(df, entry_idx=end_idx, pattern=p,
                                max_holding=max_holding)
            if t:
                trades.append(t)
    return trades


# ─────────────────────────────────────────────────────────────────────────────
# Aggregate stats
# ─────────────────────────────────────────────────────────────────────────────
def _aggregate(trades: List[Trade], pattern_name: str, universe_size: int,
                symbols_with_patterns: int, audit: List[str]) -> BacktestResult:
    if not trades:
        return BacktestResult(pattern=pattern_name, universe_size=universe_size,
                              symbols_with_patterns=symbols_with_patterns,
                              total_trades=0, winners=0, losers=0, neutrals=0,
                              win_rate=0, avg_return_pct=0, avg_winner_pct=0,
                              avg_loser_pct=0, max_winner_pct=0, max_loser_pct=0,
                              avg_holding_days=0, expectancy=0, profit_factor=0,
                              max_drawdown_pct=0, equity_curve=[], trades=[], audit=audit)

    wins = [t for t in trades if t.outcome == "WIN"]
    losses = [t for t in trades if t.outcome == "LOSS"]
    neutrals = [t for t in trades if t.outcome == "NEUTRAL"]

    win_rate = len(wins) / len(trades) * 100
    avg_ret  = sum(t.return_pct for t in trades) / len(trades)
    avg_win  = (sum(t.return_pct for t in wins) / len(wins)) if wins else 0
    avg_loss = (sum(t.return_pct for t in losses) / len(losses)) if losses else 0
    max_win  = max((t.return_pct for t in wins), default=0)
    max_loss = min((t.return_pct for t in losses), default=0)
    avg_hold = sum(t.holding_days for t in trades) / len(trades)
    expectancy = (win_rate / 100 * avg_win) + ((1 - win_rate / 100) * avg_loss)
    sum_wins = sum(t.return_pct for t in wins) or 0
    sum_loss = abs(sum(t.return_pct for t in losses)) or 0.0001
    profit_factor = sum_wins / sum_loss

    # Equity curve (sequential trades, 1% bet sizing)
    sorted_trades = sorted(trades, key=lambda t: t.entry_date)
    equity = [100.0]
    peak = 100.0
    max_dd = 0.0
    for t in sorted_trades:
        equity.append(equity[-1] * (1 + t.return_pct / 100))
        peak = max(peak, equity[-1])
        dd = (peak - equity[-1]) / peak * 100
        max_dd = max(max_dd, dd)

    return BacktestResult(
        pattern=pattern_name,
        universe_size=universe_size,
        symbols_with_patterns=symbols_with_patterns,
        total_trades=len(trades),
        winners=len(wins), losers=len(losses), neutrals=len(neutrals),
        win_rate=round(win_rate, 2),
        avg_return_pct=round(avg_ret, 2),
        avg_winner_pct=round(avg_win, 2),
        avg_loser_pct=round(avg_loss, 2),
        max_winner_pct=round(max_win, 2),
        max_loser_pct=round(max_loss, 2),
        avg_holding_days=round(avg_hold, 1),
        expectancy=round(expectancy, 2),
        profit_factor=round(profit_factor, 2),
        max_drawdown_pct=round(max_dd, 2),
        equity_curve=[round(x, 2) for x in equity],
        trades=[asdict(t) for t in sorted_trades],
        audit=audit,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────────────────────
def run_pattern_backtest(
    symbols: List[str],
    pattern_name: str,
    period: str = "5y",
    window: int = 120,
    step: int = 10,
    min_confidence: int = 60,
    max_holding: int = 60,
    max_workers: int = 6,
    progress_cb=None,
) -> BacktestResult:
    """
    Backtest a single chart pattern across a universe of symbols.

    Args:
        symbols: list of NSE symbols
        pattern_name: must be one of ALL_PATTERN_NAMES
        period: lookback window per symbol ("1y", "2y", "5y", "max")
        window: bars used per detection call (rolling window size)
        step: bars between detection calls (overlap control)
        min_confidence: ignore detections below this confidence
        max_holding: bars to hold each trade before time-stop
        progress_cb: optional callback fn(done, total, current_symbol)
    """
    audit = [f"=== Backtest: {pattern_name} ===",
             f"Universe: {len(symbols)} symbols · period={period} · window={window} bars · step={step}",
             f"Min confidence: {min_confidence}%  ·  Max holding: {max_holding} bars"]

    all_trades: List[Trade] = []
    syms_with_pats = 0

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = {ex.submit(_scan_symbol, s, pattern_name, period, window, step,
                          min_confidence, max_holding): s for s in symbols}
        done = 0
        for f in as_completed(futs):
            sym = futs[f]
            try:
                ts = f.result()
                if ts:
                    all_trades.extend(ts)
                    syms_with_pats += 1
                    audit.append(f"  ✓ {sym}: {len(ts)} occurrences")
            except Exception as e:
                audit.append(f"  ✗ {sym}: {e}")
            done += 1
            if progress_cb:
                try: progress_cb(done, len(symbols), sym)
                except Exception: pass

    audit.append(f"--- Aggregating {len(all_trades)} trades from {syms_with_pats} symbols ---")
    return _aggregate(all_trades, pattern_name, len(symbols), syms_with_pats, audit)


# Re-exports for the page
__all__ = [
    "run_pattern_backtest", "BacktestResult", "Trade",
    "PATTERN_CATEGORIES", "ALL_PATTERN_NAMES",
]
