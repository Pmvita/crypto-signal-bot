"use client";

import { useState } from "react";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { setKillSwitch } from "@/lib/api";

export function KillSwitch({
  engaged,
  onChange,
}: {
  engaged: boolean;
  onChange: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function apply(next: boolean) {
    setBusy(true);
    setError(null);
    try {
      await setKillSwitch(next);
      onChange();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  if (engaged) {
    return (
      <div className="space-y-2">
        <Button
          variant="outline"
          disabled={busy}
          onClick={() => void apply(false)}
          className="border-[var(--amber)] text-[var(--amber)]"
        >
          Disengage kill switch
        </Button>
        {error ? <p className="font-mono text-xs text-[var(--loss)]">{error}</p> : null}
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <AlertDialog>
        <AlertDialogTrigger render={<Button variant="destructive" disabled={busy} />}>
          Engage kill switch
        </AlertDialogTrigger>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Engage kill switch?</AlertDialogTitle>
            <AlertDialogDescription>
              Every order — entries and exits — will be rejected until you disengage. Paper positions
              will not close automatically while the switch is on.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={() => void apply(true)}>Engage</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
      {error ? <p className="font-mono text-xs text-[var(--loss)]">{error}</p> : null}
    </div>
  );
}
