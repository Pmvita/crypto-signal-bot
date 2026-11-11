"use client";

import { useEffect, useState } from "react";

import { EngineOffline } from "@/components/engine-offline";
import { KillSwitch } from "@/components/kill-switch";
import { LiveTradingNotice } from "@/components/live-trading-notice";
import { RiskForm } from "@/components/risk-form";
import { ShellBackfillPanel } from "@/components/shell-backfill-panel";
import { ShellEngineControls } from "@/components/shell-engine-controls";
import { ShellLlmForm } from "@/components/shell-llm-form";
import { ShellUpdatesPanel } from "@/components/shell-updates-panel";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useEngine } from "@/lib/api";
import { getCsbShell, useElectronShell, type SetupState } from "@/lib/csb-shell";
import type { RiskResponse, Status } from "@/lib/types";

export default function SettingsPage() {
  const status = useEngine<Status>("/api/status", 4000);
  const risk = useEngine<RiskResponse>("/api/risk", 4000);
  const electron = useElectronShell();
  const [setup, setSetup] = useState<SetupState | null>(null);

  useEffect(() => {
    const shell = getCsbShell();
    if (!shell) return;
    void shell.setup.getState().then(setSetup).catch(() => setSetup(null));
  }, []);

  if (!electron && (status.error || risk.error)) {
    return <EngineOffline error={status.error ?? risk.error} />;
  }
  if (!electron && (!risk.data || !status.data)) return <Skeleton className="h-40 w-full" />;

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

      {electron ? (
        <>
          <section className="space-y-3 border border-border bg-[#0c0c0c] p-4">
            <h2 className="font-mono text-[11px] uppercase tracking-[0.16em] text-muted-foreground">
              Desktop engine
            </h2>
            <ShellEngineControls />
            {setup ? (
              <div className="font-mono text-[10px] text-muted-foreground space-y-1">
                <div>Data: {setup.dataRoot}</div>
                <div>.env: {setup.envPath}</div>
                <div>Mode: {setup.packaged ? "packaged" : "dev checkout"}</div>
              </div>
            ) : null}
            <div className="flex flex-wrap gap-2">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => void getCsbShell()?.shell.openDataFolder()}
              >
                Open data folder
              </Button>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => void getCsbShell()?.shell.openEnvLocation()}
              >
                Reveal .env
              </Button>
            </div>
          </section>

          <section className="space-y-3 border border-border bg-[#0c0c0c] p-4">
            <h2 className="font-mono text-[11px] uppercase tracking-[0.16em] text-muted-foreground">
              LLM / OpenRouter API key
            </h2>
            <ShellLlmForm
              onSaved={() => {
                void status.mutate();
                void getCsbShell()?.setup.getState().then(setSetup);
              }}
            />
          </section>

          <section className="space-y-3 border border-border bg-[#0c0c0c] p-4">
            <h2 className="font-mono text-[11px] uppercase tracking-[0.16em] text-muted-foreground">
              Backfill
            </h2>
            <ShellBackfillPanel />
          </section>

          <section className="space-y-3 border border-border bg-[#0c0c0c] p-4">
            <h2 className="font-mono text-[11px] uppercase tracking-[0.16em] text-muted-foreground">
              Check for updates
            </h2>
            <ShellUpdatesPanel />
          </section>
        </>
      ) : null}

      {status.error || risk.error ? (
        <EngineOffline error={status.error ?? risk.error} />
      ) : !risk.data || !status.data ? (
        <Skeleton className="h-40 w-full" />
      ) : (
        <>
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
        </>
      )}
    </div>
  );
}
