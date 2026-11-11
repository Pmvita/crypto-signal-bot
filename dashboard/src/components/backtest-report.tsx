"use client";

import { useState } from "react";

import { EquityChart } from "@/components/equity-chart";
import { Button } from "@/components/ui/button";
import { engineErrorMessage, runBackfill, runBacktest } from "@/lib/api";
import { pct, timeUtc, usd } from "@/lib/format";
import type { BacktestRun, CandleHistorySummary } from "@/lib/types";

type Phase = "idle" | "backfilling" | "running";

export function BacktestReport({
  run,
  history,
  onRan,
  onHistoryChange,
}: {
  run: BacktestRun | null | undefined;
  history: CandleHistorySummary | null | undefined;
  onRan: () => void;
  onHistoryChange: () => void;
}) {
  const [phase, setPhase] = useState<Phase>("idle");
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);

  const historyKnown = history != null;
  const ready = !historyKnown || history.ready_for_backtest;
  const needsHistory = historyKnown && !history.ready_for_backtest;
  const busy = phase !== "idle";
  const days = history?.backfill_days_default ?? 730;

  async function downloadAndRun() {
    setPhase("backfilling");
    setError(null);
    setStatus(`Downloading ~${days} days of 1h candles… this can take several minutes.`);
    try {
      const result = await runBackfill(days);
      onHistoryChange();
      const stored = Object.entries(result.stored)
        .map(([sym, n]) => `${sym}: ${n}`)
        .join(", ");
      setStatus(`Backfill done (${stored}). Running backtest…`);
      setPhase("running");
      await runBacktest();
      setStatus(null);
      onRan();
      onHistoryChange();
    } catch (e) {
      setError(engineErrorMessage(e));
      setStatus(null);
    } finally {
      setPhase("idle");
    }
  }

  async function runNow() {
    setPhase("running");
    setError(null);
    setStatus(null);
    try {
      await runBacktest();
      onRan();
      onHistoryChange();
    } catch (e) {
      const message = engineErrorMessage(e);
      setError(message);
      if (/backfill|candle history|no candles/i.test(message)) {
        onHistoryChange();
      }
    } finally {
      setPhase("idle");
    }
  }

  return (
    <div className="space-y-4">
      <div className="rounded-md border border-[var(--amber)]/25 bg-[var(--amber)]/5 px-3 py-2 font-mono text-xs text-[var(--amber)]">
        Price rules only — news scoring is not part of this backtest.
      </div>

      {needsHistory ? (
        <div className="rounded-md border border-[var(--loss)]/40 bg-[var(--loss)]/10 px-3 py-3 font-mono text-xs text-[var(--loss)] space-y-2">
          <p>
            {history.message ??
              `Need at least ${history.required_signal_bars} 4h bars; have ${history.max_signal_bars}.`}
          </p>
          <p className="text-muted-foreground">
            Paper cycles only keep a short warm-up window. Download history before running a
            backtest, or use Settings → Run backfill.
          </p>
        </div>
      ) : null}

      {historyKnown && ready ? (
        <p className="font-mono text-[10px] text-muted-foreground">
          History ready · {history.max_signal_bars} 4h bars (need {history.required_signal_bars}) ·{" "}
          {history.symbols.map((s) => `${s.symbol} ${s.hourly_candles}h`).join(" · ")}
        </p>
      ) : null}

      <div className="flex flex-wrap items-center gap-3">
        {needsHistory ? (
          <Button
            onClick={() => void downloadAndRun()}
            disabled={busy}
            className="bg-[var(--amber)] text-black hover:bg-[var(--amber)]/90"
          >
            {phase === "backfilling"
              ? "Downloading history…"
              : phase === "running"
                ? "Running…"
                : "Download history & run"}
          </Button>
        ) : (
          <Button
            onClick={() => void runNow()}
            disabled={busy}
            className="bg-[var(--amber)] text-black hover:bg-[var(--amber)]/90"
          >
            {phase === "running" ? "Running…" : "Run backtest"}
          </Button>
        )}
        {needsHistory && !busy ? (
          <Button variant="outline" onClick={() => void runNow()} disabled={busy}>
            Try run anyway
          </Button>
        ) : null}
      </div>

      {status ? <p className="font-mono text-xs text-[var(--amber)]">{status}</p> : null}
      {error ? (
        <div className="rounded-md border border-[var(--loss)]/40 bg-[var(--loss)]/10 px-3 py-2 font-mono text-xs text-[var(--loss)] whitespace-pre-wrap">
          {error}
        </div>
      ) : null}

      {!run ? (
        <p className="font-mono text-xs text-muted-foreground">No backtest run stored yet.</p>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            <Metric label="Return" value={pct(run.result.total_return_pct)} />
            <Metric label="Max DD" value={pct(-run.result.max_drawdown_pct).replace("+", "")} />
            <Metric label="Trades" value={String(run.result.trades)} />
            <Metric label="Final equity" value={usd(run.result.final_equity)} />
            <Metric label="Win rate" value={pct(run.result.win_rate_pct)} />
            <Metric
              label="Profit factor"
              value={run.result.profit_factor == null ? "—" : run.result.profit_factor.toFixed(2)}
            />
            <Metric label="Fees" value={usd(run.result.total_fees)} />
            <Metric label="Buy & hold" value={pct(run.result.buy_hold_return_pct)} />
          </div>
          <p className="font-mono text-[10px] text-muted-foreground">
            Run {run.id} · {timeUtc(run.created_at)} · bars {run.result.bars} · news included:{" "}
            {String(run.news_included)}
          </p>
          {run.result.trades === 0 ? (
            <p className="font-mono text-xs text-muted-foreground">
              Zero trades in this window — with short history that is expected. Download a longer
              history and re-run if you have not already.
            </p>
          ) : null}
          <EquityChart points={run.result.equity_curve} />
          {run.result.trade_list.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full font-mono text-xs">
                <thead className="text-left text-muted-foreground">
                  <tr>
                    <th className="py-1">Symbol</th>
                    <th>Entry</th>
                    <th>Exit</th>
                    <th className="text-right">PnL</th>
                    <th>Reason</th>
                  </tr>
                </thead>
                <tbody>
                  {run.result.trade_list.slice(0, 40).map((t, i) => (
                    <tr key={i} className="border-t border-border/50">
                      <td className="py-1 text-[var(--amber)]">{String(t.symbol)}</td>
                      <td>{usd(Number(t.entry_price))}</td>
                      <td>{usd(Number(t.exit_price))}</td>
                      <td
                        className={`text-right ${
                          Number(t.pnl) >= 0 ? "text-[var(--gain)]" : "text-[var(--loss)]"
                        }`}
                      >
                        {usd(Number(t.pnl))}
                      </td>
                      <td className="text-muted-foreground">{String(t.exit_reason)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </>
      )}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
        {label}
      </div>
      <div className="mt-1 font-mono text-lg tabular-nums">{value}</div>
    </div>
  );
}
