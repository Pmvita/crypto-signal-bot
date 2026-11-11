import { pnlClass, usd } from "@/lib/format";

export function Kpi({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: "gain" | "loss" | "neutral";
}) {
  const color =
    tone === "gain"
      ? "text-[var(--gain)]"
      : tone === "loss"
        ? "text-[var(--loss)]"
        : tone === "neutral"
          ? "text-foreground"
          : "text-foreground";

  return (
    <div className="min-w-0">
      <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
        {label}
      </div>
      <div className={`mt-1 font-mono text-xl tabular-nums ${color}`}>{value}</div>
    </div>
  );
}

export function PnlKpi({ label, value }: { label: string; value: number | null | undefined }) {
  const tone = value == null || value === 0 ? "neutral" : value > 0 ? "gain" : "loss";
  return <Kpi label={label} value={usd(value)} tone={tone} />;
}

export function MoneyKpi({ label, value }: { label: string; value: number | null | undefined }) {
  return <Kpi label={label} value={usd(value)} />;
}

export { pnlClass };
