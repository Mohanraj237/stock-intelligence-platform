"use client";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { PageHeader } from "@/components/common/page-header";

export default function LearnPage() {
  return (
    <div className="max-w-5xl mx-auto space-y-5">
      <PageHeader title="Learn" subtitle="Platform guide, chart patterns, indicators, fundamentals & risk." />
      <Tabs defaultValue="guide">
        <TabsList>
          <TabsTrigger value="guide">Platform Guide</TabsTrigger>
          <TabsTrigger value="patterns">Chart Patterns</TabsTrigger>
          <TabsTrigger value="indicators">Indicators</TabsTrigger>
          <TabsTrigger value="fundamentals">Fundamentals</TabsTrigger>
          <TabsTrigger value="risk">Risk Management</TabsTrigger>
        </TabsList>
        <TabsContent value="guide"><PlatformGuide /></TabsContent>
        <TabsContent value="patterns"><Patterns /></TabsContent>
        <TabsContent value="indicators"><Indicators /></TabsContent>
        <TabsContent value="fundamentals"><Fundamentals /></TabsContent>
        <TabsContent value="risk"><RiskManagement /></TabsContent>
      </Tabs>
    </div>
  );
}

function Patterns() {
  const { data, isLoading } = useQuery({ queryKey: ["pattern-library"], queryFn: api.patternLibrary });
  if (isLoading) return <Skeleton className="h-96" />;
  return (
    <div className="grid md:grid-cols-2 gap-4">
      {(data ?? []).map((p) => (
        <Card key={p.name}>
          <CardHeader>
            <div className="flex items-center justify-between gap-2">
              <CardTitle>{p.name}</CardTitle>
              <Badge variant={p.direction === "Bullish" ? "success" : p.direction === "Bearish" ? "danger" : "default"}>
                {p.direction}
              </Badge>
            </div>
            <CardDescription>{p.category} · best on {p.best_timeframes}</CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-[var(--color-text)] leading-relaxed">{p.description}</p>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

const INDICATORS = [
  { name: "RSI (Relative Strength Index)", levels: "Below 30 = oversold · Above 70 = overbought", use: "Spot stretched conditions; pair with trend." },
  { name: "MACD", levels: "Crossover above signal = bullish; histogram > 0 = momentum up", use: "Confirm trend changes; avoid in choppy markets." },
  { name: "ADX", levels: "Below 20 = no trend · Above 25 = trend; 40+ = strong", use: "Use as filter — only trade trend setups when ADX > 20." },
  { name: "EMA / SMA", levels: "Price > 50 SMA = uptrend bias; 50 > 200 = bull regime", use: "Trend filter; never fight the moving averages." },
  { name: "Bollinger Bands", levels: "Width contraction → expansion = breakout", use: "Spot squeezes before breakouts." },
  { name: "Stochastic", levels: "Below 20 = oversold · Above 80 = overbought", use: "Mean-reversion in ranging markets." },
];

function Indicators() {
  return (
    <div className="grid md:grid-cols-2 gap-4">
      {INDICATORS.map((i) => (
        <Card key={i.name}>
          <CardHeader><CardTitle>{i.name}</CardTitle></CardHeader>
          <CardContent className="text-sm space-y-2">
            <p><span className="muted">Key levels: </span>{i.levels}</p>
            <p><span className="muted">How to use: </span>{i.use}</p>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

const FUNDS = [
  { name: "PE (Price/Earnings)", desc: "Healthy varies by sector. <20 cheap, 20-40 fair, >40 rich (with caveats)." },
  { name: "PB (Price/Book)", desc: "<1 deep value, 1-3 normal, >5 premium. Banks watched closely." },
  { name: "ROE", desc: ">15% strong; sustained 20%+ is a quality signal." },
  { name: "ROCE", desc: ">15% indicates capital-efficient operations." },
  { name: "Debt/Equity", desc: "<0.5 conservative; >1.0 elevated (capital-intensive sectors aside)." },
  { name: "OPM (Operating margin)", desc: "Stable / rising margin compounds over years." },
  { name: "Promoter holding", desc: ">50% strong skin in the game; pledge % > 25 is a warning." },
];

function Fundamentals() {
  return (
    <div className="grid md:grid-cols-2 gap-4">
      {FUNDS.map((f) => (
        <Card key={f.name}>
          <CardHeader><CardTitle>{f.name}</CardTitle></CardHeader>
          <CardContent className="text-sm">{f.desc}</CardContent>
        </Card>
      ))}
    </div>
  );
}

function RiskManagement() {
  const items = [
    ["Risk per trade", "Cap at 1% of total capital. A 10-loss streak = 10% drawdown — survivable."],
    ["R:R (Reward / Risk)", "Minimum 2:1 expected. 3:1 ideal for swing trades."],
    ["Position size formula", "Qty = (Capital × Risk%) / (Entry − Stop)"],
    ["Stop discipline", "Pre-set stop before placing trade. Never widen a stop after entry."],
    ["Diversification", "Max 5–8 open positions; spread across sectors."],
    ["Trailing stops", "Lock in once price moves > 1.5R in your favour."],
    ["Daily / weekly drawdown", "Stop trading after −3% day or −5% week. Sleep on it."],
  ] as const;
  return (
    <Card>
      <CardHeader><CardTitle>The seven rules</CardTitle></CardHeader>
      <CardContent>
        <dl className="space-y-3 text-sm">
          {items.map(([k, v]) => (
            <div key={k} className="border-b border-[var(--color-border)] pb-3 last:border-0 last:pb-0">
              <dt className="font-medium text-white">{k}</dt>
              <dd className="muted mt-1">{v}</dd>
            </div>
          ))}
        </dl>
      </CardContent>
    </Card>
  );
}

// ─── Platform Guide ────────────────────────────────────────────────────────────

interface GuideSection {
  title: string;
  icon: string;
  path: string;
  summary: string;
  steps: string[];
  tips?: string[];
}

const EQUITY_GUIDE: GuideSection[] = [
  {
    title: "Dashboard",
    icon: "📊",
    path: "/dashboard",
    summary: "Market-wide situational awareness — indices, sector heatmap, FII/DII flow, and top movers. Works for both India and US markets.",
    steps: [
      "Switch between India and US using the Market Region toggle in the sidebar.",
      "The Indices row shows the top 6 indices for your selected region.",
      "Open the Sectors tab to see a colour-coded heatmap of sector performance.",
      "Open FII/DII (India only) to see 30-day institutional flow charts and daily totals.",
      "Top Movers shows the 5 biggest gainers and losers in the NIFTY 50 (India) or DOW 30 (US).",
    ],
    tips: ["Dashboard auto-refreshes every 60 s — no need to reload."],
  },
  {
    title: "Universe Explorer",
    icon: "🔭",
    path: "/universe",
    summary: "Browse every stock in an index with live prices, 30-day and 1-year returns, volume, and 52-week range.",
    steps: [
      "Choose a universe from the dropdown (NIFTY 50, NIFTY 500, DOW 30, NASDAQ 100, sector indices, etc.).",
      "Sort by any column by clicking the column header.",
      "Click any row to open the Stock Analyzer for that symbol.",
      "Use the search box to filter by symbol or company name within the loaded universe.",
    ],
    tips: ["Live prices come from NSE for India and Yahoo Finance for US.", "If prices show —, the data source is temporarily unavailable — refresh in 30 s."],
  },
  {
    title: "Stock Analyzer",
    icon: "📈",
    path: "/analyzer",
    summary: "Full technical + fundamental analysis for any stock. Candlestick chart, 20+ indicators, AI verdict, and peer comparison.",
    steps: [
      "Type a symbol in the search box (e.g. RELIANCE, HDFCBANK, AAPL).",
      "Change timeframe (1D · 1W · 1M) using the buttons above the chart.",
      "The Indicators panel below the chart shows RSI, MACD, ADX, moving averages, Bollinger Bands, and more.",
      "Switch to the Fundamentals tab for PE, PB, ROE, debt, revenue, and promoter holding.",
      "The AI Verdict tab uses Claude AI to summarise the technical and fundamental picture.",
      "Peers tab shows how the stock compares to sector peers on key metrics.",
    ],
    tips: ["Press the copy icon next to the symbol to share the exact chart URL.", "AI Verdict is generated on-demand — it is not cached, so each fetch is fresh."],
  },
  {
    title: "Scanner",
    icon: "🔍",
    path: "/scanner",
    summary: "Scan an entire index for technical setups in seconds: RSI extremes, MACD crossovers, moving average alignments, and more.",
    steps: [
      "Select a universe (e.g. NIFTY 500) and a scan type (e.g. 'RSI Oversold').",
      "Click Run Scan — results appear as a ranked table.",
      "Click any result row to open the Stock Analyzer for deeper analysis.",
    ],
    tips: ["Scans run over live data; larger universes (500 stocks) take 15–30 s.", "Combine Scanner findings with Pattern Lab for high-confidence setups."],
  },
  {
    title: "Pattern Lab",
    icon: "🧪",
    path: "/patterns",
    summary: "Detect classic chart patterns (Head & Shoulders, Cup & Handle, Flags, Wedges, etc.) on any stock across all timeframes.",
    steps: [
      "Enter a symbol and select a timeframe.",
      "The app scans recent bars and returns all detected patterns with confidence scores.",
      "Click a pattern name to see the example chart and description in the Learn tab.",
      "Use Multi-TF Breakout to check alignment across Daily, Weekly, and Monthly.",
    ],
    tips: ["Higher confidence (>70%) patterns on higher timeframes (Weekly/Monthly) carry more weight.", "Patterns work best on liquid, high-volume stocks."],
  },
  {
    title: "Compare",
    icon: "⚖️",
    path: "/compare",
    summary: "Compare up to 4 stocks side-by-side on price performance, fundamentals, and technical strength.",
    steps: [
      "Add 2–4 symbols using the input boxes.",
      "The normalised price chart shows relative performance from a common start date.",
      "The metrics table below highlights which stock is best/worst on each metric.",
    ],
  },
  {
    title: "Backtest",
    icon: "🔄",
    path: "/backtest",
    summary: "Test a pattern-based entry strategy against historical data for any universe to see win rate, average return, and equity curve.",
    steps: [
      "Select a universe, pattern, and timeframe.",
      "Set max symbols, holding bars, and minimum confidence threshold.",
      "Click Run — the backtest engine runs entry/exit simulations on historical bars.",
      "Review win rate, profit factor, max drawdown, and the equity curve chart.",
      "The Trades table shows every simulated trade with entry/exit dates and returns.",
    ],
    tips: ["A profit factor > 1.5 and win rate > 50% is a solid baseline.", "Larger universes increase sample size and statistical significance."],
  },
  {
    title: "Position Sizing",
    icon: "🧮",
    path: "/position-sizing",
    summary: "Calculate the correct quantity to trade based on your capital, risk tolerance, entry price, and stop-loss.",
    steps: [
      "Enter your total capital and risk per trade percentage (default 1%).",
      "Enter entry price and stop-loss price.",
      "The tool instantly shows recommended quantity, capital at risk, and position size.",
    ],
    tips: ["Stick to 1% risk per trade — it makes a 20-trade losing streak survivable.", "Use this before every trade, not just when in doubt."],
  },
  {
    title: "Rule Engine",
    icon: "⚙️",
    path: "/rules",
    summary: "Build custom screening rules (IF RSI < 40 AND price > SMA200 THEN flag) and apply them to any universe.",
    steps: [
      "Click New Rule and define conditions using the visual builder.",
      "Save the rule and combine multiple rules into a ruleset.",
      "Apply the ruleset to a universe — results show all matching stocks.",
    ],
  },
  {
    title: "Portfolio",
    icon: "💼",
    path: "/portfolio",
    summary: "Track your holdings, view unrealised P&L, and see your overall allocation.",
    steps: [
      "Add a holding by entering symbol, quantity, buy price, and optional buy date.",
      "The portfolio table shows current price, P&L (absolute and %), and weight.",
      "Remove a holding by clicking the delete icon.",
    ],
    tips: ["Prices are refreshed from the same data sources as the rest of the app."],
  },
  {
    title: "Watchlist",
    icon: "⭐",
    path: "/watchlist",
    summary: "A quick-view list of your tracked symbols with live price, RSI, MACD histogram, and moving averages.",
    steps: [
      "Add a symbol by typing it in the input box and pressing Add.",
      "The watchlist shows live price, % change, RSI, and MACD histogram colour-coded by signal.",
      "Remove a symbol using the × button.",
    ],
    tips: ["Supports both NSE symbols (RELIANCE) and US tickers (AAPL, TSLA) in the same list."],
  },
  {
    title: "News & Earnings",
    icon: "📰",
    path: "/news",
    summary: "Aggregated market news and corporate earnings calendar for India and US.",
    steps: [
      "News shows the latest 60 headlines from RSS feeds, filterable by symbol.",
      "Earnings shows upcoming results for the next 14 days and recent surprises.",
    ],
  },
];

const FO_GUIDE: GuideSection[] = [
  {
    title: "F&O Dashboard",
    icon: "📉",
    path: "/fo-dashboard",
    summary: "Overview of the F&O market: India VIX, PCR, index futures premium/discount, and live OI spurts.",
    steps: [
      "Switch to F&O mode using the Market Mode toggle (India only).",
      "VIX gauge shows current implied volatility — above 20 is elevated fear.",
      "PCR (Put-Call Ratio) > 1.2 signals oversold market; < 0.8 signals complacency.",
      "Index futures section shows premium/discount to spot for NIFTY, BANKNIFTY, FINNIFTY.",
      "OI Spurts table shows contracts with the biggest open interest changes.",
    ],
    tips: ["PCR and VIX together give the clearest sentiment signal.", "OI spurts often lead price moves by 15–30 minutes."],
  },
  {
    title: "Option Chain",
    icon: "🔗",
    path: "/option-chain",
    summary: "Full NSE option chain for any F&O-eligible symbol, showing CE and PE OI, IV, delta, and gamma at every strike.",
    steps: [
      "Select a symbol (NIFTY, BANKNIFTY, or any F&O stock) and expiry date.",
      "The chain is centred on the ATM strike with ITM/OTM strikes above and below.",
      "Max Pain is highlighted — the strike where option writers lose the least.",
      "Clicking a row populates the strike in the Strategy Builder.",
    ],
  },
  {
    title: "OI Analytics",
    icon: "📊",
    path: "/oi-analytics",
    summary: "Open interest charts, CE vs PE OI comparison, and OI change across strikes.",
    steps: [
      "Select symbol and expiry.",
      "OI bar chart shows total CE OI (red) and PE OI (blue) at each strike.",
      "The OI change chart highlights where new positions are being built or unwound.",
    ],
    tips: ["High CE OI at a strike = resistance; high PE OI = support.", "Sudden OI additions with price movement = trend continuation."],
  },
  {
    title: "PCR & Sentiment",
    icon: "📡",
    path: "/pcr-sentiment",
    summary: "Put-Call Ratio history, Fear & Greed gauge, and market breadth for F&O stocks.",
    steps: [
      "PCR chart shows daily history — spot trend reversals when PCR reaches extremes.",
      "Sentiment gauge aggregates VIX, PCR, and breadth into a single Fear/Neutral/Greed reading.",
    ],
  },
  {
    title: "Expiry Heatmap",
    icon: "🗓️",
    path: "/expiry-heatmap",
    summary: "OI distribution across all strikes and expiry dates in a single heatmap view.",
    steps: [
      "Each cell shows OI for a (strike, expiry) combination.",
      "Colour intensity indicates OI magnitude — darker = more OI.",
      "Use this to spot the strikes with maximum concentration across near/far expiries.",
    ],
    tips: ["The near-expiry columns (left side) have far more OI than far expiries."],
  },
  {
    title: "Strategy Builder",
    icon: "🎯",
    path: "/strategy-builder",
    summary: "Visually build multi-leg options strategies (spreads, condors, straddles) and see the P&L payoff chart.",
    steps: [
      "Add legs by selecting Buy/Sell, CE/PE, strike, expiry, and premium.",
      "The payoff chart updates instantly as you add legs.",
      "Max profit, max loss, and breakeven points are shown below the chart.",
      "Click Add to Paper Trade to execute the strategy as a virtual trade.",
    ],
  },
  {
    title: "F&O Scanner",
    icon: "🔦",
    path: "/fo-scanner",
    summary: "Scan for options with unusual activity: high IV, large OI changes, and volume spikes.",
    steps: [
      "Select a scan type (High IV, OI Buildup, Volume Surge).",
      "Click Scan — results show the top contracts across all F&O symbols.",
    ],
  },
  {
    title: "Greeks Dashboard",
    icon: "🔢",
    path: "/greeks",
    summary: "Calculate and visualise Delta, Gamma, Theta, Vega, and Rho for any option.",
    steps: [
      "Select symbol, expiry, strike, and option type (CE/PE).",
      "Greeks are computed using Black-Scholes with live VIX as implied volatility.",
      "Charts show how each Greek changes across strikes and time-to-expiry.",
    ],
    tips: ["Theta decay accelerates in the last 7 days before expiry.", "High Gamma near ATM means P&L can swing rapidly — size accordingly."],
  },
  {
    title: "Paper Trade",
    icon: "📝",
    path: "/paper-trade",
    summary: "Simulate F&O trades without real money. Track P&L, see equity curve, and measure strategy performance.",
    steps: [
      "Add a paper trade by filling in symbol, strategy, entry price, quantity, and direction.",
      "Open trades table shows live mark-to-market P&L.",
      "Close a trade by clicking the Close button and entering exit price.",
      "Equity Curve chart shows cumulative P&L over time.",
    ],
    tips: [
      "Paper trades are purely virtual — no real broker is connected.",
      "Use paper trading to validate a strategy for 20+ trades before risking real capital.",
    ],
  },
  {
    title: "AI F&O Advisor",
    icon: "🤖",
    path: "/fo-ai-advisor",
    summary: "Claude AI analyses the option chain, VIX, and PCR to suggest appropriate strategies and risk levels.",
    steps: [
      "Select a symbol and timeframe.",
      "Click Analyse — the AI reads the full option chain, OI profile, and sentiment indicators.",
      "The response includes a market bias, specific strategy suggestions with strikes, and risk warnings.",
    ],
    tips: ["AI suggestions are educational — always verify with your own analysis before trading.", "The AI never recommends specific position sizes or guarantees outcomes."],
  },
];

function GuideCard({ section }: { section: GuideSection }) {
  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <span className="text-2xl">{section.icon}</span>
          <div>
            <CardTitle>{section.title}</CardTitle>
            <CardDescription className="text-[11px] mt-0.5">{section.path}</CardDescription>
          </div>
        </div>
        <p className="text-sm text-[var(--color-text)] mt-2 leading-relaxed">{section.summary}</p>
      </CardHeader>
      <CardContent className="space-y-3">
        <div>
          <p className="text-[10px] uppercase tracking-wider muted mb-2">How to use</p>
          <ol className="space-y-1.5 text-sm">
            {section.steps.map((s, i) => (
              <li key={i} className="flex gap-2">
                <span className="shrink-0 size-5 rounded-full bg-[var(--color-primary)]/20 text-[var(--color-primary)] text-[11px] font-medium grid place-items-center">{i + 1}</span>
                <span className="text-[var(--color-text)] leading-relaxed">{s}</span>
              </li>
            ))}
          </ol>
        </div>
        {section.tips && section.tips.length > 0 && (
          <div className="rounded-md bg-[var(--color-surface-2)] p-3 space-y-1">
            <p className="text-[10px] uppercase tracking-wider muted">Tips</p>
            {section.tips.map((t, i) => (
              <p key={i} className="text-xs text-[var(--color-text)] leading-relaxed">💡 {t}</p>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function PlatformGuide() {
  return (
    <div className="space-y-6">
      <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] p-4 text-sm">
        <p className="font-medium text-white mb-1">Stock Intelligence Platform v2.0</p>
        <p className="muted leading-relaxed">
          A fully local, data-sovereign stock research tool for India and US markets.
          All data is fetched directly from NSE India and Yahoo Finance — no paid subscriptions required.
          The F&O module (India only) is accessible via the Market Mode toggle in the sidebar.
        </p>
      </div>

      <div>
        <h2 className="text-xs uppercase tracking-wider muted mb-3">Equity Mode</h2>
        <div className="grid md:grid-cols-2 gap-4">
          {EQUITY_GUIDE.map((s) => <GuideCard key={s.path} section={s} />)}
        </div>
      </div>

      <div>
        <h2 className="text-xs uppercase tracking-wider muted mb-3">F&amp;O Mode · India only</h2>
        <div className="grid md:grid-cols-2 gap-4">
          {FO_GUIDE.map((s) => <GuideCard key={s.path} section={s} />)}
        </div>
      </div>
    </div>
  );
}
