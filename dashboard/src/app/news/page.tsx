"use client";

import { EngineOffline } from "@/components/engine-offline";
import { HeadlineList } from "@/components/headline-list";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useEngine } from "@/lib/api";
import { timeUtc } from "@/lib/format";
import type { NewsResponse } from "@/lib/types";

export default function NewsPage() {
  const { data, error, isLoading } = useEngine<NewsResponse>("/api/news?limit=80", 10000);

  if (error) return <EngineOffline error={error} />;
  if (isLoading && !data) return <Skeleton className="h-40 w-full" />;

  const scoringOn = Boolean(data?.scoring.enabled);

  return (
    <div className="space-y-6">
      <header>
        <h1 className="font-heading text-2xl font-semibold tracking-wide text-[var(--amber)]">
          News
        </h1>
        <p className="mt-1 font-mono text-xs text-muted-foreground">
          RSS headlines and optional LLM scores
        </p>
      </header>

      {!scoringOn ? (
        <p className="font-mono text-xs text-cyan-400/90">
          Scoring off — no LLM API key configured
          {data?.scoring.reason ? ` (${data.scoring.reason})` : ""}
        </p>
      ) : (
        <p className="font-mono text-xs text-cyan-400/90">
          Scoring on · {data?.scoring.provider}/{data?.scoring.model}
        </p>
      )}

      <section className="space-y-2 border border-border bg-[#0c0c0c] p-3">
        <h2 className="font-mono text-[11px] uppercase tracking-[0.16em] text-muted-foreground">
          Sources
        </h2>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Kind</TableHead>
              <TableHead>Last OK</TableHead>
              <TableHead>Count</TableHead>
              <TableHead>Error</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {(data?.sources ?? []).map((s) => (
              <TableRow key={s.name}>
                <TableCell className="font-mono text-cyan-400/90">{s.name}</TableCell>
                <TableCell className="font-mono text-xs">{s.kind}</TableCell>
                <TableCell className="font-mono text-[10px] text-muted-foreground">
                  {timeUtc(s.last_ok_at)}
                </TableCell>
                <TableCell className="font-mono">{s.last_count ?? "—"}</TableCell>
                <TableCell className="max-w-[240px] truncate font-mono text-[10px] text-[var(--loss)]">
                  {s.last_error || "—"}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </section>

      <HeadlineList rows={data?.headlines ?? []} scoringEnabled={scoringOn} />
    </div>
  );
}
