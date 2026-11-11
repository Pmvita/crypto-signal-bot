"use client";

import { Sparkline } from "@/components/sparkline";
import { Badge } from "@/components/ui/badge";
import { ago, pnlClass, qty, timeUtc, usd } from "@/lib/format";
import type {
  Action,
  CandleSeriesResponse,
  Heartbeat,
  OrderRow,
  Portfolio,
  PositionRow,
  SignalRow,
  WatchlistRow,
} from "@/lib/types";
import { cn } from "@/lib/utils";

function actionBadge(action: Action) {
  switch (action) {
    case "enter":
      return <Badge className="bg-[var(--gain)]/20 text-[var(--gain)]">ENTER</Badge>;
    case "exit":
      return <Badge className="bg-[var(--loss)]/20 text-[var(--loss)]">EXIT</Badge>;
    case "hold":
      return <Badge variant="outline">HOLD</Badge>;
    default: {
      const _exhaustive: never = action;
      return _exhaustive;
    }
  }
}

function latestBySymbol(signals: SignalRow[]): Map<string, SignalRow> {
  const map = new Map<string, SignalRow>();
  for (const s of signals) {
    if (!map.has(s.symbol)) map.set(s.symbol, s);
  }
  return map;
}

function positionBySymbol(positions: PositionRow[]): Map<string, PositionRow> {
  return new Map(positions.map((p) => [p.symbol, p]));
}

function cycleLine(hb: Heartbeat | null | undefined, tradingEnabled: boolean): string {
  if (!tradingEnabled) return "Paper trading paused — open Trading to start the loop";
  if (!hb) return "Waiting for first paper cycle…";
  const summary = hb.summary;
  if (!summary) {
    return hb.error
      ? `Last cycle #${hb.id} failed: ${hb.error}`
      : `Last cycle #${hb.id} · ${hb.status} · ${ago(hb.finished_at ?? hb.started_at)}`;
  }
  const signals = Array.isArray(summary.signals) ? summary.signals.length : 0;
  const orders = Array.isArray(summary.orders) ? summary.orders.length : 0;
  if (signals === 0 && orders === 0) {
    return `Last cycle #${hb.id} · ${hb.status} · ${ago(hb.finished_at ?? hb.started_at)} · waiting for next 4h signal bar`;
  }
  return `Last cycle #${hb.id} · ${hb.status} · ${ago(hb.finished_at ?? hb.started_at)} · ${signals} signals · ${orders} paper orders`;
}

