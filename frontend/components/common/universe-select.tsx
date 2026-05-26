"use client";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from "@/components/ui/select";

export function UniverseSelect({
  value, onChange, className,
}: {
  value: string;
  onChange: (v: string) => void;
  className?: string;
}) {
  const { data, isLoading } = useQuery({
    queryKey: ["universe-list"],
    queryFn: api.listUniverses,
    staleTime: 60 * 60_000,
  });
  const items = Object.keys(data ?? {});
  return (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger className={className} aria-label="Select universe">
        <SelectValue placeholder={isLoading ? "Loading…" : "Select universe"} />
      </SelectTrigger>
      <SelectContent>
        {items.length === 0 && (
          <div className="px-2 py-1.5 text-xs muted">No universes</div>
        )}
        {items.map((u) => (
          <SelectItem key={u} value={u}>{u}</SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
