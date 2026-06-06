"use client";

import { useState, useMemo } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { getFnoSymbols, getFnoAiSuggestion, addPaperTrade } from "@/lib/fno-api";
import type { FNOSuggestion, TradeRecommendation } from "@/lib/fno-types";
import { getLotSize, INDEX_SYMBOLS } from "@/lib/fno-types";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { cn, formatINR } from "@/lib/utils";
import { Cpu, AlertTriangle, CheckCircle2, ChevronDown, ChevronUp, RefreshCw } from "lucide-react";

// ── Helpers ───────────────────────────────────────────────────────────────────

function confidenceBadge(c: string | undefined) {
  if (c === "HIGH") return <Badge variant="success">HIGH</Badge>;
  if (c === "LOW")  return <Badge variant="danger">LOW</Badge>;
  return <Badge variant="default">MEDIUM</Badge>;
}

function biasBadge(bias: string | undefined) {
  if (bias === "BULLISH")  return <Badge variant="success">BULLISH</Badge>;
  if (bias === "BEARISH")  return <Badge variant="danger">BEARISH</Badge>;
  if (bias === "SIDEWAYS") return <Badge variant="default">SIDEWAYS</Badge>;
  if (bias === "VOLATILE") return <Badge variant="info">VOLATILE</Badge>;
  return <Badge variant="default">NEUTRAL</Badge>;
}

function signalBadge(signal: string | undefined) {
  if (!signal) return null;
  if (signal.includes("STRONG_BUY_CE")) return <Badge variant="success">🚀 STRONG BUY CE</Badge>;
  if (signal.includes("BUY_CE"))        return <Badge variant="success">📈 BUY CE</Badge>;
  if (signal.includes("WATCH_CE"))      return <Badge variant="info">👀 WATCH CE</Badge>;
  if (signal.includes("STRONG_BUY_PE")) return <Badge variant="danger">🔻 STRONG BUY PE</Badge>;
  if (signal.includes("BUY_PE"))        return <Badge variant="danger">📉 BUY PE</Badge>;
  if (signal.includes("WATCH_PE"))      return <Badge variant="info">👀 WATCH PE</Badge>;
  return <Badge variant="default">⛔ NO TRADE</Badge>;
}

function ScoreRing({ score }: { score: number }) {
  const r    = 22;
  const circ = 2 * Math.PI * r;
  const dash = (Math.min(100, score) / 100) * circ;
  const color = score >= 85 ? "var(--color-success)" : score >= 70 ? "#22c55e" : "#f5c542";
  return (
    <div className="relative inline-flex items-center justify-center shrink-0">
      <svg width="56" height="56">
        <circle cx="28" cy="28" r={r} fill="none" stroke="var(--color-surface-2)" strokeWidth="5" />
        <circle cx="28" cy="28" r={r} fill="none"
          stroke={color} strokeWidth="5"
          strokeDasharray={`${dash} ${circ - dash}`}
          strokeLinecap="round"
          transform="rotate(-90 28 28)"
        />
      </svg>
      <span className="absolute text-xs font-bold" style={{ color }}>{score}</span>
    </div>
  );
}

// ── Trade Card ────────────────────────────────────────────────────────────────

