"use client";

import { EngineOffline } from "@/components/engine-offline";
import { OrdersTable } from "@/components/orders-table";
import { Skeleton } from "@/components/ui/skeleton";
import { useEngine } from "@/lib/api";
import type { OrderRow } from "@/lib/types";

export default function TradesPage() {
  const { data, error, isLoading } = useEngine<OrderRow[]>("/api/trades?limit=200", 5000);

  if (error) return <EngineOffline error={error} />;
  if (isLoading && !data) return <Skeleton className="h-40 w-full" />;

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
        <OrdersTable rows={data ?? []} />
      </div>
    </div>
  );
}
