"use client";
import { useEffect, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Trash2, Sliders } from "lucide-react";
import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState, ErrorState } from "@/components/ui/empty-state";
import { Table, THead, TBody, TR, TH, TD } from "@/components/ui/table";
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from "@/components/ui/select";
import { UniverseSelect } from "@/components/common/universe-select";
import { PageHeader } from "@/components/common/page-header";
import type { Rule, RuleCondition, RuleOp } from "@/lib/types";
import { useRegion } from "@/lib/region";
import { toast } from "sonner";

const FIELDS = ["close", "rsi", "adx", "macd_hist", "sma50", "sma200", "pe", "pb", "roe", "roce", "debt_to_equity", "promoter_holding", "sales_growth", "profit_growth"];
const OPS: readonly RuleOp[] = [">", ">=", "<", "<=", "==", "between"] as const;

export default function RulesPage() {
  const qc = useQueryClient();
  const list = useQuery({ queryKey: ["rules"], queryFn: api.listRules });
  const [draft, setDraft] = useState<Rule>({ name: "", conditions: [{ field: "rsi", op: "<", value: 30 }], logic: "AND" });

  const create = useMutation({
    mutationFn: () => api.createRule(draft),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["rules"] }); toast.success("Rule saved"); setDraft({ name: "", conditions: [{ field: "rsi", op: "<", value: 30 }], logic: "AND" }); },
    onError: (e) => toast.error((e as Error).message),
  });
  const remove = useMutation({
    mutationFn: (id: string) => api.deleteRule(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["rules"] }); toast.success("Deleted"); },
  });

  const { region, isUS } = useRegion();
  const [universe, setUniverse] = useState(isUS ? "S&P 500" : "NIFTY 50");
  useEffect(() => { setUniverse(isUS ? "S&P 500" : "NIFTY 50"); }, [isUS]);
  const [selectedRuleIds, setSelectedRuleIds] = useState<string[]>([]);

  const apply = useMutation({
    mutationFn: () => api.applyRules({
      universe, max_symbols: 50, region,
      ruleset: {
        rules: (list.data ?? []).filter((r) => selectedRuleIds.includes(r.id ?? "")),
        cross_logic: "AND",
      },
    }),
    onError: (e) => toast.error((e as Error).message),
  });

  const addCondition = () => setDraft({ ...draft, conditions: [...draft.conditions, { field: "rsi", op: "<", value: 30 }] });
  const updCondition = (i: number, patch: Partial<RuleCondition>) => {
    const next = [...draft.conditions];
    next[i] = { ...next[i], ...patch };
    setDraft({ ...draft, conditions: next });
  };
  const rmCondition = (i: number) => setDraft({ ...draft, conditions: draft.conditions.filter((_, j) => j !== i) });

  return (
    <div className="max-w-6xl mx-auto space-y-5">
      <PageHeader title="Rule Engine" subtitle="Build custom screeners with visual rule conditions." />

      <Card>
        <CardHeader><CardTitle>Create rule</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          <div className="grid md:grid-cols-3 gap-3">
            <div className="md:col-span-2 space-y-1">
              <Label>Rule name</Label>
              <Input value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} placeholder="e.g. Momentum quality" />
            </div>
            <div className="space-y-1">
              <Label>Logic</Label>
              <Select value={draft.logic} onValueChange={(v) => setDraft({ ...draft, logic: v as "AND" | "OR" })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="AND">AND</SelectItem>
                  <SelectItem value="OR">OR</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          <div>
            <Label>Conditions ({draft.conditions.length})</Label>
            <div className="space-y-2 mt-1">
              {draft.conditions.map((c, i) => (
                <div key={i} className="flex flex-wrap items-center gap-2">
                  <Select value={c.field} onValueChange={(v) => updCondition(i, { field: v })}>
                    <SelectTrigger className="w-44"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {FIELDS.map((f) => <SelectItem key={f} value={f}>{f}</SelectItem>)}
                    </SelectContent>
                  </Select>
                  <Select value={c.op} onValueChange={(v) => updCondition(i, { op: v as RuleOp })}>
                    <SelectTrigger className="w-28"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {OPS.map((o) => <SelectItem key={o} value={o}>{o}</SelectItem>)}
                    </SelectContent>
                  </Select>
                  <Input
                    aria-label="Value"
                    className="w-32"
                    type="number"
                    value={String(c.value)}
                    onChange={(e) => updCondition(i, { value: Number(e.target.value) })}
                  />
                  {c.op === "between" && (
                    <Input
                      aria-label="To"
                      className="w-32"
                      type="number"
                      value={String(c.value2 ?? "")}
                      onChange={(e) => updCondition(i, { value2: Number(e.target.value) })}
                    />
                  )}
                  <Button type="button" variant="ghost" size="icon" aria-label="Remove condition" onClick={() => rmCondition(i)}>
                    <Trash2 className="size-3.5" />
                  </Button>
                </div>
              ))}
            </div>
            <Button type="button" variant="outline" size="sm" className="mt-3" onClick={addCondition}>
              + Add condition
            </Button>
          </div>

          <Button onClick={() => create.mutate()} disabled={!draft.name.trim() || draft.conditions.length === 0 || create.isPending}>
            {create.isPending ? "Saving…" : "Save rule"}
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Saved rules</CardTitle></CardHeader>
        <CardContent>
          {list.isLoading ? <Skeleton className="h-32" /> :
            list.error ? <ErrorState message={(list.error as Error).message} /> :
            !(list.data ?? []).length ? <EmptyState icon={Sliders} title="No rules yet" /> : (
              <ul className="space-y-2">
                {(list.data ?? []).map((r) => (
                  <li key={r.id} className="flex items-center justify-between gap-3 p-2 rounded border border-[var(--color-border)]">
                    <label className="flex items-center gap-2 flex-1 min-w-0">
                      <input
                        type="checkbox"
                        aria-label={`Select rule ${r.name}`}
                        checked={selectedRuleIds.includes(r.id ?? "")}
                        onChange={(e) => setSelectedRuleIds(e.target.checked ? [...selectedRuleIds, r.id ?? ""] : selectedRuleIds.filter((x) => x !== r.id))}
                      />
                      <span className="font-medium text-white">{r.name}</span>
                      <Badge variant="default">{r.logic}</Badge>
                      <span className="text-xs muted truncate">{r.conditions?.length ?? 0} conditions</span>
                    </label>
                    <Button variant="ghost" size="icon" aria-label="Delete rule" onClick={() => remove.mutate(r.id ?? "")}>
                      <Trash2 className="size-3.5" />
                    </Button>
                  </li>
                ))}
              </ul>
            )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Apply rules</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center gap-3">
            <UniverseSelect value={universe} onChange={setUniverse} />
            <Button onClick={() => apply.mutate()} disabled={selectedRuleIds.length === 0 || apply.isPending}>
              {apply.isPending ? "Applying…" : `Apply ${selectedRuleIds.length} rule${selectedRuleIds.length !== 1 ? "s" : ""}`}
            </Button>
          </div>
          {apply.isPending && <Skeleton className="h-40" />}
          {apply.data && (
            apply.data.length === 0 ? <EmptyState title="No matches" /> : (
              <Table>
                <THead><TR>
                  <TH>Symbol</TH>
                  <TH className="text-right">Price</TH>
                  <TH>Rules passed</TH>
                </TR></THead>
                <TBody>
                  {apply.data.map((m) => (
                    <TR key={m.symbol}>
                      <TD className="font-medium text-white">{m.symbol}</TD>
                      <TD className="text-right tnum">{m.last_price ?? "—"}</TD>
                      <TD>
                        <div className="flex flex-wrap gap-1">
                          {m.rules_passed.map((p, i) => <Badge key={i} variant="success">{p}</Badge>)}
                        </div>
                      </TD>
                    </TR>
                  ))}
                </TBody>
              </Table>
            )
          )}
        </CardContent>
      </Card>
    </div>
  );
}
