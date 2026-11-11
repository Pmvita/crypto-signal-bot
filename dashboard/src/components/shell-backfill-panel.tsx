"use client";

import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { getCsbShell } from "@/lib/csb-shell";

export function ShellBackfillPanel() {
  const shell = getCsbShell();
  const [busy, setBusy] = useState(false);
  const [log, setLog] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!shell) return;
    return shell.jobs.onLog((payload) => {
      if (payload.type === "start") {
        setLog("");
        setBusy(true);
      }
      if (payload.type === "chunk" && payload.text) {
        setLog((prev) => prev + payload.text);
      }
      if (payload.type === "done") {
        setBusy(false);
        if (!payload.ok && payload.message) setError(payload.message);
      }
    });
  }, [shell]);

  if (!shell) return null;

  const run = async () => {
    setBusy(true);
    setError(null);
    setLog("");
    try {
      await shell.jobs.backfill();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setBusy(false);
    }
  };

  return (
    <div className="space-y-3">
      <p className="font-mono text-xs text-muted-foreground">
        Downloads historical 1h candles into the local SQLite database (same as{" "}
        <code className="text-[var(--amber)]">python -m csb backfill</code>).
      </p>
      <Button type="button" disabled={busy} onClick={() => void run()}>
        {busy ? "Backfill running…" : "Run backfill"}
      </Button>
      {error ? <p className="font-mono text-xs text-[var(--loss)]">{error}</p> : null}
      {log ? (
        <pre className="max-h-48 overflow-auto border border-border bg-black/40 p-2 font-mono text-[10px] text-muted-foreground whitespace-pre-wrap">
          {log}
        </pre>
      ) : null}
    </div>
  );
}
