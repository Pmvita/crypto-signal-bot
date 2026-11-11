"use client";

import useSWR, { type KeyedMutator } from "swr";

import type { BacktestRun, RiskLimits, RiskResponse } from "@/lib/types";

export const ENGINE_URL =
  process.env.NEXT_PUBLIC_ENGINE_URL?.replace(/\/$/, "") || "http://127.0.0.1:8787";

export class EngineError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

export async function fetcher<T>(path: string): Promise<T> {
  const res = await fetch(`${ENGINE_URL}${path}`, { cache: "no-store" });
  if (!res.ok) {
    const detail = await res.text().catch(() => res.statusText);
    throw new EngineError(detail || res.statusText, res.status);
  }
  return res.json() as Promise<T>;
}

export async function putRisk(limits: RiskLimits): Promise<RiskResponse> {
  const res = await fetch(`${ENGINE_URL}/api/risk`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(limits),
  });
  if (!res.ok) throw new EngineError(await res.text(), res.status);
  return res.json() as Promise<RiskResponse>;
}

export async function setKillSwitch(engaged: boolean): Promise<RiskResponse> {
  const res = await fetch(`${ENGINE_URL}/api/kill-switch`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ engaged }),
  });
  if (!res.ok) throw new EngineError(await res.text(), res.status);
  return res.json() as Promise<RiskResponse>;
}

export async function runBacktest(): Promise<BacktestRun> {
  const res = await fetch(`${ENGINE_URL}/api/backtests`, { method: "POST" });
  if (!res.ok) throw new EngineError(await res.text(), res.status);
  return res.json() as Promise<BacktestRun>;
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
