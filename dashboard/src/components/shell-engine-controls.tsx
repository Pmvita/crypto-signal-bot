"use client";

import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { getCsbShell, type EngineShellStatus } from "@/lib/csb-shell";

export function ShellEngineControls({ compact = false }: { compact?: boolean }) {
  const shell = getCsbShell();
  const [status, setStatus] = useState<EngineShellStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!shell) return;
    let cancelled = false;
    const refresh = async () => {
      try {
        const next = await shell.engine.status();
        if (!cancelled) setStatus(next);
      } catch {
        // ignore
      }
    };
    void refresh();
    const unsub = shell.engine.onEvent((payload) => {
      const p = payload as { type?: string; status?: EngineShellStatus };
      if (p.type === "status" && p.status) setStatus(p.status);
      if (p.type === "exit") void refresh();
    });
    const id = window.setInterval(() => void refresh(), 4000);
    return () => {
      cancelled = true;
      unsub();
      window.clearInterval(id);
    };
  }, [shell]);

  if (!shell) return null;

  const running = Boolean(status?.running || status?.healthy);
  const label = status?.healthy ? "ENGINE ON" : running ? "ENGINE…" : "ENGINE OFF";

  const start = async () => {
    setBusy(true);
    setError(null);
    try {
      const next = await shell.engine.start();
      setStatus(next);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  const stop = async () => {
    setBusy(true);
    setError(null);
    try {
      const next = await shell.engine.stop();
      setStatus(next);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  if (compact) {
    return (
      <div className="flex items-center gap-2">
        <span className={status?.healthy ? "text-[var(--gain)]" : "text-[var(--loss)]"}>{label}</span>
        {running ? (
          <Button
            type="button"
            size="sm"
            variant="outline"
            className="h-6 px-2 font-mono text-[10px]"
            disabled={busy}
            onClick={() => void stop()}
          >
            Stop
          </Button>
        ) : (
          <Button
            type="button"
            size="sm"
            variant="outline"
            className="h-6 px-2 font-mono text-[10px]"
            disabled={busy}
            onClick={() => void start()}
          >
            Start
          </Button>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-3 font-mono text-xs text-muted-foreground">
        <span className={status?.healthy ? "text-[var(--gain)]" : "text-[var(--loss)]"}>{label}</span>
        <span>
          {status?.host || "127.0.0.1"}:{status?.port || 8787}
        </span>
        {status?.pid ? <span>pid {status.pid}</span> : null}
      </div>
      <div className="flex flex-wrap gap-2">
        <Button type="button" disabled={busy || running} onClick={() => void start()}>
          Start engine
        </Button>
        <Button type="button" variant="outline" disabled={busy || !running} onClick={() => void stop()}>
          Stop engine
        </Button>
      </div>
      {error ? <p className="font-mono text-xs text-[var(--loss)]">{error}</p> : null}
    </div>
  );
}
