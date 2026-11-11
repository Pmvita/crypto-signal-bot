import { cn } from "@/lib/utils";

/** Tiny close-only polyline for desk market preview / readiness board. */
export function Sparkline({
  values,
  className,
  width = 120,
  height = 28,
  marker,
}: {
  values: number[];
  className?: string;
  width?: number;
  height?: number;
  /** Optional horizontal price marker (e.g. Donchian breakout level). */
  marker?: number | null;
}) {
  if (values.length < 2) {
    return (
      <svg
        width={width}
        height={height}
        className={cn("text-muted-foreground", className)}
        aria-hidden
      >
        <line
          x1={0}
          y1={height / 2}
          x2={width}
          y2={height / 2}
          stroke="currentColor"
          strokeWidth={1}
          strokeDasharray="2 3"
          opacity={0.5}
        />
      </svg>
    );
  }

  const withMarker = marker != null && Number.isFinite(marker) ? [...values, marker] : values;
  const min = Math.min(...withMarker);
  const max = Math.max(...withMarker);
  const span = max - min || 1;
  const pad = 2;
  const yFor = (v: number) => pad + (1 - (v - min) / span) * (height - pad * 2);
  const points = values
    .map((v, i) => {
      const x = pad + (i / (values.length - 1)) * (width - pad * 2);
      const y = yFor(v);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  const up = values[values.length - 1]! >= values[0]!;
  const markerY = marker != null && Number.isFinite(marker) ? yFor(marker) : null;

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      className={cn(up ? "text-[var(--gain)]" : "text-[var(--loss)]", className)}
      aria-hidden
    >
      {markerY != null ? (
        <line
          x1={0}
          y1={markerY}
          x2={width}
          y2={markerY}
          stroke="var(--amber)"
          strokeWidth={1}
          strokeDasharray="3 2"
          opacity={0.85}
        />
      ) : null}
      <polyline
        fill="none"
        stroke="currentColor"
        strokeWidth={1.5}
        strokeLinejoin="round"
        strokeLinecap="round"
        points={points}
      />
    </svg>
  );
}
