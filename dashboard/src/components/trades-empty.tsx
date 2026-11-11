import Link from "next/link";

import type { Action, SignalRow, Status } from "@/lib/types";

function latestActionBySymbol(signals: SignalRow[]): { symbol: string; action: Action }[] {
  const seen = new Set<string>();
  const out: { symbol: string; action: Action }[] = [];
  for (const row of signals) {
    if (seen.has(row.symbol)) continue;
    seen.add(row.symbol);
    out.push({ symbol: row.symbol, action: row.action });
  }
  return out;
}

export function TradesEmpty({
  status,
  signals,
}: {
  status: Status | undefined;
  signals: SignalRow[] | undefined;
}) {
  const kill = Boolean(status?.risk.kill_switch);
  const halted = Boolean(status?.risk.halted);
  const heartbeat = status?.heartbeat;
  const loopOk = heartbeat?.status === "ok";
  const loopError = heartbeat?.status === "error";
  const latest = signals ? latestActionBySymbol(signals) : [];
  const allHold = latest.length > 0 && latest.every((r) => r.action === "hold");
  const hasTradeSignal = latest.some((r) => r.action === "enter" || r.action === "exit");

  let why: string;
  if (kill) {
    why =
      "Kill switch is engaged, so new paper entries are blocked. Disengage it in Settings if you want the loop to trade again.";
  } else if (halted) {
    why =
      "Daily loss halt is active. New entries stay blocked until the next risk day or you adjust limits in Settings.";
  } else if (loopError) {
    why = `The paper loop’s last cycle failed${heartbeat?.error ? `: ${heartbeat.error}` : "."} Check the engine log / restart the desk.`;
  } else if (!heartbeat) {
    why =
      "No paper-loop heartbeat yet. Keep the desk/engine running (`serve` / desktop app) so cycles can evaluate bars and place orders.";
  } else if (allHold) {
    const symbols = latest.map((r) => r.symbol).join(", ");
    why = `Latest signals are HOLD (${symbols}). HOLD bars do not create orders — fills appear only on ENTER / EXIT.`;
  } else if (hasTradeSignal) {
    why =
      "Recent signals include ENTER/EXIT, but nothing is in the order log yet. Wait for the next cycle, or check Signals for reject reasons.";
  } else if (signals && signals.length === 0) {
    why =
      "No signals have been recorded yet. Leave the paper loop running until it evaluates a closed 4h bar.";
  } else {
    why =
      "The paper broker only logs fills and risk rejections. Until strategy ENTER/EXIT fires, this list stays empty.";
  }

  return (
    <div className="space-y-3 px-1 py-2">
      <p className="font-mono text-sm text-[var(--amber)]">No paper trades yet</p>
      <p className="max-w-2xl font-mono text-xs leading-relaxed text-muted-foreground">{why}</p>
      <ul className="max-w-2xl list-disc space-y-1.5 pl-4 font-mono text-[11px] leading-relaxed text-muted-foreground">
        <li>
          Paper loop status:{" "}
          <span className={loopOk ? "text-[var(--gain)]" : loopError ? "text-[var(--loss)]" : ""}>
            {loopOk ? "running" : loopError ? "error" : heartbeat ? heartbeat.status : "waiting"}
          </span>
          {kill ? " · kill switch ENGAGED" : ""}
          {halted ? " · daily halt ON" : ""}
        </li>
        <li>
          Orders are written when risk allows a buy/sell through the paper broker — not on every signal.
        </li>
        <li>
          Review{" "}
          <Link href="/signals" className="text-[var(--amber)] underline-offset-2 hover:underline">
            Signals
          </Link>{" "}
          for HOLD vs ENTER/EXIT, and{" "}
          <Link href="/settings" className="text-[var(--amber)] underline-offset-2 hover:underline">
            Settings
          </Link>{" "}
          for kill switch / risk limits.
        </li>
      </ul>
    </div>
  );
}
