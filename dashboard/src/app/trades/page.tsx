"use client";

import { EngineOffline } from "@/components/engine-offline";
import { OrdersTable } from "@/components/orders-table";
import { TradesEmpty } from "@/components/trades-empty";
import { Skeleton } from "@/components/ui/skeleton";
import { useEngine } from "@/lib/api";
import type { OrderRow, SignalRow, Status } from "@/lib/types";

export default function TradesPage() {
  const trades = useEngine<OrderRow[]>("/api/trades?limit=200", 5000);
  const status = useEngine<Status>("/api/status", 5000);
  const signals = useEngine<SignalRow[]>("/api/signals?limit=30", 8000);

  if (trades.error) return <EngineOffline error={trades.error} />;
  if (trades.isLoading && !trades.data) return <Skeleton className="h-40 w-full" />;

  const rows = trades.data ?? [];

  return (
    <div className="space-y-4">
      <header>
        <h1 className="font-heading text-2xl font-semibold tracking-wide text-[var(--amber)]">
          Trades
        </h1>
        <p className="mt-1 font-mono text-xs text-muted-foreground">
          Paper order log including risk rejections
        </p>
      </header>
      <div className="border border-border bg-[#0c0c0c] p-3">
        {rows.length === 0 ? (
          <TradesEmpty status={status.data} signals={signals.data} />
        ) : (
          <OrdersTable rows={rows} />
        )}
      </div>
    </div>
  );
}
