"use client";
import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { PageHeader } from "@/components/common/page-header";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import type { AppSettings, ScoringConfig } from "@/lib/types";
import { DEFAULT_SCORING_CONFIG, scoringWeightsTotal } from "@/lib/types";
import { WeightSlider } from "@/components/scanner/WeightSlider";
import { toast } from "sonner";
import { Eye, EyeOff } from "lucide-react";

export default function SettingsPage() {
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({ queryKey: ["settings"], queryFn: api.settings });
  const [draft, setDraft] = useState<AppSettings | null>(null);
  useEffect(() => { if (data) setDraft(data); }, [data]);

  const m = useMutation({
    mutationFn: (s: Partial<AppSettings>) => api.patchSettings(s),
    onSuccess: (s) => { setDraft(s); qc.invalidateQueries({ queryKey: ["settings"] }); toast.success("Settings saved"); },
    onError: (e) => toast.error(`Save failed: ${(e as Error).message}`),
  });

  if (isLoading || !draft) {
    return <div className="space-y-3"><Skeleton className="h-10 w-1/3" /><Skeleton className="h-72" /></div>;
  }

  const upd = <K extends keyof AppSettings>(k: K, v: AppSettings[K]) => setDraft({ ...draft, [k]: v });

  return (
    <div className="max-w-4xl mx-auto space-y-5">
      <PageHeader
        title="Settings"
        subtitle="Local-only configuration. No data leaves this machine."
        actions={
          <Button onClick={() => m.mutate(draft)} disabled={m.isPending}>
            {m.isPending ? "Saving…" : "Save"}
          </Button>
        }
      />

      <Tabs defaultValue="general">
        <TabsList>
          <TabsTrigger value="general">General</TabsTrigger>
          <TabsTrigger value="data">Data Sources</TabsTrigger>
          <TabsTrigger value="cache">Cache</TabsTrigger>
          <TabsTrigger value="scoring">Scoring</TabsTrigger>
          <TabsTrigger value="ai">AI Agent</TabsTrigger>
        </TabsList>

        <TabsContent value="general">
          <Card>
            <CardHeader><CardTitle>General</CardTitle></CardHeader>
            <CardContent className="grid md:grid-cols-2 gap-4">
              <Field label="Refresh interval (seconds)">
                <Input type="number" min={15} max={3600} value={draft.refresh_interval_sec}
                  onChange={(e) => upd("refresh_interval_sec", Number(e.target.value))} />
              </Field>
              <Field label="Default universe">
                <Input value={draft.default_universe} onChange={(e) => upd("default_universe", e.target.value)} />
              </Field>
              <Field label="Max parallel workers">
                <Input type="number" min={1} max={32} value={draft.max_parallel_workers}
                  onChange={(e) => upd("max_parallel_workers", Number(e.target.value))} />
              </Field>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="data">
          <Card>
            <CardHeader>
              <CardTitle>Screener.in (optional)</CardTitle>
              <p className="text-xs muted mt-1">Provide cookies for richer fundamentals. Leave blank otherwise.</p>
            </CardHeader>
            <CardContent className="grid md:grid-cols-2 gap-4">
              <Field label="Screener CSRF token">
                <Input value={draft.screener_csrf ?? ""} onChange={(e) => upd("screener_csrf", e.target.value)} />
              </Field>
              <Field label="Screener session cookie">
                <Input value={draft.screener_session ?? ""} onChange={(e) => upd("screener_session", e.target.value)} />
              </Field>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="cache">
          <Card>
            <CardHeader><CardTitle>Cache TTLs</CardTitle></CardHeader>
            <CardContent className="grid md:grid-cols-3 gap-4">
              <Field label="Screener (hours)">
                <Input type="number" min={1} max={168} value={draft.screener_cache_ttl_hours}
                  onChange={(e) => upd("screener_cache_ttl_hours", Number(e.target.value))} />
              </Field>
              <Field label="Market data (minutes)">
                <Input type="number" min={1} max={120} value={draft.market_cache_ttl_min}
                  onChange={(e) => upd("market_cache_ttl_min", Number(e.target.value))} />
              </Field>
              <Field label="Universe (hours)">
                <Input type="number" min={1} max={168} value={draft.universe_cache_ttl_hours}
                  onChange={(e) => upd("universe_cache_ttl_hours", Number(e.target.value))} />
              </Field>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="scoring">
          <ScoringTab />
        </TabsContent>

        <TabsContent value="ai">
          <AIAgentTab draft={draft} upd={upd} onSave={() => m.mutate(draft)} saving={m.isPending} />
        </TabsContent>
      </Tabs>
    </div>
  );
}