function TradeCard({
  trade,
  symbol,
  onAddToPaper,
  adding,
}: {
  trade: TradeRecommendation;
  symbol: string;
  onAddToPaper: (t: TradeRecommendation) => void;
  adding: boolean;
}) {
  const isBuy = trade.action === "BUY";
  return (
    <div className={cn(
      "rounded-lg border p-4 space-y-3",
      isBuy
        ? "border-[var(--color-success)]/40 bg-[var(--color-success)]/5"
        : "border-[var(--color-danger)]/40 bg-[var(--color-danger)]/5",
    )}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className={cn("text-sm font-bold", isBuy ? "text-[var(--color-success)]" : "text-[var(--color-danger)]")}>
            {trade.action}
          </span>
          <span className="text-white text-sm font-medium">
            {symbol} {trade.strike > 0 ? `${trade.strike} ` : ""}{trade.instrument}
          </span>
        </div>
        {confidenceBadge(trade.confidence)}
      </div>

      {trade.strategy_name && (
        <div className="text-[11px] text-[var(--color-text-muted)] font-medium uppercase tracking-wide">
          {trade.strategy_name}
        </div>
      )}

      <div className="grid grid-cols-3 gap-3 text-xs tnum">
        <div>
          <div className="text-[var(--color-text-muted)]">Entry</div>
          <div className="text-white font-medium">{formatINR(trade.entry_price)}</div>
        </div>
        <div>
          <div className="text-[var(--color-text-muted)]">T1 (book 50%)</div>
          <div className="up font-medium">{formatINR(trade.target_1 || trade.target_price)}</div>
        </div>
        <div>
          <div className="text-[var(--color-text-muted)]">T2 (trail rest)</div>
          <div className="up font-medium">{formatINR(trade.target_2 || (trade.target_price * 1.5))}</div>
        </div>
        <div>
          <div className="text-[var(--color-text-muted)]">Stop Loss</div>
          <div className="down font-medium">{formatINR(trade.stop_loss)}</div>
        </div>
        <div>
          <div className="text-[var(--color-text-muted)]">Max Loss</div>
          <div className="down font-medium">{formatINR(trade.max_loss_rs)}</div>
        </div>
        <div>
          <div className="text-[var(--color-text-muted)]">R:R</div>
          <div className={cn("font-medium", trade.reward_risk_ratio >= 2 ? "up" : "text-yellow-400")}>
            {trade.reward_risk_ratio?.toFixed(2)}×
          </div>
        </div>
      </div>
      {trade.time_stop && (
        <div className="text-[10px] text-yellow-400/70 flex items-center gap-1">
          <span>⏱</span> {trade.time_stop}
        </div>
      )}

      {trade.expiry && (
        <div className="text-[10px] text-[var(--color-text-muted)]">Expiry: {trade.expiry}</div>
      )}

      <button
        onClick={() => onAddToPaper(trade)}
        disabled={adding}
        className={cn(
          "w-full py-1.5 rounded text-xs font-medium transition-colors",
          isBuy
            ? "bg-[var(--color-success)]/20 hover:bg-[var(--color-success)]/30 text-[var(--color-success)] border border-[var(--color-success)]/30"
            : "bg-[var(--color-danger)]/20 hover:bg-[var(--color-danger)]/30 text-[var(--color-danger)] border border-[var(--color-danger)]/30",
          adding && "opacity-50 cursor-not-allowed",
        )}
      >
        {adding ? "Adding…" : "+ Add to Paper Trade"}
      </button>
    </div>
  );
}

// ── Result Card ───────────────────────────────────────────────────────────────

