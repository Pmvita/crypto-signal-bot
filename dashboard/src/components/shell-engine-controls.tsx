"use client";

import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { getCsbShell, useElectronShell, type EngineShellStatus } from "@/lib/csb-shell";
import { cn } from "@/lib/utils";

type Variant = "compact" | "full" | "strip";

export function ShellEngineControls({
  variant = "full",
  compact = false,
}: {
  variant?: Variant;
  /** @deprecated use variant="compact" */
  compact?: boolean;
}) {
  const resolved: Variant = compact ? "compact" : variant;
  const electron = useElectronShell();
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

  const running = Boolean(status?.running || status?.healthy);
  const healthy = Boolean(status?.healthy);
  const label = healthy ? "ENGINE ON" : running ? "ENGINE…" : "ENGINE OFF";

  const start = async () => {
    if (!shell) return;
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
    if (!shell) return;
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

  if (!electron) {
    if (resolved === "compact") {
      return (
        <span className="font-mono text-[10px] text-muted-foreground">
          Start/Stop: desktop app
        </span>
      );
    }
    if (resolved === "strip") {
      return (
        <div className="flex flex-wrap items-center gap-2">
          <Button type="button" size="sm" className="h-8 min-w-[7.5rem] font-mono text-xs" disabled>
            Start engine
          </Button>
          <Button type="button" size="sm" variant="outline" className="h-8 min-w-[7.5rem] font-mono text-xs" disabled>
            Stop engine
          </Button>
        </div>
      );
    }
    return (
      <div className="space-y-2">
        <div className="font-mono text-xs text-muted-foreground">
          <span className="text-[var(--amber)]">Start / Stop engine</span> requires the desktop
          app. In a browser, start the engine with{" "}
          <code className="text-[var(--amber)]">python -m csb serve</code>.
        </div>
        <div className="flex flex-wrap gap-2">
          <Button type="button" disabled>
            Start engine
          </Button>
          <Button type="button" variant="outline" disabled>
            Stop engine
          </Button>
        </div>
      </div>
    );
  }

  if (resolved === "compact") {
    return (
      <div className="flex items-center gap-2">
        <span className={healthy ? "text-[var(--gain)]" : "text-[var(--loss)]"}>{label}</span>
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
            className="h-6 px-2 font-mono text-[10px] bg-[var(--amber)] text-black hover:bg-[var(--amber)]/90"
            disabled={busy}
            onClick={() => void start()}
          >
            Start
          </Button>
        )}
      </div>
    );
  }

  if (resolved === "strip") {
    return (
      <div className="flex flex-wrap items-center gap-3">
        <div
          className={cn(
            "flex items-center gap-2 font-mono text-xs tracking-wide",
            healthy ? "text-[var(--gain)]" : running ? "text-[var(--amber)]" : "text-[var(--loss)]",
          )}
        >
          <span
            className={cn(
              "inline-block size-2 rounded-full",
              healthy
                ? "bg-[var(--gain)] shadow-[0_0_8px_var(--gain)]"
                : running
                  ? "bg-[var(--amber)] animate-pulse"
                  : "bg-[var(--loss)]",
            )}
            aria-hidden
          />
          {healthy ? "Running" : running ? "Starting…" : "Stopped"}
        </div>
        {running ? (
          <Button
            type="button"
            size="sm"
            variant="outline"
            className="h-8 min-w-[7.5rem] font-mono text-xs"
            disabled={busy}
            onClick={() => void stop()}
          >
            Stop engine
          </Button>
        ) : (
          <Button
            type="button"
            size="sm"
            className="h-8 min-w-[7.5rem] font-mono text-xs bg-[var(--amber)] text-black hover:bg-[var(--amber)]/90"
            disabled={busy}
            onClick={() => void start()}
          >
            Start engine
          </Button>
        )}
        <span className="font-mono text-[10px] text-muted-foreground">
          {status?.host || "127.0.0.1"}:{status?.port || 8787}
          {status?.pid ? ` · pid ${status.pid}` : ""}
        </span>
        {error ? <span className="font-mono text-[10px] text-[var(--loss)]">{error}</span> : null}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-3 font-mono text-xs text-muted-foreground">
        <span className={healthy ? "text-[var(--gain)]" : "text-[var(--loss)]"}>{label}</span>
        <span>
          {status?.host || "127.0.0.1"}:{status?.port || 8787}
        </span>
        {status?.pid ? <span>pid {status.pid}</span> : null}
      </div>
      <div className="flex flex-wrap gap-2">
        <Button
          type="button"
          className="bg-[var(--amber)] text-black hover:bg-[var(--amber)]/90"
          disabled={busy || running}
          onClick={() => void start()}
        >
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
