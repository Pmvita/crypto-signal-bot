import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";

export function LiveTradingNotice() {
  return (
    <Alert className="border-[var(--amber)]/30 bg-[var(--amber)]/5">
      <AlertTitle className="text-[var(--amber)]">Live trading not available</AlertTitle>
      <AlertDescription className="font-mono text-xs text-muted-foreground">
        Phase 1 is paper trading only. No code path places orders on an exchange. Live execution is
        reserved for a later phase.
      </AlertDescription>
    </Alert>
  );
}
