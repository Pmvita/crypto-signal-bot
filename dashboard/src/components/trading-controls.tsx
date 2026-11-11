"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { engineErrorMessage, startTrading, stopTrading } from "@/lib/api";
import type { Status } from "@/lib/types";
import { cn } from "@/lib/utils";

export function TradingControls({
  status,
  onChanged,
}: {
  status: Status | undefined;
  onChanged?: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const enabled = Boolean(status?.trading?.enabled);
  const engineUp = Boolean(status);

  const toggle = async (next: boolean) => {
    setBusy(true);
    setError(null);
    try {
      if (next) await startTrading();
      else await stopTrading();
      onChanged?.();
    } catch (err) {
      setError(engineErrorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-3 border border-border bg-[#0c0c0c] p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="space-y-1">
          <div className="font-mono text-[11px] uppercase tracking-[0.16em] text-muted-foreground">
            Paper trading loop
          </div>
          <div
            className={cn(
              "font-mono text-sm tracking-wide",
              !engineUp
                ? "text-[var(--loss)]"
                : enabled
                  ? "text-[var(--gain)]"
                  : "text-muted-foreground",
            )}
          >
            {!engineUp
              ? "Engine offline — start the engine first"
              : enabled
                ? "Running — evaluating bars and placing paper orders"
                : "Stopped — market/news still refresh; no ENTER/EXIT"}
          </div>
          {status?.trading?.note ? (
            <p className="max-w-xl font-mono text-[11px] text-muted-foreground">{status.trading.note}</p>
          ) : null}
        </div>
        <div className="flex flex-wrap gap-2">
          {enabled ? (
            <Button
              type="button"
              size="lg"
              variant="outline"
              className="min-w-[10rem] font-mono"
              disabled={busy || !engineUp}
              onClick={() => void toggle(false)}
            >
              Stop trading
            </Button>
          ) : (
            <Button
              type="button"
              size="lg"
              className="min-w-[10rem] font-mono bg-[var(--amber)] text-black hover:bg-[var(--amber)]/90"
              disabled={busy || !engineUp}
              onClick={() => void toggle(true)}
            >
              Start trading
            </Button>
          )}
        </div>
      </div>
      {error ? <p className="font-mono text-xs text-[var(--loss)]">{error}</p> : null}
      <p className="font-mono text-[10px] text-muted-foreground">
        Stopping the loop or the engine does not reset the paper portfolio. Trading starts stopped
        after each engine restart.
      </p>
    </div>
  );
}