export function MarketPreview({
  portfolio,
  signals,
  trades,
  candles,
  heartbeat,
  exchange,
  tradingEnabled = false,
}: {
  portfolio: Portfolio;
  signals: SignalRow[];
  trades: OrderRow[];
  candles: CandleSeriesResponse | undefined;
  heartbeat: Heartbeat | null | undefined;
  exchange: string;
  tradingEnabled?: boolean;
}) {
  const latest = latestBySymbol(signals);
  const open = positionBySymbol(portfolio.positions);
  const symbols =
    portfolio.watchlist.length > 0
      ? portfolio.watchlist
      : (["BTC/USD", "ETH/USD", "SOL/USD"] as const).map(
          (symbol): WatchlistRow => ({
            symbol,
            last: null,
            bid: null,
            ask: null,
            ts: null,
            trend: null,
          }),
        );

  return (
    <section className="space-y-4 border border-border bg-[#0c0c0c] p-4">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <h2 className="font-mono text-[11px] uppercase tracking-[0.16em] text-[var(--amber)]">
            Live market preview
          </h2>
          <p className="mt-1 font-mono text-xs text-muted-foreground">
            What the paper bot sees on {exchange} right now · auto-refresh · loop control on Trading
          </p>
        </div>
        <p
          className={cn(
            "font-mono text-[11px]",
            !tradingEnabled
              ? "text-muted-foreground"
              : heartbeat?.status === "ok"
                ? "text-[var(--gain)]"
                : heartbeat?.status === "error"
                  ? "text-[var(--loss)]"
                  : "text-muted-foreground",
          )}
        >
          {cycleLine(heartbeat, tradingEnabled)}
        </p>
      </div>

      <div className="grid gap-3 md:grid-cols-3">
        {symbols.map((row) => {
          const sig = latest.get(row.symbol);
          const pos = open.get(row.symbol);
          const series = candles?.series?.[row.symbol] ?? [];
          const closes = series.map((p) => p.close);
          return (
            <div
              key={row.symbol}
              className="border border-border/80 bg-[#090909] px-3 py-3"
            >
              <div className="flex items-start justify-between gap-2">
                <div>
                  <div className="font-mono text-sm tracking-wide text-[var(--amber)]">
                    {row.symbol}
                  </div>
                  <div className="mt-0.5 font-mono text-lg tabular-nums text-foreground">
                    {usd(row.last, row.last != null && row.last >= 1000 ? 2 : 4)}
                  </div>
                  <div className="mt-0.5 font-mono text-[10px] text-muted-foreground">
                    {row.trend === "up" ? (
                      <span className="text-[var(--gain)]">trend up</span>
                    ) : row.trend === "down" ? (
                      <span className="text-[var(--loss)]">trend down</span>
                    ) : (
                      "trend —"
                    )}
                    {row.ts ? ` · quote ${ago(row.ts)}` : ""}
                  </div>
                </div>
                <Sparkline values={closes} />
              </div>

              <div className="mt-3 flex flex-wrap items-center gap-2">
                {sig ? actionBadge(sig.action) : <Badge variant="outline">—</Badge>}
                <span className="font-mono text-[10px] text-muted-foreground">
                  {sig ? ago(sig.created_at) : "no signal yet"}
                </span>
              </div>
              <p className="mt-2 line-clamp-2 font-mono text-[11px] text-muted-foreground">
                {sig?.reasons?.[0] ?? "Waiting for the next evaluation cycle."}
              </p>

              {pos ? (
                <div className="mt-3 border-t border-border/60 pt-2 font-mono text-[10px]">
                  <span className="text-muted-foreground">open </span>
                  <span>{qty(pos.qty)}</span>
                  <span className="text-muted-foreground"> @ </span>
                  <span>{usd(pos.entry_price)}</span>
                  <span className="text-muted-foreground"> · uPnL </span>
                  <span className={pnlClass(pos.unrealized_pnl)}>{usd(pos.unrealized_pnl)}</span>
                </div>
              ) : (
                <div className="mt-3 border-t border-border/60 pt-2 font-mono text-[10px] text-muted-foreground">
                  No open paper position
                </div>
              )}
            </div>
          );
        })}
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <div>
          <h3 className="mb-2 font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
            Recent paper tape
          </h3>
          {trades.length === 0 ? (
            <p className="font-mono text-xs text-muted-foreground">
              No paper fills yet — HOLD cycles stay quiet until ENTER/EXIT fires.
            </p>
          ) : (
            <ul className="space-y-1.5 font-mono text-[11px]">
              {trades.slice(0, 8).map((t) => (
                <li
                  key={t.id}
                  className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5 border-b border-border/40 pb-1.5 last:border-0"
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
                  <span className="ml-auto tabular-nums">{usd(t.fill_price ?? t.ref_price)}</span>
                  {t.realized_pnl != null ? (
                    <span className={pnlClass(t.realized_pnl)}>{usd(t.realized_pnl)}</span>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </div>
        <div>
          <h3 className="mb-2 font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
            Open paper positions
          </h3>
          {portfolio.positions.length === 0 ? (
            <p className="font-mono text-xs text-muted-foreground">Flat — no open positions.</p>
          ) : (
            <ul className="space-y-1.5 font-mono text-[11px]">
              {portfolio.positions.map((p) => (
                <li
                  key={p.symbol}
                  className="flex flex-wrap items-baseline gap-x-2 border-b border-border/40 pb-1.5 last:border-0"
                >
                  <span className="text-[var(--amber)]">{p.symbol}</span>
                  <span>{qty(p.qty)}</span>
                  <span className="text-muted-foreground">last {usd(p.last)}</span>
                  <span className={cn("ml-auto", pnlClass(p.unrealized_pnl))}>
                    {usd(p.unrealized_pnl)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </section>
  );
}
