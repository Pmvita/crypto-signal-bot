"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { putRisk } from "@/lib/api";
import type { RiskLimits } from "@/lib/types";

export function RiskForm({
  limits,
  onSaved,
}: {
  limits: RiskLimits;
  onSaved: () => void;
}) {
  const [form, setForm] = useState(limits);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [ok, setOk] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setOk(false);
    try {
      await putRisk(form);
      setOk(true);
      onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={(e) => void submit(e)} className="max-w-md space-y-4">
      <div className="space-y-1.5">
        <Label htmlFor="max_position_pct">Max position % of equity</Label>
        <Input
          id="max_position_pct"
          type="number"
          step="0.1"
          min={1}
          max={100}
          value={form.max_position_pct}
          onChange={(e) => setForm({ ...form, max_position_pct: Number(e.target.value) })}
          className="font-mono"
        />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="max_open_positions">Max open positions</Label>
        <Input
          id="max_open_positions"
          type="number"
          min={1}
          max={20}
          value={form.max_open_positions}
          onChange={(e) => setForm({ ...form, max_open_positions: Number(e.target.value) })}
          className="font-mono"
        />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="daily_loss_limit_pct">Daily loss limit %</Label>
        <Input
          id="daily_loss_limit_pct"
          type="number"
          step="0.1"
          min={0.5}
          max={50}
          value={form.daily_loss_limit_pct}
          onChange={(e) => setForm({ ...form, daily_loss_limit_pct: Number(e.target.value) })}
          className="font-mono"
        />
      </div>
      <Button type="submit" disabled={busy} className="bg-[var(--amber)] text-black hover:bg-[var(--amber)]/90">
        Save limits
      </Button>
      {ok ? <p className="font-mono text-xs text-[var(--gain)]">Saved.</p> : null}
      {error ? <p className="font-mono text-xs text-[var(--loss)]">{error}</p> : null}
    </form>
  );
}
