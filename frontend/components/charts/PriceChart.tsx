"use client";
/**
 * Unified candlestick chart used by every page that displays price data:
 * Stock Analyzer, Pattern Lab, Scanner expand-rows, Reports preview, Backtest detail.
 *
 * Built on lightweight-charts (TradingView's open-source engine).
 * Supports: candlesticks, volume pane, EMA overlays, pattern trendlines,
 * Entry / Target / Stop horizontal lines, dark theme.
 */
import { useEffect, useRef } from "react";
import {
  createChart, ColorType, CrosshairMode, LineStyle,
  type IChartApi, type ISeriesApi, type Time, type UTCTimestamp,
} from "lightweight-charts";
import type { OHLCVBar, PatternHit } from "@/lib/types";

export interface PriceChartProps {
  bars: OHLCVBar[];
  patterns?: PatternHit[];
  emas?: number[];               // [20, 50, 200]
  entry?: number | null;
  target?: number | null;
  stop?: number | null;
  height?: number;
  showVolume?: boolean;
}

const EMA_COLORS: Record<number, string> = {
  20:  "#f5c542",   // yellow
  50:  "#818cf8",   // accent
  100: "#94a3b8",   // muted
  200: "#26a69a",   // teal
};

function calcEMA(closes: number[], period: number): (number | null)[] {
  const k = 2 / (period + 1);
  const out: (number | null)[] = [];
  let ema: number | null = null;
  for (let i = 0; i < closes.length; i++) {
    const c = closes[i];
    if (i + 1 < period) { out.push(null); continue; }
    if (ema === null) {
      const slice = closes.slice(0, period);
      ema = slice.reduce((s, x) => s + x, 0) / period;
    } else {
      ema = c * k + ema * (1 - k);
    }
    out.push(ema);
  }
  return out;
}

