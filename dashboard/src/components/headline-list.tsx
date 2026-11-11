import { Badge } from "@/components/ui/badge";
import { timeUtc } from "@/lib/format";
import type { HeadlineRow } from "@/lib/types";

export function HeadlineList({
  rows,
  scoringEnabled,
}: {
  rows: HeadlineRow[];
  scoringEnabled: boolean;
}) {
  if (rows.length === 0) {
    return <p className="font-mono text-xs text-muted-foreground">No headlines stored</p>;
  }

  return (
    <div className="space-y-2">
      {rows.map((h) => (
        <div key={h.id} className="border border-border/70 bg-[#0c0c0c] px-3 py-2">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-[10px] uppercase tracking-wide text-cyan-400/90">
              {h.source}
            </span>
            {!scoringEnabled || h.score_status === "unscored" ? (
              <Badge variant="outline" className="font-mono text-[10px]">
                unscored
              </Badge>
            ) : (
              <Badge variant="outline" className="font-mono text-[10px]">
                {h.score_status}
              </Badge>
            )}
            <span className="ml-auto font-mono text-[10px] text-muted-foreground">
              {timeUtc(h.published_at)}
            </span>
          </div>
          <a
            href={h.url}
            target="_blank"
            rel="noreferrer"
            className="mt-1 block font-mono text-sm text-foreground hover:text-[var(--amber)]"
          >
            {h.title}
          </a>
          {scoringEnabled && h.scores.length > 0 ? (
            <ul className="mt-2 space-y-1 font-mono text-[11px] text-muted-foreground">
              {h.scores.map((s) => (
                <li key={`${h.id}-${s.coin}`}>
                  {s.coin} dir={s.direction} str={s.strength.toFixed(2)} conf=
                  {s.confidence.toFixed(2)} — {s.rationale}
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ))}
    </div>
  );
}
