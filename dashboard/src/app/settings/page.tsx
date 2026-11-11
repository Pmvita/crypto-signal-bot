"use client";

import { EngineOffline } from "@/components/engine-offline";
import { KillSwitch } from "@/components/kill-switch";
import { LiveTradingNotice } from "@/components/live-trading-notice";
import { RiskForm } from "@/components/risk-form";
import { Skeleton } from "@/components/ui/skeleton";
import { useEngine } from "@/lib/api";
import type { RiskResponse, Status } from "@/lib/types";

export default function SettingsPage() {
  const status = useEngine<Status>("/api/status", 4000);
  const risk = useEngine<RiskResponse>("/api/risk", 4000);

  if (status.error || risk.error) {
    return <EngineOffline error={status.error ?? risk.error} />;
  }
  if (!risk.data || !status.data) return <Skeleton className="h-40 w-full" />;

  return (
    <div className="space-y-6">
      <header>
        <h1 className="font-heading text-2xl font-semibold tracking-wide text-[var(--amber)]">
          Settings
        </h1>
        <p className="mt-1 font-mono text-xs text-muted-foreground">
          Risk limits and kill switch · strategy parameters are fixed in phase 1
        </p>
      </header>

      <LiveTradingNotice />

      <section className="space-y-3 border border-border bg-[#0c0c0c] p-4">
        <h2 className="font-mono text-[11px] uppercase tracking-[0.16em] text-muted-foreground">
          Kill switch
        </h2>
        <p className="font-mono text-xs text-muted-foreground">
          Current state:{" "}
          <span className={risk.data.kill_switch ? "text-[var(--loss)]" : ""}>
            {risk.data.kill_switch ? "ENGAGED" : "off"}
          </span>
          {risk.data.halted ? " · daily loss halt active" : ""}
        </p>
        <KillSwitch engaged={risk.data.kill_switch} onChange={() => void risk.mutate()} />
      </section>

      <section className="space-y-3 border border-border bg-[#0c0c0c] p-4">
        <h2 className="font-mono text-[11px] uppercase tracking-[0.16em] text-muted-foreground">
          Risk limits
        </h2>
        <RiskForm
          key={JSON.stringify(risk.data.limits)}
          limits={risk.data.limits}
          onSaved={() => void risk.mutate()}
        />
      </section>

      <section className="border border-border bg-[#0c0c0c] p-4 font-mono text-xs text-muted-foreground">
        <div>Exchange: {status.data.exchange}</div>
        <div>Symbols: {status.data.symbols.join(", ")}</div>
        <div>
          News scoring: {status.data.news_scoring.enabled ? "on" : "off"}
          {status.data.news_scoring.reason ? ` — ${status.data.news_scoring.reason}` : ""}
        </div>
      </section>
    </div>
  );
}
