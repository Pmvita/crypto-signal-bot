"use client";

import { BacktestReport } from "@/components/backtest-report";
import { EngineOffline } from "@/components/engine-offline";
import { Skeleton } from "@/components/ui/skeleton";
import { useEngine } from "@/lib/api";
import type { BacktestRun } from "@/lib/types";

export default function BacktestPage() {
  const { data, error, isLoading, mutate } = useEngine<BacktestRun | null>(
    "/api/backtests/latest",
    0,
  );

  if (error) return <EngineOffline error={error} />;
  if (isLoading && data === undefined) return <Skeleton className="h-40 w-full" />;

  return (
    <div className="space-y-4">
      <header>
        <h1 className="font-heading text-2xl font-semibold tracking-wide text-[var(--amber)]">
          Backtest
        </h1>
        <p className="mt-1 font-mono text-xs text-muted-foreground">
          Historical replay of price rules on stored candles
        </p>
      </header>
      <div className="border border-border bg-[#0c0c0c] p-4">
        <BacktestReport run={data ?? null} onRan={() => void mutate()} />
      </div>
    </div>
  );
}
