"use client";

import { ShellEngineControls } from "@/components/shell-engine-controls";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { ENGINE_URL } from "@/lib/api";
import { useElectronShell } from "@/lib/csb-shell";

export function EngineOffline({ error }: { error?: Error }) {
  const electron = useElectronShell();
  return (
    <Alert variant="destructive" className="border-[var(--loss)]/40 bg-[var(--loss)]/10">
      <AlertTitle>Engine unreachable</AlertTitle>
      <AlertDescription className="space-y-3 font-mono text-xs">
        <p>
          Cannot reach {ENGINE_URL}.{" "}
          {electron ? (
            <>
              Use <span className="text-[var(--amber)]">Start engine</span> in the control strip
              above (or Settings).
            </>
          ) : (
            <>
              Start it with <code className="text-[var(--amber)]">python -m csb serve</code>, or
              open the desktop app for Start/Stop controls.
            </>
          )}
          {error ? ` — ${error.message}` : ""}. Stale numbers are not shown.
        </p>
        <ShellEngineControls />
      </AlertDescription>
    </Alert>
  );
}