function ResultCard({ symbol, result }: { symbol: string; result: FNOSuggestion }) {
  const [expanded, setExpanded] = useState(false);
  const [addingId, setAddingId] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  const addMutation = useMutation({
    mutationFn: addPaperTrade,
    onSuccess: (_, vars) => {
      setAddingId(null);
      setToast(`Added ${vars.action} ${vars.symbol} ${vars.instrument_type}`);
      setTimeout(() => setToast(null), 3000);
    },
    onError: (e) => {
      setAddingId(null);
      setToast(`Error: ${e.message}`);
      setTimeout(() => setToast(null), 4000);
    },
  });

  const handleAdd = (trade: TradeRecommendation) => {
    const id = `${trade.action}-${trade.strike}-${trade.instrument}`;
    setAddingId(id);
    addMutation.mutate({
      symbol,
      instrument_type: trade.instrument,
      strike: trade.strike,
      expiry: trade.expiry,
      action: trade.action,
      lots: trade.lots,
      lot_size: getLotSize(symbol),
      entry_price: trade.entry_price,
      target_price: trade.target_price,
      stop_loss: trade.stop_loss,
      source: "AI",
      ai_confidence: trade.confidence,
      strategy_name: trade.strategy_name,
    });
  };

  if (result.error) {
    return (
      <Card>
        <CardContent className="p-4">
          <div className="flex items-center gap-2 text-yellow-400 text-sm font-medium mb-1">
            <AlertTriangle className="size-4" /> {symbol}
          </div>
          <p className="text-xs text-[var(--color-text-muted)]">{result.error}</p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardContent className="p-4 space-y-3">
        {toast && (
          <div className={cn(
            "text-xs px-3 py-2 rounded border",
            toast.startsWith("Error")
              ? "border-[var(--color-danger)]/40 bg-[var(--color-danger)]/10 text-[var(--color-danger)]"
              : "border-[var(--color-success)]/40 bg-[var(--color-success)]/10 text-[var(--color-success)]",
          )}>
            {toast}
          </div>
        )}

        {/* Header: symbol, signal, score */}
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-white font-semibold">{symbol}</span>
            {result.signal ? signalBadge(result.signal) : biasBadge(result.market_bias)}
          </div>
          <div className="flex items-center gap-2 shrink-0">
            {result.setup_score != null && result.setup_score > 0 && (
              <ScoreRing score={result.setup_score} />
            )}
            <span className="text-[10px] text-[var(--color-text-muted)] text-right">
              {result.valid_for_minutes}min<br />{result.tokens_used.toLocaleString()}tok
            </span>
          </div>
        </div>

        {/* No-trade message */}
        {result.no_trade && result.no_trade_reason && (
          <div className="rounded border border-[var(--color-border)] bg-[var(--color-surface-2)] px-3 py-2 text-xs text-[var(--color-text-muted)] flex items-start gap-2">
            <AlertTriangle className="size-3.5 shrink-0 mt-0.5 text-yellow-400" />
            <span>{result.no_trade_reason}</span>
          </div>
        )}

        {/* Market context assessment */}
        {result.market_context_assessment && (result.market_context_assessment.vix_assessment || result.market_context_assessment.pcr_assessment) && (
          <div className="rounded bg-[var(--color-surface-2)] px-3 py-2 space-y-1 text-[11px]">
            <div className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)] mb-1">Market Context</div>
            {result.market_context_assessment.vix_assessment && (
              <div className="text-[var(--color-text)]">📊 {result.market_context_assessment.vix_assessment}</div>
            )}
            {result.market_context_assessment.pcr_assessment && (
              <div className="text-[var(--color-text)]">⚖️ {result.market_context_assessment.pcr_assessment}</div>
            )}
          </div>
        )}

        {/* Price action signal */}
        {result.price_action_signal?.pattern_name && (
          <div className="rounded border border-[var(--color-primary)]/20 bg-[var(--color-primary)]/5 px-3 py-2 text-[11px]">
            <div className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)] mb-1">Price Action Signal</div>
            <div className="font-medium text-[var(--color-primary)]">{result.price_action_signal.pattern_name}</div>
            {result.price_action_signal.where_formed && (
              <div className="text-[var(--color-text-muted)]">{result.price_action_signal.where_formed}</div>
            )}
          </div>
        )}

        {/* Key levels — compact */}
        {Object.keys(result.key_levels ?? {}).length > 0 && (
          <div className="flex flex-wrap gap-x-3 gap-y-1 text-[11px] tnum">
            {Object.entries(result.key_levels)
              .filter(([, v]) => typeof v === "number" && v > 0)
              .slice(0, 8)
              .map(([k, v]) => (
              <span key={k} className="text-[var(--color-text-muted)]">
                {k.replace(/_/g, " ")}: <span className="text-white">{typeof v === "number" ? v.toLocaleString("en-IN") : String(v)}</span>
              </span>
            ))}
          </div>
        )}

        {/* Primary trade */}
        {!result.no_trade && result.primary_trade && (
          <div>
            <div className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)] mb-1.5">Primary Trade</div>
            <TradeCard
              trade={result.primary_trade}
              symbol={symbol}
              onAddToPaper={handleAdd}
              adding={addingId === `${result.primary_trade.action}-${result.primary_trade.strike}-${result.primary_trade.instrument}`}
            />
          </div>
        )}

        {/* Secondary trade */}
        {!result.no_trade && result.secondary_trade && (
          <div>
            <div className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)] mb-1.5">Secondary Trade</div>
            <TradeCard
              trade={result.secondary_trade}
              symbol={symbol}
              onAddToPaper={handleAdd}
              adding={addingId === `${result.secondary_trade.action}-${result.secondary_trade.strike}-${result.secondary_trade.instrument}`}
            />
          </div>
        )}

        {/* Expandable: Full analysis */}
        <button
          onClick={() => setExpanded((e) => !e)}
          className="w-full flex items-center justify-between text-[11px] text-[var(--color-text-muted)] hover:text-white transition-colors pt-1 border-t border-[var(--color-border)]"
        >
          <span>Full Analysis &amp; Risk</span>
          {expanded ? <ChevronUp className="size-3.5" /> : <ChevronDown className="size-3.5" />}
        </button>

        {expanded && (
          <div className="space-y-3">
            {/* MTF Summary */}
            {result.mtf_summary && Object.values(result.mtf_summary).some(Boolean) && (
              <div className="rounded bg-[var(--color-surface-2)] p-3 space-y-1">
                <div className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)] mb-1">MTF Analysis</div>
                {Object.entries(result.mtf_summary).map(([tf, val]) => val && (
                  <div key={tf} className="flex gap-2 text-[11px]">
                    <span className="text-[var(--color-text-muted)] w-14 shrink-0 capitalize">{tf}:</span>
                    <span className="text-[var(--color-text)]">{String(val)}</span>
                  </div>
                ))}
              </div>
            )}

            {/* Trade qualification reasons */}
            {(result.trade_qualification_reasons?.length ?? 0) > 0 && (
              <div>
                <div className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)] mb-1">Why This Qualifies</div>
                <ul className="space-y-1">
                  {result.trade_qualification_reasons!.map((r, i) => (
                    <li key={i} className="flex items-start gap-2 text-[11px] text-[var(--color-text)]">
                      <CheckCircle2 className="size-3 text-[var(--color-success)] mt-0.5 shrink-0" />
                      {r}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Invalidation conditions */}
            {(result.invalidation_conditions?.length ?? 0) > 0 && (
              <div>
                <div className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)] mb-1">Trade Invalidated If</div>
                <ul className="space-y-1">
                  {result.invalidation_conditions!.map((r, i) => (
                    <li key={i} className="flex items-start gap-2 text-[11px] text-[var(--color-danger)]">
                      <AlertTriangle className="size-3 mt-0.5 shrink-0" />
                      {r}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Reasoning */}
            {result.reasoning.length > 0 && (
              <div>
                <div className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)] mb-1">Reasoning</div>
                <ul className="space-y-1">
                  {result.reasoning.map((r, i) => (
                    <li key={i} className="flex items-start gap-2 text-[11px] text-[var(--color-text-muted)]">
                      <CheckCircle2 className="size-3 text-[var(--color-success)] mt-0.5 shrink-0" />
                      {r}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Risk factors */}
            {result.risk_factors.length > 0 && (
              <div>
                <div className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)] mb-1">Risk Factors</div>
                <ul className="space-y-1">
                  {result.risk_factors.map((r, i) => (
                    <li key={i} className="flex items-start gap-2 text-[11px] text-yellow-400/80">
                      <AlertTriangle className="size-3 mt-0.5 shrink-0" />
                      {r}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function FoAiAdvisorPage() {
  const [selected, setSelected] = useState<string[]>(["NIFTY", "BANKNIFTY"]);
  const [results, setResults] = useState<Map<string, FNOSuggestion>>(new Map());
  const [analyzing, setAnalyzing] = useState<string[]>([]);
  const [symInput, setSymInput] = useState("");

  const symbolsQuery = useQuery<string[]>({
    queryKey: ["fno", "symbols"],
    queryFn: getFnoSymbols,
    staleTime: 10 * 60_000,
  });

  const allSymbols = useMemo(() => {
    const extra = (symbolsQuery.data ?? []).filter((s) => !INDEX_SYMBOLS.includes(s));
    return [...INDEX_SYMBOLS, ...extra.sort()];
  }, [symbolsQuery.data]);

  const filteredSuggestions = useMemo(() => {
    const q = symInput.toUpperCase();
    return q ? allSymbols.filter((s) => s.includes(q)).slice(0, 20) : allSymbols.slice(0, 20);
  }, [allSymbols, symInput]);

  const toggleSymbol = (sym: string) => {
    setSelected((prev) =>
      prev.includes(sym) ? prev.filter((s) => s !== sym) : prev.length < 5 ? [...prev, sym] : prev,
    );
  };

  const runAnalysis = async () => {
    if (selected.length === 0) return;
    const toRun = selected.filter((s) => !analyzing.includes(s));
    setAnalyzing(toRun);

    for (const sym of toRun) {
      try {
        const r = await getFnoAiSuggestion(sym);
        setResults((prev) => new Map(prev).set(sym, r));
      } catch (e) {
        setResults((prev) =>
          new Map(prev).set(sym, {
            symbol: sym, error: String(e),
            primary_trade: null, secondary_trade: null,
            reasoning: [], market_bias: "NEUTRAL", key_levels: {},
            risk_factors: [], valid_for_minutes: 0,
            analysis_timestamp: "", context_used: "",
            tokens_used: 0, cost_inr: 0,
          }),
        );
      }
      setAnalyzing((prev) => prev.filter((s) => s !== sym));
    }
  };

  const resultsList = useMemo(
    () => selected.map((s) => ({ symbol: s, result: results.get(s) })),
    [selected, results],
  );

  const totalTokens = useMemo(
    () => Array.from(results.values()).reduce((sum, r) => sum + (r.tokens_used ?? 0), 0),
    [results],
  );

  return (
    <div className="space-y-5 max-w-[1400px] mx-auto">
      {/* Header */}
      <header>
        <div className="flex items-center gap-2 mb-1">
          <Cpu className="size-5 text-[var(--color-primary)]" />
          <h1 className="text-xl font-semibold text-white">F&amp;O AI Advisor</h1>
        </div>
        <p className="text-xs text-[var(--color-text-muted)]">
          Elite options buying agent — scores setups 0–100 using 4-TF MTF analysis, price action, key levels, and options quality. Only suggests CE/PE buying when score ≥ 70.
        </p>
      </header>

      {/* Symbol selector + controls */}
      <Card>
        <CardContent className="p-4 space-y-4">
          <div className="flex items-center justify-between">
            <div className="text-sm font-medium text-white">
              Selected: {selected.length}/5
              {selected.length > 0 && (
                <span className="text-[var(--color-text-muted)] ml-2 font-normal">
                  {selected.join(", ")}
                </span>
              )}
            </div>
            <div className="flex items-center gap-2">
              {totalTokens > 0 && (
                <span className="text-[11px] text-[var(--color-text-muted)]">
                  {totalTokens.toLocaleString()} tokens used
                </span>
              )}
              <button
                onClick={runAnalysis}
                disabled={selected.length === 0 || analyzing.length > 0}
                className={cn(
                  "flex items-center gap-1.5 px-4 py-2 rounded-md text-sm font-medium transition-colors",
                  selected.length > 0 && analyzing.length === 0
                    ? "bg-[var(--color-primary)] hover:bg-[var(--color-primary)]/90 text-white"
                    : "bg-[var(--color-surface-2)] text-[var(--color-text-muted)] cursor-not-allowed",
                )}
              >
                {analyzing.length > 0 ? (
                  <><RefreshCw className="size-3.5 animate-spin" /> Analysing {analyzing[0]}…</>
                ) : (
                  <><Cpu className="size-3.5" /> Analyse All</>
                )}
              </button>
            </div>
          </div>

          {/* Symbol search */}
          <div className="space-y-2">
            <input
              value={symInput}
              onChange={(e) => setSymInput(e.target.value)}
              placeholder="Filter symbols…"
              className="h-8 w-full px-3 rounded border border-[var(--color-border)] bg-[var(--color-surface)] text-xs text-white uppercase placeholder:normal-case placeholder:text-[var(--color-text-muted)] focus:outline-none focus:border-[var(--color-primary)]"
            />
            <div className="flex flex-wrap gap-1.5 max-h-40 overflow-y-auto">
              {filteredSuggestions.map((sym) => {
                const isSelected = selected.includes(sym);
                const isDisabled = !isSelected && selected.length >= 5;
                return (
                  <button
                    key={sym}
                    onClick={() => toggleSymbol(sym)}
                    disabled={isDisabled}
                    className={cn(
                      "px-2.5 py-1 rounded text-[11px] font-medium transition-colors border",
                      isSelected
                        ? "bg-[var(--color-primary)] border-[var(--color-primary)] text-white"
                        : isDisabled
                        ? "border-[var(--color-border)] text-[var(--color-text-muted)] cursor-not-allowed opacity-50"
                        : "border-[var(--color-border)] text-[var(--color-text-muted)] hover:border-[var(--color-primary)]/60 hover:text-white",
                    )}
                  >
                    {sym}
                  </button>
                );
              })}
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Results grid */}
      {resultsList.some((r) => r.result) && (
        <div>
          <h2 className="text-[11px] uppercase tracking-wider text-[var(--color-text-muted)] mb-3">Analysis Results</h2>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {resultsList.map(({ symbol, result }) =>
              result ? (
                <ResultCard key={symbol} symbol={symbol} result={result} />
              ) : analyzing.includes(symbol) ? (
                <Card key={symbol}>
                  <CardContent className="p-4 space-y-3">
                    <div className="flex items-center gap-2">
                      <Skeleton className="h-4 w-20" />
                      <Skeleton className="h-4 w-16" />
                    </div>
                    <Skeleton className="h-24 w-full" />
                    <Skeleton className="h-20 w-full" />
                    <div className="text-xs text-[var(--color-text-muted)] animate-pulse">
                      Calling Claude for {symbol}…
                    </div>
                  </CardContent>
                </Card>
              ) : null,
            )}
          </div>
        </div>
      )}

      {/* Empty state */}
      {resultsList.every((r) => !r.result) && analyzing.length === 0 && (
        <div className="rounded-lg border border-[var(--color-border)] p-12 text-center space-y-3">
          <Cpu className="size-10 text-[var(--color-text-muted)] mx-auto" />
          <div className="text-sm font-medium text-white">Select symbols and click Analyse All</div>
          <p className="text-xs text-[var(--color-text-muted)] max-w-sm mx-auto">
            The Elite F&O Agent runs 4-timeframe MTF analysis, identifies price action patterns at key levels, scores options quality, and produces CE/PE buying setups when score ≥ 70/100.
          </p>
          <p className="text-[10px] text-[var(--color-text-muted)]">
            Requires an Anthropic API key — configure it in Settings → AI Agent. First scan per symbol includes MTF data fetch (~30–60s).
          </p>
        </div>
      )}
    </div>
  );
}
