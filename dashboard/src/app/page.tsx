"use client";

import { EngineOffline } from "@/components/engine-offline";
import { EquityChart } from "@/components/equity-chart";
import { HeadlineList } from "@/components/headline-list";
import { MoneyKpi, PnlKpi } from "@/components/kpi";
import { PositionsTable } from "@/components/positions-table";
import { SignalList } from "@/components/signal-list";
import { Watchlist } from "@/components/watchlist";
import { Skeleton } from "@/components/ui/skeleton";
import { useEngine } from "@/lib/api";
import type { EquityPoint, NewsResponse, Portfolio, SignalRow, Status } from "@/lib/types";

export default function DeskPage() {
  const status = useEngine<Status>("/api/status", 4000);
  const portfolio = useEngine<Portfolio>("/api/portfolio", 4000);
  const equity = useEngine<EquityPoint[]>("/api/equity?limit=400", 8000);
  const signals = useEngine<SignalRow[]>("/api/signals?limit=8", 5000);
  const news = useEngine<NewsResponse>("/api/news?limit=6", 15000);

  if (status.error || portfolio.error) {
    return <EngineOffline error={status.error ?? portfolio.error} />;
  }

  if (!portfolio.data || !status.data) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-20 w-full" />
        <Skeleton className="h-48 w-full" />
      </div>
    );
  }

  const p = portfolio.data;

  return (
    <div className="space-y-6">
      <header>
        <h1 className="font-heading text-2xl font-semibold tracking-wide text-[var(--amber)]">
          Desk
        </h1>
        <p className="mt-1 font-mono text-xs text-muted-foreground">
          Paper account on {status.data.exchange} · live trading not available
        </p>
      </header>

      <section className="grid grid-cols-2 gap-6 border border-border bg-[#0c0c0c] p-4 md:grid-cols-5">
        <MoneyKpi label="Equity" value={p.equity} />
        <MoneyKpi label="Cash" value={p.cash} />
        <PnlKpi label="Day P&L" value={p.day_pnl} />
        <PnlKpi label="Total P&L" value={p.total_pnl} />
        <MoneyKpi label="Fees paid" value={p.fees_paid} />
      </section>

      <div className="grid gap-6 lg:grid-cols-2">
        <section className="space-y-3 border border-border bg-[#0c0c0c] p-4">
          <h2 className="font-mono text-[11px] uppercase tracking-[0.16em] text-muted-foreground">
            Equity
          </h2>
          <EquityChart points={equity.data ?? []} />
        </section>
        <section className="space-y-3 border border-border bg-[#0c0c0c] p-4">
          <h2 className="font-mono text-[11px] uppercase tracking-[0.16em] text-muted-foreground">
            Watchlist
          </h2>
          <Watchlist rows={p.watchlist} />
        </section>
      </div>

      <section className="space-y-3 border border-border bg-[#0c0c0c] p-4">
        <h2 className="font-mono text-[11px] uppercase tracking-[0.16em] text-muted-foreground">
          Open positions
        </h2>
        <PositionsTable rows={p.positions} />
      </section>

      <div className="grid gap-6 lg:grid-cols-2">
        <section className="space-y-3">
          <h2 className="font-mono text-[11px] uppercase tracking-[0.16em] text-muted-foreground">
            Latest signals
          </h2>
          <SignalList rows={signals.data ?? []} compact />
        </section>
        <section className="space-y-3">
          <h2 className="font-mono text-[11px] uppercase tracking-[0.16em] text-muted-foreground">
            Headlines
          </h2>
          {!status.data.news_scoring.enabled ? (
            <p className="font-mono text-[11px] text-cyan-400/80">
              Scoring off — no LLM API key configured
            </p>
          ) : null}
          <HeadlineList
            rows={news.data?.headlines ?? []}
            scoringEnabled={Boolean(status.data.news_scoring.enabled)}
          />
        </section>
      </div>
    </div>
  );
}
