"use client";

import { EngineOffline } from "@/components/engine-offline";
import { LiveTradingWatch } from "@/components/live-trading-watch";
import { TradingControls } from "@/components/trading-controls";
import { Skeleton } from "@/components/ui/skeleton";
import { useEngine } from "@/lib/api";
import type { OrderRow, Portfolio, SignalRow, Status } from "@/lib/types";

export default function TradingPage() {
  const status = useEngine<Status>("/api/status", 2000);
  const portfolio = useEngine<Portfolio>("/api/portfolio", 2500);
  const signals = useEngine<SignalRow[]>("/api/signals?limit=40", 2500);
  const trades = useEngine<OrderRow[]>("/api/trades?limit=60", 2000);

  if (status.error || portfolio.error) {
    return <EngineOffline error={status.error ?? portfolio.error} />;
  }

  if (!status.data || !portfolio.data) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  const refresh = () => {
    void status.mutate();
    void portfolio.mutate();
    void signals.mutate();
    void trades.mutate();
  };

  return (
    <div className="space-y-6">
      <header>
        <h1 className="font-heading text-2xl font-semibold tracking-wide text-[var(--amber)]">
          Trading
        </h1>
        <p className="mt-1 font-mono text-xs text-muted-foreground">
          Start or stop the paper auto-trading loop and watch fills live. Engine Start/Stop in the
          header only controls the API and market/news services.
        </p>
      </header>

      <TradingControls status={status.data} onChanged={refresh} />

      <LiveTradingWatch
        portfolio={portfolio.data}
        signals={signals.data ?? []}
        trades={trades.data ?? []}
        heartbeat={status.data.heartbeat}
        tradingEnabled={Boolean(status.data.trading?.enabled)}
      />
    </div>
  );
}
