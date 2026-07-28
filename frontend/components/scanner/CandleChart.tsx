"use client";

import { useEffect, useRef, useState } from "react";
import { RefreshCw } from "lucide-react";

interface Candle {
  time:  string | number;
  open:  number;
  high:  number;
  low:   number;
  close: number;
}

interface Props {
  symbol:    string;
  interval:  string;
  pattern:   string;
  direction: "bullish" | "bearish" | "range";
  height?:   number;   // default 360
  bars?:     number;   // default 120
}

// ── Pattern marker spans ──────────────────────────────────────────────────────
const PATTERN_BARS: Record<string, number> = {
  "Morning Star":          3,
  "Evening Star":          3,
  "Inside Bar Breakout":   3,
  "Inside Bar Breakdown":  3,
  "Bullish Engulfing":     2,
  "Bearish Engulfing":     2,
  "Hammer / Pin Bar":      1,
  "Shooting Star":         1,
  "Bullish Marubozu":      1,
  "Bearish Marubozu":      1,
};

// ── Technical calculations ────────────────────────────────────────────────────

/** Exponential moving average; NaN before period warmup. */
function computeEma(closes: number[], period: number): number[] {
  const k   = 2 / (period + 1);
  const out = new Array<number>(closes.length).fill(NaN);
  if (closes.length < period) return out;
  let val = closes.slice(0, period).reduce((a, b) => a + b, 0) / period;
  out[period - 1] = val;
  for (let i = period; i < closes.length; i++) {
    val = closes[i] * k + val * (1 - k);
    out[i] = val;
  }
  return out;
}

/** Average true range over the last `period` bars. */
function computeAtr(candles: Candle[], period = 14): number {
  const trs: number[] = [];
  for (let i = 1; i < candles.length; i++) {
    const prev = candles[i - 1].close;
    trs.push(Math.max(
      candles[i].high - candles[i].low,
      Math.abs(candles[i].high - prev),
      Math.abs(candles[i].low  - prev),
    ));
  }
  const recent = trs.slice(-period);
  return recent.length ? recent.reduce((a, b) => a + b, 0) / recent.length : 0;
}

interface SwingPt { idx: number; price: number; time: string | number }

/**
 * Find pivot highs and lows.
 * Strict: a swing high requires candle.high > ALL neighbours within `lookback`.
 * Then applies a minimum spacing filter so adjacent pivots aren't too close.
 */
function findSwings(
  candles:       Candle[],
  lookback  = 4,
  minSpacing = 6,   // bars of separation between two accepted pivots
): { highs: SwingPt[]; lows: SwingPt[] } {
  const rawHighs: SwingPt[] = [];
  const rawLows:  SwingPt[] = [];

  for (let i = lookback; i < candles.length - lookback; i++) {
    const h = candles[i].high;
    const l = candles[i].low;
    let isH = true, isL = true;

    for (let j = i - lookback; j <= i + lookback && (isH || isL); j++) {
      if (j === i) continue;
      if (candles[j].high >= h) isH = false;
      if (candles[j].low  <= l) isL = false;
    }
    if (isH) rawHighs.push({ idx: i, price: h, time: candles[i].time });
    if (isL) rawLows .push({ idx: i, price: l, time: candles[i].time });
  }

  // Enforce minimum spacing between accepted pivots
  const filter = (pts: SwingPt[]): SwingPt[] => {
    const out: SwingPt[] = [];
    for (const p of pts) {
      if (!out.length || p.idx - out[out.length - 1].idx >= minSpacing) {
        out.push(p);
      }
    }
    return out;
  };

  return { highs: filter(rawHighs), lows: filter(rawLows) };
}

/**
 * Build trendline data from p1 (older) → p2 (newer), extended to last candle.
 * Returns empty array if the two points are too close or the slope is degenerate.
 */
function buildTrendline(
  candles:     Candle[],
  p1:          SwingPt,
  p2:          SwingPt,
  minSpan = 8,
): { time: string | number; value: number }[] {
  if (p2.idx - p1.idx < minSpan) return [];
  const slope = (p2.price - p1.price) / (p2.idx - p1.idx);
  return candles.slice(p1.idx).map((c, i) => ({
    time:  c.time,
    value: parseFloat((p1.price + slope * i).toFixed(4)),
  }));
}

// ── Component ─────────────────────────────────────────────────────────────────