function ScoringTab() {
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({ queryKey: ["scoring-config"], queryFn: api.scoringConfig });
  const [draft, setDraft] = useState<ScoringConfig | null>(null);
  useEffect(() => { if (data) setDraft(data); }, [data]);

  const save = useMutation({
    mutationFn: (c: Partial<ScoringConfig>) => api.patchScoringConfig(c),
    onSuccess: (c) => { setDraft(c); qc.invalidateQueries({ queryKey: ["scoring-config"] }); toast.success("Scoring weights saved"); },
    onError: (e) => toast.error(`Save failed: ${(e as Error).message}`),
  });
  const reset = useMutation({
    mutationFn: () => api.resetScoringConfig(),
    onSuccess: (c) => { setDraft(c); qc.invalidateQueries({ queryKey: ["scoring-config"] }); toast.success("Reset to defaults"); },
    onError: (e) => toast.error(`Reset failed: ${(e as Error).message}`),
  });

  if (isLoading || !draft) {
    return <Skeleton className="h-96" />;
  }

  const upd = <K extends keyof ScoringConfig>(k: K) => (v: number) => setDraft({ ...draft, [k]: v });
  const total = scoringWeightsTotal(draft);
  const isDefault = JSON.stringify(draft) === JSON.stringify(DEFAULT_SCORING_CONFIG);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Confluence Scoring</CardTitle>
        <p className="text-xs text-muted-foreground mt-1">
          Both scanners (Equity Scanner and F&amp;O Live Scanner) share this scoring engine.
          Adjust how much each category counts toward the 0–100 confluence score — weights are
          automatically rescaled so the total always stays on a 0–100 scale, regardless of what
          they add up to below. Applies to every scan going forward until you change it again.
        </p>
      </CardHeader>
      <CardContent className="space-y-6">
        <div className="grid md:grid-cols-2 gap-6">
          <WeightSlider
            label="Trend / Structure" value={draft.trend_weight} min={0} max={60}
            onChange={upd("trend_weight")}
          />
          <WeightSlider
            label="Momentum" value={draft.momentum_weight} min={0} max={60}
            onChange={upd("momentum_weight")}
          />
          <WeightSlider
            label="Volume confirmation" value={draft.volume_weight} min={0} max={60}
            onChange={upd("volume_weight")}
          />
          <WeightSlider
            label="Candle trigger" value={draft.candle_weight} min={0} max={60}
            onChange={upd("candle_weight")}
          />
          <WeightSlider
            label="Structural bonus" value={draft.structural_weight} min={0} max={30}
            onChange={upd("structural_weight")}
          />
          <WeightSlider
            label="Default qualifying threshold" value={draft.default_threshold} min={40} max={90} step={5}
            onChange={upd("default_threshold")}
            helperText="Scans use this when a page doesn't override it."
          />
        </div>

        <p className="text-sm">
          Configured total: <span className="font-semibold">{total}</span>
          {total !== 100 && (
            <span className="text-muted-foreground"> — auto-normalized to 100 when scoring</span>
          )}
        </p>

        <div className="flex gap-2">
          <Button onClick={() => save.mutate(draft)} disabled={save.isPending}>
            {save.isPending ? "Saving…" : "Save"}
          </Button>
          <Button variant="outline" onClick={() => reset.mutate()} disabled={reset.isPending || isDefault}>
            Reset to defaults
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function AIAgentTab({
  draft,
  upd,
  onSave,
  saving,
}: {
  draft: AppSettings;
  upd: <K extends keyof AppSettings>(k: K, v: AppSettings[K]) => void;
  onSave: () => void;
  saving: boolean;
}) {
  const [show, setShow] = useState(false);
  const key = draft.anthropic_api_key ?? "";
  const hasKey = key.startsWith("sk-ant-");

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Claude AI (Anthropic)</CardTitle>
          <p className="text-xs text-muted-foreground mt-1">
            Powers the F&amp;O AI Advisor feature. Your key is stored locally and never sent anywhere except Anthropic's API.
          </p>
        </CardHeader>
        <CardContent className="space-y-4">
          <Field label="Anthropic API Key">
            <div className="relative">
              <Input
                type={show ? "text" : "password"}
                placeholder="sk-ant-api03-…"
                value={key}
                onChange={(e) => upd("anthropic_api_key", e.target.value)}
                className="pr-10 font-mono text-sm"
              />
              <button
                type="button"
                className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                onClick={() => setShow((s) => !s)}
              >
                {show ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            </div>
          </Field>

          {hasKey && (
            <p className="text-xs text-green-500">Key configured — Claude AI features are active.</p>
          )}
          {key && !hasKey && (
            <p className="text-xs text-yellow-500">Key doesn't look right — should start with <code>sk-ant-</code>.</p>
          )}
          {!key && (
            <p className="text-xs text-muted-foreground">No key set — AI Advisor will return an error until you add one.</p>
          )}

          <div className="rounded-md bg-muted/50 p-4 text-sm space-y-2">
            <p className="font-medium">How to get your API key:</p>
            <ol className="list-decimal list-inside space-y-1 text-muted-foreground text-xs">
              <li>Go to <strong>console.anthropic.com</strong> and sign in (or create a free account).</li>
              <li>Click <strong>API Keys</strong> in the left sidebar.</li>
              <li>Click <strong>Create Key</strong>, give it a name, then copy the <code>sk-ant-…</code> value.</li>
              <li>Paste it in the field above and click <strong>Save</strong>.</li>
            </ol>
            <p className="text-xs text-muted-foreground pt-1">
              New accounts get free credits. Usage is billed per token — a typical F&amp;O analysis costs ~$0.01.
            </p>
          </div>

          <Button onClick={onSave} disabled={saving}>
            {saving ? "Saving…" : "Save"}
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1">
      <Label>{label}</Label>
      {children}
    </div>
  );
}
