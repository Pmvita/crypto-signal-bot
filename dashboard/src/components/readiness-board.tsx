"use client";

import { useEffect, useRef, useState } from "react";

import { Sparkline } from "@/components/sparkline";
import { Badge } from "@/components/ui/badge";
import { ago, pct, usd } from "@/lib/format";
import type { ReadinessState, SymbolReadiness, TradingReadiness } from "@/lib/types";
import { cn } from "@/lib/utils";

function stateChip(state: ReadinessState, tradingEnabled: boolean, positionSide: string | null) {
  if (!tradingEnabled) {
    return <Badge variant="outline">Loop paused</Badge>;
  }
  switch (state) {
    case "in_position":
      return (
        <Badge className="bg-[var(--gain)]/20 text-[var(--gain)]">
          In {positionSide === "short" ? "SHORT" : "LONG"}
        </Badge>
      );
    case "ready_to_enter_long":
      return <Badge className="bg-[var(--amber)]/25 text-[var(--amber)]">Ready LONG</Badge>;
    case "ready_to_enter_short":
      return <Badge className="bg-[var(--amber)]/25 text-[var(--amber)]">Ready SHORT</Badge>;
    case "waiting_for_long":
      return (
        <Badge className="border-[var(--amber)]/40 bg-[var(--amber)]/10 text-[var(--amber)]">
          Waiting LONG
        </Badge>
      );
    case "waiting_for_short":
      return (
        <Badge className="border-[var(--amber)]/40 bg-[var(--amber)]/10 text-[var(--amber)]">
          Waiting SHORT
        </Badge>
      );
    case "waiting_for_enter":
      return (
        <Badge className="border-[var(--amber)]/40 bg-[var(--amber)]/10 text-[var(--amber)]">
          Waiting
        </Badge>
      );
    case "warming_up":
      return <Badge variant="outline">Warming up</Badge>;
    default: {
      const _exhaustive: never = state;
      return _exhaustive;
    }
  }
}

function yesNo(ok: boolean | null | undefined) {
  if (ok == null) return <span className="text-muted-foreground">—</span>;
  return ok ? (
    <span className="text-[var(--gain)]">yes</span>
  ) : (
    <span className="text-[var(--loss)]">no</span>
  );
}

function conditionMeter(label: string, ok: boolean, detail: string) {
  return (
    <div className="flex items-start justify-between gap-2 border-b border-border/40 py-1 last:border-0">
      <div className="min-w-0">
        <div className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground">
          {label}
        </div>
        <div className="truncate font-mono text-[11px] tabular-nums text-foreground/90">{detail}</div>
      </div>
      <div
        className={cn(
          "mt-0.5 h-2 w-2 shrink-0 rounded-full",
          ok ? "bg-[var(--gain)] shadow-[0_0_6px_var(--gain)]" : "bg-[var(--loss)]/70",
        )}
        aria-hidden
      />
    </div>
  );
}

function priceDigits(n: number | null | undefined) {
  if (n == null) return 2;
  return n >= 1000 ? 2 : 4;
}

