"use client";

import useSWR, { type KeyedMutator } from "swr";

import type { BacktestRun, CandleHistorySummary, RiskLimits, RiskResponse } from "@/lib/types";

export const ENGINE_URL =
  process.env.NEXT_PUBLIC_ENGINE_URL?.replace(/\/$/, "") || "http://127.0.0.1:8787";

export class EngineError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

/** Prefer FastAPI `{ detail: string }` bodies; fall back to raw text / Error.message. */
export function engineErrorMessage(err: unknown): string {
  if (err instanceof EngineError || err instanceof Error) {
    const raw = err.message?.trim() || "";
    if (raw.startsWith("{") || raw.startsWith("[")) {
      try {
        const parsed = JSON.parse(raw) as { detail?: unknown };
        if (typeof parsed.detail === "string" && parsed.detail.trim()) return parsed.detail.trim();
        if (Array.isArray(parsed.detail)) {
          const parts = parsed.detail
            .map((item) => {
              if (typeof item === "string") return item;
              if (item && typeof item === "object" && "msg" in item) {
                return String((item as { msg: unknown }).msg);
              }
              return JSON.stringify(item);
            })
            .filter(Boolean);
          if (parts.length) return parts.join("; ");
        }
      } catch {
        /* keep raw */
      }
    }
    return raw || "Request failed";
  }
  return String(err);
}

async function readError(res: Response): Promise<EngineError> {
  const detail = await res.text().catch(() => res.statusText);
  return new EngineError(detail || res.statusText, res.status);
}

export async function fetcher<T>(path: string): Promise<T> {
  const res = await fetch(`${ENGINE_URL}${path}`, { cache: "no-store" });
  if (!res.ok) throw await readError(res);
  return res.json() as Promise<T>;
}

export async function putRisk(limits: RiskLimits): Promise<RiskResponse> {
  const res = await fetch(`${ENGINE_URL}/api/risk`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(limits),
  });
  if (!res.ok) throw await readError(res);
  return res.json() as Promise<RiskResponse>;
}

export async function setKillSwitch(engaged: boolean): Promise<RiskResponse> {
  const res = await fetch(`${ENGINE_URL}/api/kill-switch`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ engaged }),
  });
  if (!res.ok) throw await readError(res);
  return res.json() as Promise<RiskResponse>;
}

export async function runBacktest(): Promise<BacktestRun> {
  const res = await fetch(`${ENGINE_URL}/api/backtests`, { method: "POST" });
  if (!res.ok) throw await readError(res);
  return res.json() as Promise<BacktestRun>;
}

export async function runBackfill(days?: number): Promise<{
  days: number;
  stored: Record<string, number>;
  summary: CandleHistorySummary;
}> {
  const res = await fetch(`${ENGINE_URL}/api/backfill`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(days != null ? { days } : {}),
  });
  if (!res.ok) throw await readError(res);
  return res.json() as Promise<{
    days: number;
    stored: Record<string, number>;
    summary: CandleHistorySummary;
  }>;
}

export function useEngine<T>(
  path: string | null,
  refreshMs = 5000,
): {
  data: T | undefined;
  error: Error | undefined;
  isLoading: boolean;
  mutate: KeyedMutator<T>;
} {
  const { data, error, isLoading, mutate } = useSWR<T>(
    path ? `${ENGINE_URL}${path}` : null,
    () => fetcher<T>(path!),
    { refreshInterval: refreshMs, revalidateOnFocus: true, shouldRetryOnError: true },
  );
  return { data, error, isLoading, mutate };
}
