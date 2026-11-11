import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { ENGINE_URL } from "@/lib/api";

export function EngineOffline({ error }: { error?: Error }) {
  return (
    <Alert variant="destructive" className="border-[var(--loss)]/40 bg-[var(--loss)]/10">
      <AlertTitle>Engine unreachable</AlertTitle>
      <AlertDescription className="font-mono text-xs">
        Cannot reach {ENGINE_URL}. Start it with{" "}
        <code className="text-[var(--amber)]">python -m csb serve</code>
        {error ? ` — ${error.message}` : ""}. Stale numbers are not shown.
      </AlertDescription>
    </Alert>
  );
}