function SymbolCard({
  row,
  tradingEnabled,
  pulse,
  closer,
}: {
  row: SymbolReadiness;
  tradingEnabled: boolean;
  pulse: boolean;
  closer: boolean;
}) {
  const last = row.last ?? row.bar_close;
  const gap = row.ema_gap_pct;
  const distHighPct = row.distance_to_breakout_pct;
  const distHighUsd = row.distance_to_breakout;
  const distLowPct = row.distance_to_breakdown_pct;
  const distLowUsd = row.distance_to_breakdown;
  const trendLabel =
    row.trend_direction === "up" ? "up" : row.trend_direction === "down" ? "down" : "flat";

  return (
    <article
      className={cn(
        "relative border bg-[#090909] px-3 py-3 transition-colors duration-500",
        pulse ? "border-[var(--amber)]/70 bg-[var(--amber)]/[0.06]" : "border-border/80",
        closer && !pulse ? "border-[var(--gain)]/35" : null,
      )}
    >
      {pulse ? (
        <span
          className="absolute right-2 top-2 h-1.5 w-1.5 animate-pulse rounded-full bg-[var(--amber)]"
          title="Cycle tick"
          aria-hidden
        />
      ) : null}

      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="font-mono text-sm tracking-wide text-[var(--amber)]">{row.symbol}</div>
          <div className="mt-0.5 font-mono text-xl tabular-nums leading-none text-foreground">
            {usd(last, priceDigits(last))}
          </div>
          <div className="mt-1 font-mono text-[10px] text-muted-foreground">
            {row.quote_ts ? `quote ${ago(row.quote_ts)}` : "no quote yet"}
            {row.bar_ts ? ` · 15m bar ${ago(row.bar_ts)}` : ""}
          </div>
        </div>
        <div className="flex flex-col items-end gap-2">
          {stateChip(row.state, tradingEnabled, row.position_side)}
          <Sparkline
            values={row.sparkline}
            marker={row.breakout_level}
            markerLow={row.breakdown_level}
            width={132}
            height={36}
          />
          <div className="flex flex-col items-end gap-0.5 font-mono text-[9px]">
            {row.breakout_level != null ? (
              <span className="text-[var(--amber)]/80">
                high {usd(row.breakout_level, priceDigits(row.breakout_level))}
              </span>
            ) : null}
            {row.breakdown_level != null ? (
              <span className="text-[var(--loss)]/80">
                low {usd(row.breakdown_level, priceDigits(row.breakdown_level))}
              </span>
            ) : null}
          </div>
        </div>
      </div>

      <div className="mt-3 space-y-0.5">
        {conditionMeter(
          `EMA${row.ema_fast_period} vs EMA${row.ema_slow_period}`,
          Boolean(row.trend_up || row.trend_down),
          row.ema_fast != null && row.ema_slow != null
            ? `${usd(row.ema_fast, priceDigits(row.ema_fast))} / ${usd(row.ema_slow, priceDigits(row.ema_slow))} · gap ${pct(gap)} · trend ${trendLabel}`
            : `Need ~${row.bars_needed} 15m bars (${row.bars_ready} ready)`,
        )}
        {conditionMeter(
          `LONG · close vs ${row.breakout_bars}-bar high`,
          Boolean(row.breakout_ready && row.trend_up),
          row.prior_high != null
            ? distHighUsd != null && distHighUsd > 0
              ? `${usd(distHighUsd, priceDigits(distHighUsd))} (${pct(distHighPct)}) below breakout`
              : row.breakout_ready
                ? `Above breakout · ${usd(row.prior_high, priceDigits(row.prior_high))}`
                : `At / below ${usd(row.prior_high, priceDigits(row.prior_high))}`
            : "Breakout level unavailable",
        )}
        {conditionMeter(
          `SHORT · close vs ${row.breakout_bars}-bar low`,
          Boolean(row.breakdown_ready && row.trend_down),
          row.prior_low != null
            ? distLowUsd != null && distLowUsd > 0
              ? `${usd(distLowUsd, priceDigits(distLowUsd))} (${pct(distLowPct)}) above breakdown`
              : row.breakdown_ready
                ? `Below breakdown · ${usd(row.prior_low, priceDigits(row.prior_low))}`
                : `At / above ${usd(row.prior_low, priceDigits(row.prior_low))}`
            : "Breakdown level unavailable",
        )}
        {conditionMeter(
          "News gate",
          row.conditions.news_ok,
          row.news_state === "off"
            ? "Scoring off — no veto"
            : row.news_state === "veto"
              ? `Bearish · score ${row.news_score ?? "—"} (blocks LONG / boosts SHORT)`
              : row.news_state === "boost"
                ? `Bullish · score ${row.news_score ?? "—"} (boosts LONG / blocks SHORT)`
                : `${row.news_state} · score ${row.news_score ?? "—"}`,
        )}
      </div>

      <div className="mt-3 grid grid-cols-2 gap-x-3 gap-y-1 border-t border-border/60 pt-2 font-mono text-[10px]">
        <div>
          <span className="text-muted-foreground">trend </span>
          <span className="text-foreground">{trendLabel}</span>
        </div>
        <div>
          <span className="text-muted-foreground">breakout </span>
          {yesNo(row.breakout_ready)}
          <span className="text-muted-foreground"> · breakdown </span>
          {yesNo(row.breakdown_ready)}
        </div>
        {row.in_position ? (
          <div className="col-span-2 text-muted-foreground">
            ATR trail stop{" "}
            <span className="text-foreground">
              {usd(row.trail_stop ?? row.position_stop, priceDigits(row.trail_stop ?? row.position_stop))}
            </span>
            {row.atr != null ? (
              <span>
                {" "}
                · ATR{row.atr_period} {usd(row.atr, priceDigits(row.atr))} × {row.stop_atr_mult}
              </span>
            ) : null}
          </div>
        ) : row.atr != null ? (
          <div className="col-span-2 text-muted-foreground">
            ATR{row.atr_period}{" "}
            <span className="text-foreground">{usd(row.atr, priceDigits(row.atr))}</span>
            <span> · initial stop {row.stop_atr_mult}×ATR from entry (above for SHORT)</span>
          </div>
        ) : null}
      </div>
    </article>
  );
}