export function CandleChart({
  symbol,
  interval,
  pattern,
  direction,
  height = 360,
  bars   = 120,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef     = useRef<any>(null);
  const [status, setStatus] = useState<"loading" | "ok" | "empty" | "error">("loading");

  useEffect(() => {
    if (!containerRef.current) return;
    let destroyed = false;

    const init = async () => {
      try {
        const { createChart, ColorType, CrosshairMode, LineStyle } =
          await import("lightweight-charts");
        if (destroyed || !containerRef.current) return;

        const chart = createChart(containerRef.current, {
          width:  containerRef.current.clientWidth || 700,
          height,
          layout: {
            background: { type: ColorType.Solid, color: "transparent" },
            textColor:  "rgba(255,255,255,0.45)",
            fontSize:   11,
          },
          grid: {
            vertLines: { color: "rgba(255,255,255,0.04)" },
            horzLines: { color: "rgba(255,255,255,0.04)" },
          },
          crosshair: { mode: CrosshairMode.Normal },
          rightPriceScale: {
            borderColor:  "rgba(255,255,255,0.12)",
            textColor:    "rgba(255,255,255,0.45)",
            scaleMargins: { top: 0.10, bottom: 0.10 },
          },
          timeScale: {
            borderColor:    "rgba(255,255,255,0.12)",
            timeVisible:    !["1d", "1wk", "1mo"].includes(interval),
            secondsVisible: false,
          },
          handleScroll: true,
          handleScale:  true,
        });
        chartRef.current = chart;

        // ── Candlestick series ────────────────────────────────────────────
        const candleSeries = chart.addCandlestickSeries({
          upColor:         "#10b981",
          downColor:       "#ef4444",
          borderUpColor:   "#10b981",
          borderDownColor: "#ef4444",
          wickUpColor:     "#10b981",
          wickDownColor:   "#ef4444",
        });

        // ── Fetch data ────────────────────────────────────────────────────
        const res = await fetch(
          `/api/equity-scanner/chart-data?symbol=${encodeURIComponent(symbol)}&interval=${interval}&bars=${bars}`,
        );
        if (destroyed) return;
        if (!res.ok) { setStatus("error"); return; }

        const data: { candles: Candle[] } = await res.json();
        if (!data.candles?.length) { setStatus("empty"); return; }

        const candles = data.candles;
        candleSeries.setData(candles as any);

        const closes = candles.map(c => c.close);
        const atr    = computeAtr(candles);

        // ── EMA 20 ────────────────────────────────────────────────────────
        const ema20Vals = computeEma(closes, 20);
        const ema20Data = candles
          .map((c, i) => ({ time: c.time, value: ema20Vals[i] }))
          .filter(p => !isNaN(p.value));

        if (ema20Data.length >= 2) {
          const emaSeries = chart.addLineSeries({
            color:                  "rgba(239,68,68,0.85)",
            lineWidth:              2,
            crosshairMarkerVisible: false,
            priceLineVisible:       false,
            lastValueVisible:       true,
          });
          emaSeries.setData(ema20Data as any);
        }

        // ── Swing-point detection ─────────────────────────────────────────
        const { highs, lows } = findSwings(candles, 4, 6);

        // Take the two most recent swing highs with enough separation for a trendline
        const recentHighs = highs.slice(-6).reverse();
        const recentLows  = lows .slice(-6).reverse();

        // Resistance trendline — through the last two valid swing highs
        let drewResistance = false;
        for (let i = 0; i < recentHighs.length - 1 && !drewResistance; i++) {
          const p2 = recentHighs[i];       // more recent
          const p1 = recentHighs[i + 1];   // older
          const pts = buildTrendline(candles, p1, p2, 8);
          if (!pts.length) continue;

          const tlSeries = chart.addLineSeries({
            color:                  "rgba(255,255,255,0.75)",
            lineWidth:              2,
            lineStyle:              LineStyle.Solid,
            crosshairMarkerVisible: false,
            priceLineVisible:       false,
            lastValueVisible:       false,
          });
          tlSeries.setData(pts as any);
          drewResistance = true;
        }

        // Support trendline — through the last two valid swing lows
        let drewSupport = false;
        for (let i = 0; i < recentLows.length - 1 && !drewSupport; i++) {
          const p2 = recentLows[i];
          const p1 = recentLows[i + 1];
          const pts = buildTrendline(candles, p1, p2, 8);
          if (!pts.length) continue;

          const tlSeries = chart.addLineSeries({
            color:                  "rgba(255,255,255,0.75)",
            lineWidth:              2,
            lineStyle:              LineStyle.Solid,
            crosshairMarkerVisible: false,
            priceLineVisible:       false,
            lastValueVisible:       false,
          });
          tlSeries.setData(pts as any);
          drewSupport = true;
        }

        // ── Horizontal S/R price lines ────────────────────────────────────
        // Top 2 recent swing highs → dashed red resistance rays
        const lastClose = closes[closes.length - 1];

        for (const h of recentHighs.slice(0, 3)) {
          const dist = Math.abs(h.price - lastClose) / lastClose;
          if (dist < 0.002) continue;   // skip if at current price
          candleSeries.createPriceLine({
            price:            h.price,
            color:            "rgba(239,68,68,0.50)",
            lineWidth:        1,
            lineStyle:        LineStyle.Dashed,
            axisLabelVisible: true,
            title:            "R",
          } as any);
          break; // one resistance ray is enough
        }

        for (const l of recentLows.slice(0, 3)) {
          const dist = Math.abs(l.price - lastClose) / lastClose;
          if (dist < 0.002) continue;
          candleSeries.createPriceLine({
            price:            l.price,
            color:            "rgba(16,185,129,0.50)",
            lineWidth:        1,
            lineStyle:        LineStyle.Dashed,
            axisLabelVisible: true,
            title:            "S",
          } as any);
          break;
        }

        // ── Pattern markers ───────────────────────────────────────────────
        const spanBars = PATTERN_BARS[pattern] ?? 1;
        const isBull   = direction === "bullish";
        const markers  = candles.slice(-spanBars).map((c, i) => ({
          time:     c.time,
          position: isBull ? "belowBar" : "aboveBar",
          color:    "#fbbf24",
          shape:    isBull ? "arrowUp" : "arrowDown",
          text:     i === spanBars - 1 ? pattern : "",
          size:     2,
        }));
        candleSeries.setMarkers(markers as any);

        chart.timeScale().fitContent();
        if (destroyed || !containerRef.current) return;
        setStatus("ok");

        const ro = new ResizeObserver(() => {
          if (containerRef.current && !destroyed)
            chart.applyOptions({ width: containerRef.current.clientWidth });
        });
        ro.observe(containerRef.current);
        return () => ro.disconnect();

      } catch (err) {
        console.error("CandleChart error:", err);
        if (!destroyed) setStatus("error");
      }
    };

    init();
    return () => {
      destroyed = true;
      chartRef.current?.remove();
      chartRef.current = null;
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [symbol, interval, height, bars]);

  return (
    <div className="relative w-full">
      {/* Loading */}
      {status === "loading" && (
        <div
          className="flex items-center justify-center bg-[var(--color-surface)] rounded"
          style={{ height }}
        >
          <RefreshCw className="size-5 text-white/20 animate-spin" />
        </div>
      )}
      {/* Empty */}
      {status === "empty" && (
        <div
          className="flex items-center justify-center text-[11px] text-white/25"
          style={{ height }}
        >
          No chart data for {symbol}/{interval}
        </div>
      )}
      {/* Error */}
      {status === "error" && (
        <div
          className="flex items-center justify-center text-[11px] text-red-400/50"
          style={{ height }}
        >
          Chart unavailable
        </div>
      )}

      {/* Legend overlay */}
      {status === "ok" && (
        <div className="absolute top-2 left-3 flex items-center gap-3 text-[9px] text-white/35 pointer-events-none z-10">
          <span className="flex items-center gap-1">
            <span className="inline-block w-4 h-0.5 bg-red-400/80 rounded" />
            EMA 20
          </span>
          <span className="flex items-center gap-1">
            <span className="inline-block w-4 h-0.5 bg-white/70 rounded" />
            Trendline
          </span>
          <span className="flex items-center gap-1">
            <span className="inline-block w-4 h-px border-t border-dashed border-red-400/50" />
            Resistance
          </span>
          <span className="flex items-center gap-1">
            <span className="inline-block w-4 h-px border-t border-dashed border-emerald-400/50" />
            Support
          </span>
        </div>
      )}

      <div
        ref={containerRef}
        className={status === "ok" ? "w-full" : "w-full opacity-0 h-0 overflow-hidden"}
      />
    </div>
  );
}
