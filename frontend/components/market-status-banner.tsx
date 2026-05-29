"use client";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { formatPct, formatNum, trendClass } from "@/lib/utils";
import { Activity, Circle } from "lucide-react";
import { useRegion } from "@/lib/region";

export function MarketStatusBanner() {
  const { region, isUS } = useRegion();

  const { data, isLoading } = useQuery({
    queryKey: ["marketStatus", region],
    queryFn: () => api.marketStatus(region),
    refetchInterval: 60_000,
  });

  if (isLoading) {
    return <div className="h-12 rounded-md bg-[var(--color-surface)] animate-pulse" />;
  }
  if (!data) return null;

  const primaryLabel = isUS ? "S&P 500" : "NIFTY";
  const secondaryLabel = isUS ? "NASDAQ" : "GIFT";

  return (
    <div className="rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-2.5 flex items-center gap-6 text-xs">
      <div className="flex items-center gap-2">
        <Circle className={`size-2.5 fill-current ${data.is_open ? "up" : "down"}`} />
        <span className="font-medium text-white">{data.is_open ? "Market Open" : "Market Closed"}</span>
        {data.trade_date && <span className="muted">· {data.trade_date}</span>}
      </div>
      {data.nifty != null && (
        <div className="flex items-center gap-2">
          <span className="muted">{primaryLabel}</span>
          <span className="font-medium text-white tnum">{formatNum(data.nifty)}</span>
          {data.nifty_change_pct != null && (
            <span className={`tnum ${trendClass(data.nifty_change_pct)}`}>
              {formatPct(data.nifty_change_pct, { sign: true })}
            </span>
          )}
        </div>
      )}
      {!isUS && data.market_cap_lakh_cr != null && (
        <div className="flex items-center gap-2">
          <span className="muted">Mcap</span>
          <span className="tnum">₹{formatNum(data.market_cap_lakh_cr, { maxFrac: 1 })} L Cr</span>
        </div>
      )}
      {data.gift_nifty != null && (
        <div className="flex items-center gap-2">
          <Activity className="size-3 muted" />
          <span className="muted">{secondaryLabel}</span>
          <span className="tnum">{formatNum(data.gift_nifty)}</span>
          {data.gift_nifty_change_pct != null && (
            <span className={`tnum ${trendClass(data.gift_nifty_change_pct)}`}>
              {formatPct(data.gift_nifty_change_pct, { sign: true })}
            </span>
          )}
        </div>
      )}
      <Badge variant="info" className="ml-auto">
        {isUS ? "🇺🇸 US" : "🇮🇳 India"} · v2.0
      </Badge>
    </div>
  );
}
