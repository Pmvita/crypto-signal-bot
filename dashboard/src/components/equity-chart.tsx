"use client";

import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { usd } from "@/lib/format";

export function EquityChart({
  points,
}: {
  points: Array<{ ts: number; equity: number }>;
}) {
  if (points.length === 0) {
    return (
      <div className="flex h-48 items-center justify-center font-mono text-xs text-muted-foreground">
        No equity points yet
      </div>
    );
  }

  const data = points.map((p) => ({
    ts: p.ts,
    equity: p.equity,
    label: new Date(p.ts).toISOString().slice(5, 16),
  }));

  return (
    <div className="h-48 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid stroke="rgba(255,255,255,0.06)" vertical={false} />
          <XAxis dataKey="label" tick={{ fill: "#737373", fontSize: 10 }} minTickGap={40} />
          <YAxis
            domain={["auto", "auto"]}
            tick={{ fill: "#737373", fontSize: 10 }}
            width={64}
            tickFormatter={(v: number) => `$${Math.round(v)}`}
          />
          <Tooltip
            contentStyle={{
              background: "#111",
              border: "1px solid #333",
              fontFamily: "var(--font-mono)",
              fontSize: 11,
            }}
            formatter={(value) => [usd(Number(value)), "equity"]}
          />
          <Line
            type="monotone"
            dataKey="equity"
            stroke="var(--amber)"
            strokeWidth={1.5}
            dot={false}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
