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
import type { AppSettings } from "@/lib/types";
import { toast } from "sonner";

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
      </Tabs>
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
