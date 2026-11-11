"use client";

import { ShellEngineControls } from "@/components/shell-engine-controls";
import { useEngine } from "@/lib/api";
import { useElectronShell } from "@/lib/csb-shell";
import { ago } from "@/lib/format";
import type { Status } from "@/lib/types";
import { cn } from "@/lib/utils";

function cycleBlurb(status: Status | undefined): string {
  const tradingOn = Boolean(status?.trading?.enabled);
  const hb = status?.heartbeat;
  if (!tradingOn) {
    return "Engine services only — paper trading is stopped. Open Trading to start the loop.";
  }
  if (!hb) return "Trading on — waiting for the first evaluate cycle.";
  const summary = hb.summary;
  if (!summary) {
    return hb.error
      ? `Cycle #${hb.id} ${hb.status}: ${hb.error}`
      : `Cycle #${hb.id} · ${hb.status}`;
  }
  const signals = Array.isArray(summary.signals) ? summary.signals.length : 0;
  const orders = Array.isArray(summary.orders) ? summary.orders.length : 0;
  const skipped = Array.isArray(summary.skipped) ? summary.skipped.length : 0;
  const candles = summary.candles_added
    ? Object.values(summary.candles_added).reduce((a, n) => a + (Number(n) || 0), 0)
    : 0;
  if (signals === 0 && orders === 0 && skipped === 0) {
    return `Cycle #${hb.id} · ${hb.status} · quotes refreshed · waiting for next 15m signal bar`;
  }
  return `Cycle #${hb.id} · ${hb.status} · +${candles} bars · ${signals} signals · ${orders} orders · ${skipped} skipped`;
}

export function EngineControlStrip() {
  const electron = useElectronShell();
  const { data, error } = useEngine<Status>("/api/status", 3000);
  const hb = data?.heartbeat;
  const reachable = Boolean(data) && !error;

  return (
    <div className="border-b border-border bg-[#0d0d0d] px-4 py-3">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div className="min-w-0 space-y-1">
          <div className="flex flex-wrap items-center gap-2 font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
            <span className="text-[var(--amber)]">Engine</span>
            <span className="text-border">·</span>
            <span
              className={cn(
                reachable ? "text-[var(--gain)]" : "text-[var(--loss)]",
              )}
            >
              {reachable ? "API reachable" : "API offline"}
            </span>
            {data?.trading ? (
              <>
                <span className="text-border">·</span>
                <span
                  className={
                    data.trading.enabled ? "text-[var(--gain)]" : "text-muted-foreground"
                  }
                >
                  trading {data.trading.enabled ? "on" : "off"}
                </span>
              </>
            ) : null}
            {hb && data?.trading?.enabled ? (
              <>
                <span className="text-border">·</span>
                <span
                  className={
                    hb.status === "ok"
                      ? "text-[var(--gain)]"
                      : hb.status === "running"
                        ? "text-[var(--amber)]"
                        : "text-[var(--loss)]"
                  }
                >
                  heartbeat {hb.status} · {ago(hb.finished_at ?? hb.started_at)}
                </span>
              </>
            ) : null}
          </div>
          <p className="truncate font-mono text-xs text-muted-foreground">{cycleBlurb(data)}</p>
          {!electron ? (
            <p className="font-mono text-[10px] text-muted-foreground">
              Browser mode: Engine Start/Stop is disabled — use the desktop app, or{" "}
              <code className="text-[var(--amber)]">python -m csb serve</code>. Paper trading
              controls live on the Trading page.
            </p>
          ) : null}
        </div>
        <div className="flex flex-wrap items-center gap-3">
          {!electron && reachable ? (
            <div className="flex items-center gap-2 font-mono text-xs tracking-wide text-[var(--gain)]">
              <span
                className="inline-block size-2 rounded-full bg-[var(--gain)] shadow-[0_0_8px_var(--gain)]"
                aria-hidden
              />
              Running via serve
            </div>
          ) : null}
          <ShellEngineControls variant="strip" />
        </div>
      </div>
    </div>
  );
}
