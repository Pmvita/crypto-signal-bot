"use client";

import { useEffect, useRef, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { PositionsTable } from "@/components/positions-table";
import { SignalList } from "@/components/signal-list";
import { ago, pnlClass, qty, timeUtc, usd } from "@/lib/format";
import type { Heartbeat, OrderRow, Portfolio, SignalRow } from "@/lib/types";
import { cn } from "@/lib/utils";

export function LiveTradingWatch({
  portfolio,
  signals,
  trades,
  heartbeat,
  tradingEnabled,
}: {
  portfolio: Portfolio | undefined;
  signals: SignalRow[];
  trades: OrderRow[];
  heartbeat: Heartbeat | null | undefined;
  tradingEnabled: boolean;
}) {
  const [flashIds, setFlashIds] = useState<Set<number>>(new Set());
  const seenRef = useRef<Set<number>>(new Set());
  const primed = useRef(false);

  useEffect(() => {
    const ids = trades.map((t) => t.id);
    if (!primed.current) {
      seenRef.current = new Set(ids);
      primed.current = true;
      return;
    }
    const fresh = ids.filter((id) => !seenRef.current.has(id));
    if (fresh.length === 0) return;
    for (const id of fresh) seenRef.current.add(id);
    setFlashIds(new Set(fresh));
    const timer = window.setTimeout(() => setFlashIds(new Set()), 4000);
    return () => window.clearTimeout(timer);
  }, [trades]);

  const fills = trades.filter((t) => t.status === "filled" || t.status === "rejected");

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <h2 className="font-mono text-[11px] uppercase tracking-[0.16em] text-[var(--amber)]">
            Live watch
          </h2>
          <p className="mt-1 font-mono text-xs text-muted-foreground">
            Open positions, latest signals, and a scrolling paper tape — auto-refresh while the engine
            is up
            {tradingEnabled ? "" : " (loop paused — tape stays until the next fill)"}.
          </p>
        </div>
        <p className="font-mono text-[11px] text-muted-foreground">
          {heartbeat
            ? `Last cycle #${heartbeat.id} · ${heartbeat.status} · ${ago(heartbeat.finished_at ?? heartbeat.started_at)}`
            : tradingEnabled
              ? "Waiting for first trading cycle…"
              : "No trading cycles yet"}
        </p>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <section className="space-y-2 border border-border bg-[#0c0c0c] p-4">
          <h3 className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
            Open positions
          </h3>
          <PositionsTable rows={portfolio?.positions ?? []} />
        </section>
        <section className="space-y-2 border border-border bg-[#0c0c0c] p-4">
          <h3 className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
            Signal stream
          </h3>
          <SignalList rows={signals.slice(0, 12)} compact />
        </section>
      </div>

      <section className="border border-border bg-[#0c0c0c] p-4">
        <h3 className="mb-3 font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
          Live paper tape
        </h3>
        {fills.length === 0 ? (
          <p className="font-mono text-xs text-muted-foreground">
            No paper fills yet. When Start trading is on and ENTER/EXIT fires, new rows highlight
            here.
          </p>
        ) : (
          <ul className="max-h-[28rem] space-y-1.5 overflow-y-auto font-mono text-[11px]">
            {fills.slice(0, 40).map((t) => {
              const flash = flashIds.has(t.id);
              return (
                <li
                  key={t.id}
                  className={cn(
                    "flex flex-wrap items-baseline gap-x-2 gap-y-0.5 border-b border-border/40 px-1 py-1.5 last:border-0 transition-colors",
                    flash && "bg-[var(--amber)]/15",
                  )}
                >
                  <span className="text-muted-foreground">{timeUtc(t.created_at)}</span>
                  <span className="text-[var(--amber)]">{t.symbol}</span>
                  <span className="uppercase">{t.side}</span>
                  <span
                    className={
                      t.status === "filled" ? "text-[var(--gain)]" : "text-[var(--loss)]"
                    }
                  >
                    {t.status}
                  </span>
                  <span className="tabular-nums">{qty(t.qty)}</span>
                  <span className="ml-auto tabular-nums">{usd(t.fill_price ?? t.ref_price)}</span>
                  {t.realized_pnl != null ? (
                    <span className={pnlClass(t.realized_pnl)}>{usd(t.realized_pnl)}</span>
                  ) : null}
                  {flash ? (
                    <Badge className="bg-[var(--amber)]/25 text-[var(--amber)]">new</Badge>
                  ) : null}
                </li>
              );
            })}
          </ul>
        )}
      </section>

      {portfolio && portfolio.watchlist.length > 0 ? (
        <section className="border border-border bg-[#090909] p-3">
          <h3 className="mb-2 font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
            Marks
          </h3>
          <div className="flex flex-wrap gap-3">
            {portfolio.watchlist.map((w) => (
              <div key={w.symbol} className="font-mono text-xs">
                <span className="text-[var(--amber)]">{w.symbol}</span>{" "}
                <span className="tabular-nums">
                  {usd(w.last, w.last != null && w.last >= 1000 ? 2 : 4)}
                </span>
              </div>
            ))}
          </div>
        </section>
      ) : null}
    </div>
  );
}
