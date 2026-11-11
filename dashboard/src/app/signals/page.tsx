"use client";

import { EngineOffline } from "@/components/engine-offline";
import { SignalList } from "@/components/signal-list";
import { Skeleton } from "@/components/ui/skeleton";
import { useEngine } from "@/lib/api";
import type { SignalRow } from "@/lib/types";

export default function SignalsPage() {
  const { data, error, isLoading } = useEngine<SignalRow[]>("/api/signals?limit=100", 5000);

  if (error) return <EngineOffline error={error} />;
  if (isLoading && !data) return <Skeleton className="h-40 w-full" />;

  return (
    <div className="space-y-4">
      <header>
        <h1 className="font-heading text-2xl font-semibold tracking-wide text-[var(--amber)]">
          Signals
        </h1>
        <p className="mt-1 font-mono text-xs text-muted-foreground">
          Every evaluated bar with reasons, indicators and news state
        </p>
      </header>
      <SignalList rows={data ?? []} />
    </div>
  );
}
