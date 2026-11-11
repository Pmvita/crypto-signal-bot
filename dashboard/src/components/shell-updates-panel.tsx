"use client";

import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  getCsbShell,
  type UpdateApplyResult,
  type UpdateCheckResult,
} from "@/lib/csb-shell";

export function ShellUpdatesPanel() {
  const shell = getCsbShell();
  const [progress, setProgress] = useState<string[]>([]);
  const [check, setCheck] = useState<UpdateCheckResult | null>(null);
  const [applyResult, setApplyResult] = useState<UpdateApplyResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!shell) return;
    return shell.updates.onProgress((payload) => {
      setProgress((prev) => [...prev.slice(-20), payload.message]);
    });
  }, [shell]);

  if (!shell) return null;

  const runCheck = async () => {
    setBusy(true);
    setError(null);
    setApplyResult(null);
    setProgress([]);
    try {
      const result = await shell.updates.check();
      setCheck(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  const runApply = async () => {
    setBusy(true);
    setError(null);
    try {
      const result = await shell.updates.apply();
      setApplyResult(result);
      setCheck(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-3">
      <p className="font-mono text-xs text-muted-foreground">
        Local test loop: pulls newer commits from{" "}
        <span className="text-foreground">Pmvita/crypto-signal-bot</span> via git when this app is
        running from a checkout. Packaged installs cannot git-pull — use GitHub Releases instead.
        Never overwrites <code className="text-[var(--amber)]">.env</code>.
      </p>
      <div className="flex flex-wrap gap-2">
        <Button type="button" disabled={busy} onClick={() => void runCheck()}>
          Check for updates
        </Button>
        {check?.canApply ? (
          <Button type="button" variant="outline" disabled={busy} onClick={() => void runApply()}>
            Apply update (ff-only)
          </Button>
        ) : null}
        {check?.mode === "packaged" && check.releasesUrl ? (
          <Button
            type="button"
            variant="outline"
            disabled={busy}
            onClick={() => void shell.shell.openExternal(check.releasesUrl)}
          >
            Open Releases
          </Button>
        ) : null}
        {applyResult?.restartRequired ? (
          <Button type="button" variant="outline" disabled={busy} onClick={() => void shell.shell.restartApp()}>
            Restart app
          </Button>
        ) : null}
      </div>
      {check ? (
        <p className="font-mono text-xs text-foreground whitespace-pre-wrap">{check.message}</p>
      ) : null}
      {applyResult?.engineRestarted ? (
        <p className="font-mono text-xs text-[var(--gain)]">Engine restarted after update.</p>
      ) : null}
      {applyResult?.engineRestartError ? (
        <p className="font-mono text-xs text-[var(--loss)]">
          Engine restart failed: {applyResult.engineRestartError}
        </p>
      ) : null}
      {error ? <p className="font-mono text-xs text-[var(--loss)]">{error}</p> : null}
      {progress.length ? (
        <pre className="max-h-40 overflow-auto border border-border bg-black/40 p-2 font-mono text-[10px] text-muted-foreground">
          {progress.join("\n")}
        </pre>
      ) : null}
    </div>
  );
}
