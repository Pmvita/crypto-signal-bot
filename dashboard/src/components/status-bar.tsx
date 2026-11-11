"use client";

import { Badge } from "@/components/ui/badge";
import { useEngine } from "@/lib/api";
import { ago } from "@/lib/format";
import type { Status } from "@/lib/types";

export function StatusBar() {
  const { data, error } = useEngine<Status>("/api/status", 3000);

  if (error || !data) {
    return (
      <div className="flex h-9 items-center gap-3 border-b border-border bg-[#0a0a0a] px-4 font-mono text-[11px] tracking-wide text-muted-foreground">
        <Badge variant="outline" className="border-[var(--loss)] text-[var(--loss)]">
          OFFLINE
        </Badge>
        <span>Engine unreachable</span>
        <span className="ml-auto text-[var(--amber)]">Live trading: not available</span>
      </div>
    );
  }

  const hb = data.heartbeat;
  const kill = data.risk.kill_switch;
  const scoring = data.news_scoring.enabled ? "ON" : "OFF";

  return (
    <div className="flex h-9 items-center gap-3 overflow-x-auto border-b border-border bg-[#0a0a0a] px-4 font-mono text-[11px] tracking-wide text-muted-foreground">
      <Badge className="bg-[var(--amber)] text-black hover:bg-[var(--amber)]">PAPER</Badge>
      <span className="text-[var(--amber)]">Live trading: not available</span>
      <span className="text-border">|</span>
      <span>{data.exchange}</span>
      <span className="text-border">|</span>
      <span>
        heartbeat{" "}
        {hb ? (
          <span className={hb.status === "ok" ? "text-[var(--gain)]" : "text-[var(--loss)]"}>
            {hb.status} · {ago(hb.finished_at ?? hb.started_at)}
          </span>
        ) : (
          <span>none yet</span>
        )}
      </span>
      <span className="text-border">|</span>
      <span>
        news scoring{" "}
        <span className={data.news_scoring.enabled ? "text-cyan-400" : "text-muted-foreground"}>
          {scoring}
        </span>
      </span>
      <span className="text-border">|</span>
      <span className={kill ? "text-[var(--loss)]" : "text-muted-foreground"}>
        kill switch {kill ? "ENGAGED" : "off"}
      </span>
      {data.risk.halted ? (
        <>
          <span className="text-border">|</span>
          <span className="text-[var(--loss)]">daily loss halt</span>
        </>
      ) : null}
    </div>
  );
}