export function ReadinessBoard({
  readiness,
  tradingEnabled,
}: {
  readiness: TradingReadiness | undefined;
  tradingEnabled: boolean;
}) {
  const [pulse, setPulse] = useState(false);
  const lastCycleId = useRef<number | null>(null);
  const prevDist = useRef<Map<string, number | null>>(new Map());
  const [closer, setCloser] = useState<Set<string>>(new Set());

  useEffect(() => {
    const id = readiness?.heartbeat?.id ?? null;
    if (id == null) return;
    if (lastCycleId.current == null) {
      lastCycleId.current = id;
      return;
    }
    if (id === lastCycleId.current) return;
    lastCycleId.current = id;
    setPulse(true);
    const t = window.setTimeout(() => setPulse(false), 1200);
    return () => window.clearTimeout(t);
  }, [readiness?.heartbeat?.id]);

  useEffect(() => {
    if (!readiness?.symbols) return;
    const nextCloser = new Set<string>();
    for (const row of readiness.symbols) {
      const d =
        row.trend_direction === "down"
          ? row.distance_to_breakdown_pct
          : row.distance_to_breakout_pct;
      const prev = prevDist.current.get(row.symbol);
      const ready =
        row.trend_direction === "down" ? row.breakdown_ready : row.breakout_ready;
      if (prev != null && d != null && d > 0 && d < prev && !ready && !row.in_position) {
        nextCloser.add(row.symbol);
      }
      prevDist.current.set(row.symbol, d);
    }
    setCloser(nextCloser);
    if (nextCloser.size === 0) return;
    const t = window.setTimeout(() => setCloser(new Set()), 4000);
    return () => window.clearTimeout(t);
  }, [readiness?.symbols]);

  const nextAt = readiness?.next_cycle_at;
  const lastAt = readiness?.last_cycle_at;
  const cycleSec = readiness?.cycle_seconds ?? 20;
  const hb = readiness?.heartbeat;
  const tf = readiness?.params.timeframe ?? "15m";

  return (
    <section className="space-y-3 border border-border bg-[#0c0c0c] p-4">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <h2 className="font-mono text-[11px] uppercase tracking-[0.16em] text-[var(--amber)]">
            Active watch
          </h2>
          <p className="mt-1 max-w-2xl font-mono text-xs text-muted-foreground">
            Live readiness on {tf} · EMA{readiness?.params.ema_fast ?? 50}/
            {readiness?.params.ema_slow ?? 200} trend + {readiness?.params.breakout_bars ?? 20}-bar
            Donchian long/short. Amber = breakout high; red = breakdown low.
          </p>
        </div>
        <div className="text-right font-mono text-[11px]">
          <div
            className={cn(
              "flex items-center justify-end gap-2",
              tradingEnabled ? "text-[var(--gain)]" : "text-muted-foreground",
            )}
          >
            {tradingEnabled ? (
              <span
                className={cn(
                  "inline-block h-1.5 w-1.5 rounded-full bg-[var(--gain)]",
                  pulse && "animate-ping",
                )}
                aria-hidden
              />
            ) : null}
            {tradingEnabled ? "Loop watching" : "Loop paused"}
            {hb ? ` · cycle #${hb.id}` : ""}
          </div>
          <div className="mt-0.5 text-muted-foreground">
            {lastAt != null ? `Last ${ago(lastAt)}` : "No cycle yet"}
            {nextAt != null && tradingEnabled
              ? ` · next ~${Math.max(0, Math.ceil((nextAt - Date.now()) / 1000))}s`
              : ` · every ${cycleSec}s`}
          </div>
        </div>
      </div>

      {!readiness ? (
        <p className="font-mono text-xs text-muted-foreground">Loading readiness…</p>
      ) : (
        <div className="grid gap-3 lg:grid-cols-3">
          {readiness.symbols.map((row) => (
            <SymbolCard
              key={row.symbol}
              row={row}
              tradingEnabled={tradingEnabled}
              pulse={pulse}
              closer={closer.has(row.symbol)}
            />
          ))}
        </div>
      )}
    </section>
  );
}
