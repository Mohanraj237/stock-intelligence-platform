import {
  BookOpen,
  TrendingUp,
  AlertCircle,
  Info,
  BarChart2,
  Target,
  Shield,
  Zap,
  Clock,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

// ── Section Divider ───────────────────────────────────────────────────────────

function SectionDivider() {
  return <hr className="border-[var(--color-border)]" />;
}

// ── Section Heading ───────────────────────────────────────────────────────────

function SectionHeading({
  icon: Icon,
  title,
  subtitle,
}: {
  icon: React.ElementType;
  title: string;
  subtitle?: string;
}) {
  return (
    <div className="flex items-start gap-3">
      <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-[var(--color-primary)]/15 text-[var(--color-primary)]">
        <Icon size={16} />
      </div>
      <div>
        <h2 className="text-base font-semibold text-white">{title}</h2>
        {subtitle && (
          <p className="mt-0.5 text-xs text-[var(--color-text-muted)]">{subtitle}</p>
        )}
      </div>
    </div>
  );
}

// ── Term Card ─────────────────────────────────────────────────────────────────

function TermCard({ term, definition }: { term: string; definition: string }) {
  return (
    <div className="rounded-md border border-[var(--color-border)] bg-[var(--color-surface-2)] p-3 space-y-1">
      <div className="text-xs font-semibold text-[var(--color-primary)]">{term}</div>
      <div className="text-xs text-[var(--color-text-muted)] leading-relaxed">{definition}</div>
    </div>
  );
}

// ── Strategy Card ─────────────────────────────────────────────────────────────

function StrategyCard({
  name,
  risk,
  reward,
  when,
  riskType,
}: {
  name: string;
  risk: string;
  reward: string;
  when: string;
  riskType: "low" | "medium" | "high";
}) {
  const riskVariant =
    riskType === "low" ? "success" : riskType === "medium" ? "warning" : "danger";

  return (
    <div className="rounded-md border border-[var(--color-border)] bg-[var(--color-surface-2)] p-4 space-y-2.5">
      <div className="flex items-center justify-between">
        <div className="text-sm font-semibold text-white">{name}</div>
        <Badge variant={riskVariant}>{riskType} risk</Badge>
      </div>
      <div className="space-y-1 text-xs">
        <div className="flex items-start gap-2">
          <span className="shrink-0 text-[var(--color-text-muted)] w-14">Risk</span>
          <span className="text-[var(--color-danger)]">{risk}</span>
        </div>
        <div className="flex items-start gap-2">
          <span className="shrink-0 text-[var(--color-text-muted)] w-14">Reward</span>
          <span className="text-[var(--color-success)]">{reward}</span>
        </div>
        <div className="flex items-start gap-2">
          <span className="shrink-0 text-[var(--color-text-muted)] w-14">Use when</span>
          <span className="text-white">{when}</span>
        </div>
      </div>
    </div>
  );
}

// ── VIX Band Row ──────────────────────────────────────────────────────────────

function VixRow({
  range,
  label,
  description,
  badgeVariant,
}: {
  range: string;
  label: string;
  description: string;
  badgeVariant: "success" | "info" | "warning" | "danger";
}) {
  return (
    <div className="flex items-start gap-4 rounded-md border border-[var(--color-border)] bg-[var(--color-surface-2)] p-3">
      <div className="shrink-0 text-right">
        <div className="text-sm font-bold text-white tnum">{range}</div>
        <Badge variant={badgeVariant} className="mt-1">{label}</Badge>
      </div>
      <div className="text-xs text-[var(--color-text-muted)] leading-relaxed pt-0.5">{description}</div>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function FoLearnPage() {
  return (
    <div className="max-w-4xl mx-auto space-y-10 pb-16">
      {/* Page title */}
      <div>
        <h1 className="text-2xl font-bold text-white">F&amp;O Learning Centre</h1>
        <p className="mt-1 text-sm text-[var(--color-text-muted)]">
          A complete reference for Futures &amp; Options concepts, terms, Greeks, strategies and India-specific facts.
        </p>
      </div>

      <SectionDivider />

      {/* ── Section 1: What are Futures & Options? ─────────────────────────────── */}
      <section className="space-y-5">
        <SectionHeading
          icon={BookOpen}
          title="What are Futures & Options?"
          subtitle="The two primary derivative instruments traded on NSE"
        />

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Futures */}
          <div className="rounded-md border border-[var(--color-border)] bg-[var(--color-surface-2)] p-4 space-y-2">
            <div className="flex items-center gap-2">
              <TrendingUp size={14} className="text-[var(--color-primary)]" />
              <span className="text-sm font-semibold text-white">Futures</span>
              <Badge variant="info">Obligation</Badge>
            </div>
            <p className="text-xs text-[var(--color-text-muted)] leading-relaxed">
              A legally binding contract to buy or sell an underlying asset at a predetermined price on a specific future date.
              Both buyer and seller are obligated to fulfil the contract.
            </p>
            <ul className="text-xs text-[var(--color-text-muted)] space-y-1 list-disc list-inside">
              <li>Used for hedging existing stock/portfolio exposure</li>
              <li>Allows speculation with leverage (margin-based)</li>
              <li>Daily mark-to-market settlement</li>
            </ul>
          </div>

          {/* Options */}
          <div className="rounded-md border border-[var(--color-border)] bg-[var(--color-surface-2)] p-4 space-y-2">
            <div className="flex items-center gap-2">
              <Target size={14} className="text-[var(--color-success)]" />
              <span className="text-sm font-semibold text-white">Options</span>
              <Badge variant="success">Right, not Obligation</Badge>
            </div>
            <p className="text-xs text-[var(--color-text-muted)] leading-relaxed">
              A contract that gives the buyer the <em>right</em> (but not the obligation) to buy (Call / CE) or sell (Put / PE)
              an underlying at the strike price before or on expiry.
            </p>
            <ul className="text-xs text-[var(--color-text-muted)] space-y-1 list-disc list-inside">
              <li><span className="text-[var(--color-success)]">CE (Call)</span>: right to buy — profits when price rises</li>
              <li><span className="text-[var(--color-danger)]">PE (Put)</span>: right to sell — profits when price falls</li>
              <li>Buyer&apos;s downside is limited to premium paid</li>
            </ul>
          </div>
        </div>

        {/* Key difference */}
        <div className="rounded-md border border-[var(--color-primary)]/30 bg-[var(--color-primary)]/5 p-4 flex items-start gap-3">
          <Info size={14} className="mt-0.5 shrink-0 text-[var(--color-primary)]" />
          <p className="text-xs text-[var(--color-text-muted)] leading-relaxed">
            <span className="text-white font-medium">Key difference: </span>
            Futures carry <span className="text-[var(--color-danger)]">obligation</span> for both parties — unlimited profit and loss.
            Options give the buyer a <span className="text-[var(--color-success)]">right with capped downside</span> (premium),
            while the <span className="text-[var(--color-danger)]">seller (writer) carries unlimited risk</span>.
          </p>
        </div>
      </section>

      <SectionDivider />

      {/* ── Section 2: Key F&O Terms ──────────────────────────────────────────── */}
      <section className="space-y-5">
        <SectionHeading
          icon={Info}
          title="Key F&O Terms"
          subtitle="Essential vocabulary every F&O trader must know"
        />

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <TermCard
            term="Strike Price"
            definition="The fixed price at which the option buyer can buy (CE) or sell (PE) the underlying asset, regardless of market price."
          />
          <TermCard
            term="Expiry Date"
            definition="The date on which the contract expires. For indices: last Thursday of the expiry week. For stocks: last Thursday of the month."
          />
          <TermCard
            term="Lot Size"
            definition="The minimum number of units per contract (e.g., NIFTY = 75, BANKNIFTY = 15, FINNIFTY = 40). You always trade in lot multiples."
          />
          <TermCard
            term="LTP (Last Traded Price)"
            definition="The most recent price at which an option or future was bought or sold on the exchange."
          />
          <TermCard
            term="OI (Open Interest)"
            definition="The total number of outstanding (unsettled) contracts in the market. Rising OI with rising price = bullish confirmation."
          />
          <TermCard
            term="IV (Implied Volatility)"
            definition="The market's expectation of future volatility derived from option prices. High IV = expensive options; low IV = cheap options."
          />
          <TermCard
            term="ATM / ITM / OTM"
            definition="ATM (At-the-Money): strike ≈ spot. ITM (In-the-Money): intrinsic value exists. OTM (Out-of-the-Money): no intrinsic value, only time value."
          />
          <TermCard
            term="PCR (Put-Call Ratio)"
            definition="PE OI ÷ CE OI. PCR > 1.2 indicates bullish sentiment (more puts sold). PCR < 0.8 indicates bearish sentiment."
          />
          <TermCard
            term="Max Pain"
            definition="The strike price at which the maximum number of options expire worthless — minimising payouts by option writers. Price tends to gravitate here near expiry."
          />
          <TermCard
            term="CE / PE"
            definition="CE = Call European (right to buy). PE = Put European (right to sell). NSE index options are European-style (exercisable only at expiry)."
          />
          <TermCard
            term="Premium"
            definition="The price paid by the option buyer to the seller for the right embedded in the option contract."
          />
          <TermCard
            term="Intrinsic Value"
            definition="The real, immediate value of an option. For CE: max(Spot − Strike, 0). For PE: max(Strike − Spot, 0). OTM options have zero intrinsic value."
          />
          <TermCard
            term="Time Value"
            definition="Premium − Intrinsic Value. Represents the probability of the option becoming profitable before expiry. Decays as expiry approaches (theta decay)."
          />
          <TermCard
            term="Basis (Futures − Spot)"
            definition="The difference between the futures price and the spot price. Positive basis (contango) is normal; converges to zero at expiry."
          />
          <TermCard
            term="VIX (India VIX)"
            definition="NSE's volatility index — a real-time measure of market fear. Derived from NIFTY options. Higher VIX = costlier options, higher uncertainty."
          />
        </div>
      </section>

      <SectionDivider />

      {/* ── Section 3: The Greeks ─────────────────────────────────────────────── */}
      <section className="space-y-5">
        <SectionHeading
          icon={Zap}
          title="The Greeks — Explained Simply"
          subtitle="How option prices respond to changes in market conditions"
        />

        <div className="overflow-x-auto rounded-md border border-[var(--color-border)]">
          <table className="w-full text-xs min-w-[600px]">
            <thead className="border-b border-[var(--color-border)] bg-[var(--color-surface-2)]">
              <tr className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)]">
                <th className="px-4 py-3 text-left font-semibold">Greek</th>
                <th className="px-4 py-3 text-left font-semibold">Symbol</th>
                <th className="px-4 py-3 text-left font-semibold">Measures</th>
                <th className="px-4 py-3 text-left font-semibold">Typical Range</th>
                <th className="px-4 py-3 text-left font-semibold">Practical Meaning</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--color-border)]">
              <tr className="bg-[var(--color-surface)] hover:bg-[var(--color-surface-2)]/60 transition-colors">
                <td className="px-4 py-3 font-semibold text-[var(--color-primary)]">Delta</td>
                <td className="px-4 py-3 text-white font-bold">Δ</td>
                <td className="px-4 py-3 text-[var(--color-text-muted)]">Price sensitivity</td>
                <td className="px-4 py-3 text-[var(--color-text-muted)]">0 to 1 (CE) · −1 to 0 (PE)</td>
                <td className="px-4 py-3 text-[var(--color-text-muted)]">₹ change in option price for every ₹1 move in the underlying spot</td>
              </tr>
              <tr className="bg-[var(--color-surface)] hover:bg-[var(--color-surface-2)]/60 transition-colors">
                <td className="px-4 py-3 font-semibold text-[var(--color-primary)]">Gamma</td>
                <td className="px-4 py-3 text-white font-bold">Γ</td>
                <td className="px-4 py-3 text-[var(--color-text-muted)]">Rate of delta change</td>
                <td className="px-4 py-3 text-[var(--color-text-muted)]">Small positive</td>
                <td className="px-4 py-3 text-[var(--color-text-muted)]">Acceleration of delta — highest for ATM options, spikes near expiry</td>
              </tr>
              <tr className="bg-[var(--color-surface)] hover:bg-[var(--color-surface-2)]/60 transition-colors">
                <td className="px-4 py-3 font-semibold text-[var(--color-danger)]">Theta</td>
                <td className="px-4 py-3 text-white font-bold">Θ</td>
                <td className="px-4 py-3 text-[var(--color-text-muted)]">Time decay</td>
                <td className="px-4 py-3 text-[var(--color-text-muted)]">Negative</td>
                <td className="px-4 py-3 text-[var(--color-text-muted)]">Daily premium lost due to passage of time — the buyer&apos;s enemy, the seller&apos;s friend</td>
              </tr>
              <tr className="bg-[var(--color-surface)] hover:bg-[var(--color-surface-2)]/60 transition-colors">
                <td className="px-4 py-3 font-semibold text-[var(--color-primary)]">Vega</td>
                <td className="px-4 py-3 text-white font-bold">ν</td>
                <td className="px-4 py-3 text-[var(--color-text-muted)]">IV sensitivity</td>
                <td className="px-4 py-3 text-[var(--color-text-muted)]">Positive</td>
                <td className="px-4 py-3 text-[var(--color-text-muted)]">How much premium changes for every 1% move in implied volatility</td>
              </tr>
              <tr className="bg-[var(--color-surface)] hover:bg-[var(--color-surface-2)]/60 transition-colors">
                <td className="px-4 py-3 font-semibold text-[var(--color-text-muted)]">Rho</td>
                <td className="px-4 py-3 text-white font-bold">ρ</td>
                <td className="px-4 py-3 text-[var(--color-text-muted)]">Interest rate sensitivity</td>
                <td className="px-4 py-3 text-[var(--color-text-muted)]">Small</td>
                <td className="px-4 py-3 text-[var(--color-text-muted)]">Least impactful Greek for short-term traders; relevant for LEAPS / long-dated contracts</td>
              </tr>
            </tbody>
          </table>
        </div>

        <div className="rounded-md border border-[var(--color-border)] bg-[var(--color-surface-2)] p-3 flex items-start gap-2">
          <AlertCircle size={13} className="mt-0.5 shrink-0 text-[var(--color-warning)]" />
          <p className="text-xs text-[var(--color-text-muted)] leading-relaxed">
            <span className="text-white font-medium">Quick rule of thumb: </span>
            ATM options have Delta ≈ 0.5. Deep ITM Delta approaches 1 (CE) or −1 (PE). Deep OTM approaches 0.
            Gamma and Theta are highest at ATM and near expiry — use with caution in the last week.
          </p>
        </div>
      </section>

      <SectionDivider />

      {/* ── Section 4: Reading the Option Chain ──────────────────────────────── */}
      <section className="space-y-5">
        <SectionHeading
          icon={BarChart2}
          title="Reading the Option Chain"
          subtitle="How to interpret NSE's option chain table"
        />

        {/* Chain layout visual */}
        <div className="rounded-md border border-[var(--color-border)] bg-[var(--color-surface-2)] overflow-x-auto">
          <div className="min-w-[420px] text-xs">
            {/* Header */}
            <div className="grid grid-cols-3 border-b border-[var(--color-border)]">
              <div className="px-4 py-2.5 text-center text-[10px] font-semibold tracking-wider text-[var(--color-success)] bg-[var(--color-success)]/10 uppercase">
                CALLS (CE)
              </div>
              <div className="px-4 py-2.5 text-center text-[10px] font-semibold tracking-wider text-white bg-[var(--color-surface)] uppercase">
                Strike
              </div>
              <div className="px-4 py-2.5 text-center text-[10px] font-semibold tracking-wider text-[var(--color-danger)] bg-[var(--color-danger)]/10 uppercase">
                PUTS (PE)
              </div>
            </div>
            {/* Sub-headers */}
            <div className="grid grid-cols-3 border-b border-[var(--color-border)] text-[10px] text-[var(--color-text-muted)]">
              <div className="px-4 py-1.5 text-center">OI · Vol · IV · LTP · Delta</div>
              <div className="px-4 py-1.5 text-center font-bold text-[var(--color-primary)]">↑ ATM ↓</div>
              <div className="px-4 py-1.5 text-center">Delta · LTP · IV · Vol · OI</div>
            </div>
            {/* Sample rows */}
            {[
              { strike: "24,800", atm: false },
              { strike: "24,850", atm: true },
              { strike: "24,900", atm: false },
            ].map((r) => (
              <div
                key={r.strike}
                className={cn(
                  "grid grid-cols-3 border-b border-[var(--color-border)] text-[11px]",
                  r.atm ? "bg-[var(--color-primary)]/10" : "",
                )}
              >
                <div className="px-4 py-2 text-center text-[var(--color-success)]">
                  {r.atm ? "3.2L · 45K · 14.2% · ₹182 · 0.51" : "— · — · — · — · —"}
                </div>
                <div
                  className={cn(
                    "px-4 py-2 text-center font-bold tnum",
                    r.atm ? "text-[var(--color-primary)]" : "text-white",
                  )}
                >
                  {r.strike}
                  {r.atm && <span className="ml-1 text-[9px] font-normal">ATM</span>}
                </div>
                <div className="px-4 py-2 text-center text-[var(--color-danger)]">
                  {r.atm ? "−0.49 · ₹178 · 14.5% · 38K · 2.9L" : "— · — · — · — · —"}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Interpretation notes */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <div className="rounded-md border border-[var(--color-border)] bg-[var(--color-surface-2)] p-3 space-y-1">
            <div className="text-xs font-semibold text-white flex items-center gap-1">
              <BarChart2 size={12} className="text-[var(--color-primary)]" />
              High OI at a Strike
            </div>
            <p className="text-xs text-[var(--color-text-muted)] leading-relaxed">
              Signals a strong support (high PE OI) or resistance (high CE OI) level. Market tends to pin near these strikes.
            </p>
          </div>
          <div className="rounded-md border border-[var(--color-border)] bg-[var(--color-surface-2)] p-3 space-y-1">
            <div className="text-xs font-semibold text-white flex items-center gap-1">
              <Target size={12} className="text-[var(--color-primary)]" />
              Max Pain Strike
            </div>
            <p className="text-xs text-[var(--color-text-muted)] leading-relaxed">
              The strike where option writers (sellers) collectively lose the least. Spot price often gravitates here on expiry day.
            </p>
          </div>
          <div className="rounded-md border border-[var(--color-border)] bg-[var(--color-surface-2)] p-3 space-y-1">
            <div className="text-xs font-semibold text-white flex items-center gap-1">
              <TrendingUp size={12} className="text-[var(--color-primary)]" />
              PCR Interpretation
            </div>
            <p className="text-xs text-[var(--color-text-muted)] leading-relaxed">
              PCR &gt; 1.2 = Bullish (heavy put selling). PCR &lt; 0.8 = Bearish (heavy call selling). 0.8–1.2 = Neutral range.
            </p>
          </div>
        </div>
      </section>

      <SectionDivider />

      {/* ── Section 5: Common Strategies ─────────────────────────────────────── */}
      <section className="space-y-5">
        <SectionHeading
          icon={Shield}
          title="Common F&O Strategies"
          subtitle="Six widely-used strategies with risk/reward profiles"
        />

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          <StrategyCard
            name="Long Call"
            risk="Limited — max loss = premium paid"
            reward="Unlimited upside as price rises"
            when="Strongly bullish on the underlying"
            riskType="low"
          />
          <StrategyCard
            name="Long Put"
            risk="Limited — max loss = premium paid"
            reward="High reward as price falls (down to zero)"
            when="Strongly bearish on the underlying"
            riskType="low"
          />
          <StrategyCard
            name="Straddle"
            risk="Fixed cost — premium of CE + PE bought"
            reward="Unlimited on either side of the strike"
            when="Expecting a large move; direction unknown"
            riskType="medium"
          />
          <StrategyCard
            name="Iron Condor"
            risk="Limited — defined max loss at setup"
            reward="Limited — net premium collected"
            when="Range-bound market; low volatility expected"
            riskType="medium"
          />
          <StrategyCard
            name="Bull Call Spread"
            risk="Lower cost than a plain long call"
            reward="Capped at the spread width minus debit"
            when="Mildly bullish; want to reduce premium cost"
            riskType="low"
          />
          <StrategyCard
            name="Covered Call"
            risk="Reduces holding cost; stock still has downside"
            reward="Premium collected; upside capped at strike"
            when="Holding stock; neutral to mildly bearish view"
            riskType="medium"
          />
        </div>
      </section>

      <SectionDivider />

      {/* ── Section 6: India VIX Explained ───────────────────────────────────── */}
      <section className="space-y-5">
        <SectionHeading
          icon={AlertCircle}
          title="India VIX Explained"
          subtitle="NSE's fear gauge — how to interpret each zone"
        />

        <div className="space-y-3">
          <VixRow
            range="VIX &lt; 15"
            label="Low Fear"
            description="Market is complacent. Options are cheap. A good time to buy options (low premium). Beware of sudden spikes that could catch sellers off-guard."
            badgeVariant="success"
          />
          <VixRow
            range="VIX 15–20"
            label="Normal"
            description="Balanced risk environment. Both buying and selling strategies are viable. Markets are functioning with typical uncertainty."
            badgeVariant="info"
          />
          <VixRow
            range="VIX 20–25"
            label="Elevated Fear"
            description="Options are expensive due to elevated premium. Selling strategies (iron condor, covered call, straddle) tend to be more rewarding. Expect wider bid-ask spreads."
            badgeVariant="warning"
          />
          <VixRow
            range="VIX &gt; 25"
            label="High Fear"
            description="Very wide premiums. Market is in panic mode. Extreme caution advised. Avoid over-leveraged positions. Buying options is expensive but sellers face unlimited risk in volatile swings."
            badgeVariant="danger"
          />
        </div>

        <div className="rounded-md border border-[var(--color-border)] bg-[var(--color-surface-2)] p-3 flex items-start gap-2">
          <Info size={13} className="mt-0.5 shrink-0 text-[var(--color-primary)]" />
          <p className="text-xs text-[var(--color-text-muted)] leading-relaxed">
            India VIX is calculated using NIFTY option bid-ask quotes and represents expected 30-day annualised volatility.
            Unlike US VIX (which uses S&P 500), India VIX is a forward-looking estimate and resets after each expiry.
          </p>
        </div>
      </section>

      <SectionDivider />

      {/* ── Section 7: NSE F&O Quick Facts ───────────────────────────────────── */}
      <section className="space-y-5">
        <SectionHeading
          icon={Clock}
          title="NSE F&O Quick Facts"
          subtitle="Essential operational details for Indian markets"
        />

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div className="rounded-md border border-[var(--color-border)] bg-[var(--color-surface-2)] p-4 space-y-3">
            <div className="text-xs font-semibold text-white uppercase tracking-wider">Expiry Schedule</div>
            <div className="space-y-2 text-xs text-[var(--color-text-muted)]">
              <div className="flex justify-between">
                <span>Index weekly expiry</span>
                <span className="text-white">Last Thursday of each week</span>
              </div>
              <div className="flex justify-between">
                <span>Index monthly expiry</span>
                <span className="text-white">Last Thursday of the month</span>
              </div>
              <div className="flex justify-between">
                <span>Stock F&O expiry</span>
                <span className="text-white">Last Thursday of the month</span>
              </div>
            </div>
          </div>

          <div className="rounded-md border border-[var(--color-border)] bg-[var(--color-surface-2)] p-4 space-y-3">
            <div className="text-xs font-semibold text-white uppercase tracking-wider">Lot Sizes</div>
            <div className="space-y-2 text-xs text-[var(--color-text-muted)]">
              {[
                { sym: "NIFTY", lot: "75 units" },
                { sym: "BANKNIFTY", lot: "15 units" },
                { sym: "FINNIFTY", lot: "40 units" },
              ].map((item) => (
                <div key={item.sym} className="flex justify-between">
                  <span className="font-medium text-[var(--color-primary)]">{item.sym}</span>
                  <span className="text-white tnum">{item.lot}</span>
                </div>
              ))}
              <p className="text-[10px] pt-1 italic">Lot sizes revised periodically by NSE based on underlying price.</p>
            </div>
          </div>

          <div className="rounded-md border border-[var(--color-border)] bg-[var(--color-surface-2)] p-4 space-y-3">
            <div className="text-xs font-semibold text-white uppercase tracking-wider">Settlement</div>
            <div className="space-y-2 text-xs text-[var(--color-text-muted)]">
              <div className="flex justify-between">
                <span>Index options</span>
                <span className="text-[var(--color-success)]">Cash settled</span>
              </div>
              <div className="flex justify-between">
                <span>Stock options (ITM)</span>
                <span className="text-[var(--color-warning)]">Physical delivery</span>
              </div>
              <div className="flex justify-between">
                <span>Futures</span>
                <span className="text-[var(--color-success)]">Cash / Physical (stock)</span>
              </div>
            </div>
          </div>

          <div className="rounded-md border border-[var(--color-border)] bg-[var(--color-surface-2)] p-4 space-y-3">
            <div className="text-xs font-semibold text-white uppercase tracking-wider">Trading Hours</div>
            <div className="space-y-2 text-xs text-[var(--color-text-muted)]">
              <div className="flex justify-between">
                <span>F&O market open</span>
                <span className="text-white tnum">9:15 AM IST</span>
              </div>
              <div className="flex justify-between">
                <span>F&O market close</span>
                <span className="text-white tnum">3:30 PM IST</span>
              </div>
              <div className="flex justify-between">
                <span>Pre-open session</span>
                <span className="text-white tnum">9:00 – 9:15 AM IST</span>
              </div>
              <p className="text-[10px] pt-1 italic">No extended hours for F&O on NSE.</p>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