export function PriceChart({
  bars, patterns = [], emas = [20, 50, 200],
  entry = null, target = null, stop = null,
  height = 500, showVolume = true,
}: PriceChartProps) {
  const ref = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);

  useEffect(() => {
    if (!ref.current || bars.length === 0) return;

    const chart = createChart(ref.current, {
      height,
      layout: {
        background: { type: ColorType.Solid, color: "#0b0e14" },
        textColor: "#94a3b8",
        fontFamily: "ui-sans-serif, system-ui, sans-serif",
      },
      grid: {
        vertLines: { color: "#1a2030" },
        horzLines: { color: "#1a2030" },
      },
      crosshair: { mode: CrosshairMode.Magnet },
      rightPriceScale: { borderColor: "#232a3a", scaleMargins: { top: 0.05, bottom: showVolume ? 0.25 : 0.05 } },
      timeScale: { borderColor: "#232a3a", timeVisible: true, secondsVisible: false },
      autoSize: true,
      handleScroll: true,
      handleScale: true,
    });
    chartRef.current = chart;

    const candles: ISeriesApi<"Candlestick"> = chart.addCandlestickSeries({
      upColor: "#1ec48a", downColor: "#ef5350",
      wickUpColor: "#1ec48a", wickDownColor: "#ef5350",
      borderVisible: false,
    });
    candles.setData(bars.map((b) => ({
      time: b.time as UTCTimestamp,
      open: b.open, high: b.high, low: b.low, close: b.close,
    })));

    if (showVolume) {
      const vol = chart.addHistogramSeries({
        color: "#26a69a55",
        priceFormat: { type: "volume" },
        priceScaleId: "vol",
      });
      chart.priceScale("vol").applyOptions({ scaleMargins: { top: 0.85, bottom: 0 } });
      vol.setData(bars.map((b) => ({
        time: b.time as UTCTimestamp,
        value: b.volume ?? 0,
        color: b.close >= b.open ? "#1ec48a55" : "#ef535055",
      })));
    }

    // EMAs
    const closes = bars.map((b) => b.close);
    for (const period of emas) {
      const series = chart.addLineSeries({
        color: EMA_COLORS[period] || "#94a3b8",
        lineWidth: 1, lastValueVisible: false, priceLineVisible: false,
        title: `EMA ${period}`,
      });
      const data = calcEMA(closes, period)
        .map((v, i) => v === null ? null : { time: bars[i].time as UTCTimestamp, value: v })
        .filter((x): x is { time: UTCTimestamp; value: number } => x !== null);
      series.setData(data);
    }

    // Entry / Target / Stop horizontal lines
    const drawLevel = (price: number, color: string, label: string) => {
      candles.createPriceLine({
        price, color, lineWidth: 2, lineStyle: LineStyle.Dashed,
        axisLabelVisible: true, title: label,
      });
    };
    if (entry !== null && entry !== undefined) drawLevel(entry, "#818cf8", `Entry ${entry.toFixed(2)}`);
    if (target !== null && target !== undefined) drawLevel(target, "#1ec48a", `Target ${target.toFixed(2)}`);
    if (stop !== null && stop !== undefined) drawLevel(stop, "#ef5350", `Stop ${stop.toFixed(2)}`);

    // Pattern trendlines — engine emits {x0,x1} as date strings ("2024-12-09")
    // OR as bar indices, depending on the detector. Convert both to UTC seconds.
    const firstBarT = bars[0]?.time ?? 0;
    const lastBarT = bars[bars.length - 1]?.time ?? 0;
    const dateToTime = (v: unknown): UTCTimestamp | null => {
      if (typeof v === "number") {
        // Treat as bar index if it falls inside the bar count
        if (Number.isInteger(v) && v >= 0 && v < bars.length) return bars[v].time as UTCTimestamp;
        // Otherwise assume it's already a UTC seconds timestamp
        return v as UTCTimestamp;
      }
      if (typeof v === "string") {
        const ms = Date.parse(v);
        if (Number.isNaN(ms)) return null;
        const t = Math.floor(ms / 1000) as UTCTimestamp;
        // Clamp to chart range so off-screen points still anchor at the edge
        if (t < firstBarT) return firstBarT as UTCTimestamp;
        if (t > lastBarT) return lastBarT as UTCTimestamp;
        return t;
      }
      return null;
    };

    for (const p of patterns) {
      // Trendlines
      for (const line of p.lines ?? []) {
        const l = line as { x0?: unknown; y0?: number; x1?: unknown; y1?: number; color?: string; dash?: string };
        const t0 = dateToTime(l.x0);
        const t1 = dateToTime(l.x1);
        if (t0 === null || t1 === null || typeof l.y0 !== "number" || typeof l.y1 !== "number") continue;
        const trendline = chart.addLineSeries({
          color: l.color || "#f5c542",
          lineWidth: 2,
          lineStyle: l.dash === "dot" ? LineStyle.Dotted : LineStyle.Dashed,
          lastValueVisible: false, priceLineVisible: false,
        });
        trendline.setData([
          { time: t0 as Time, value: l.y0 },
          { time: t1 as Time, value: l.y1 },
        ] as { time: Time; value: number }[]);
      }
      // Pattern key-level horizontal lines
      if (p.target)     drawLevel(p.target,     "#1ec48a", `${p.name} T`);
      if (p.stop)       drawLevel(p.stop,       "#ef5350", `${p.name} SL`);
      if (p.support)    drawLevel(p.support,    "#26a69a55", `${p.name} S`);
      if (p.resistance) drawLevel(p.resistance, "#ef535055", `${p.name} R`);
    }

    chart.timeScale().fitContent();

    return () => {
      chart.remove();
      chartRef.current = null;
    };
  }, [bars, patterns, emas, entry, target, stop, height, showVolume]);

  if (bars.length === 0) {
    return (
      <div className="grid place-items-center text-[var(--color-text-muted)] text-sm" style={{ height }}>
        No data
      </div>
    );
  }
  return <div ref={ref} className="w-full rounded-md overflow-hidden" style={{ height }} />;
}
