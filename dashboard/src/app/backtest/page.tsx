"use client";

import { BacktestReport } from "@/components/backtest-report";
import { EngineOffline } from "@/components/engine-offline";
import { Skeleton } from "@/components/ui/skeleton";
import { useEngine } from "@/lib/api";
import type { BacktestRun, CandleHistorySummary } from "@/lib/types";

export default function BacktestPage() {
  const latest = useEngine<BacktestRun | null>("/api/backtests/latest", 0);
  const history = useEngine<CandleHistorySummary>("/api/candles/summary", 0);

  if (latest.error) return <EngineOffline error={latest.error} />;
  if (latest.isLoading && latest.data === undefined) return <Skeleton className="h-40 w-full" />;

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
        <BacktestReport
          run={latest.data ?? null}
          history={history.data}
          onRan={() => void latest.mutate()}
          onHistoryChange={() => void history.mutate()}
        />
      </div>
    </div>
  );
}
