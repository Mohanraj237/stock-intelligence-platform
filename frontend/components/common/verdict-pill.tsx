import { Badge } from "@/components/ui/badge";
import type { Verdict } from "@/lib/types";

const MAP: Record<Verdict, "success" | "info" | "warning" | "danger" | "default"> = {
  STRONG_BUY:  "success",
  BUY:         "success",
  HOLD:        "info",
  NEUTRAL:     "default",
  SELL:        "warning",
  STRONG_SELL: "danger",
};

const LABEL: Record<Verdict, string> = {
  STRONG_BUY:  "Strong Buy",
  BUY:         "Buy",
  HOLD:        "Hold",
  NEUTRAL:     "Neutral",
  SELL:        "Sell",
  STRONG_SELL: "Strong Sell",
};

export function VerdictPill({ verdict }: { verdict: Verdict | string }) {
  const v = (verdict || "NEUTRAL") as Verdict;
  return <Badge variant={MAP[v] ?? "default"}>{LABEL[v] ?? v}</Badge>;
}
