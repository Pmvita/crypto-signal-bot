"use client";

import { useState } from "react";

import { EquityChart } from "@/components/equity-chart";
import { Button } from "@/components/ui/button";
import { runBacktest } from "@/lib/api";
import { pct, timeUtc, usd } from "@/lib/format";
import type { BacktestRun } from "@/lib/types";

export function BacktestReport({
  run,
  onRan,
}: {
  run: BacktestRun | null | undefined;
  onRan: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function runNow() {
    setBusy(true);
    setError(null);
    try {
      await runBacktest();
      onRan();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      <div className="rounded-md border border-[var(--amber)]/25 bg-[var(--amber)]/5 px-3 py-2 font-mono text-xs text-[var(--amber)]">
        Price rules only — news scoring is not part of this backtest.
      </div>
      <div className="flex items-center gap-3">
        <Button
          onClick={() => void runNow()}
          disabled={busy}
          className="bg-[var(--amber)] text-black hover:bg-[var(--amber)]/90"
        >
          {busy ? "Running…" : "Run backtest"}
        </Button>
        {error ? <span className="font-mono text-xs text-[var(--loss)]">{error}</span> : null}
      </div>

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
