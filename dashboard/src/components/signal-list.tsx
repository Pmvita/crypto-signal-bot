import { Badge } from "@/components/ui/badge";
import { timeUtc } from "@/lib/format";
import type { Action, NewsState, SignalRow } from "@/lib/types";

function actionBadge(action: Action) {
  switch (action) {
    case "enter":
      return <Badge className="bg-[var(--gain)]/20 text-[var(--gain)]">ENTER</Badge>;
    case "exit":
      return <Badge className="bg-[var(--loss)]/20 text-[var(--loss)]">EXIT</Badge>;
    case "hold":
      return <Badge variant="outline">HOLD</Badge>;
    default: {
      const _exhaustive: never = action;
      return _exhaustive;
    }
  }
}

function newsBadge(state: NewsState) {
  switch (state) {
    case "off":
      return <span className="text-muted-foreground">off</span>;
    case "no_headlines":
      return <span className="text-muted-foreground">no headlines</span>;
    case "neutral":
      return <span className="text-cyan-400/80">neutral</span>;
    case "boost":
      return <span className="text-[var(--gain)]">boost</span>;
    case "veto":
      return <span className="text-[var(--loss)]">veto</span>;
    default: {
      const _exhaustive: never = state;
      return _exhaustive;
    }
  }
}

export function SignalList({ rows, compact = false }: { rows: SignalRow[]; compact?: boolean }) {
  if (rows.length === 0) {
    return <p className="font-mono text-xs text-muted-foreground">No signals yet</p>;
  }

  return (
    <div className="space-y-3">
      {rows.map((s) => (
        <div key={s.id} className="border border-border/80 bg-[#0c0c0c] px-3 py-3">
          <div className="flex flex-wrap items-center gap-2">
            {actionBadge(s.action)}
            <span className="font-mono text-sm text-[var(--amber)]">{s.symbol}</span>
            <span className="font-mono text-[10px] text-muted-foreground">{timeUtc(s.created_at)}</span>
            <span className="ml-auto font-mono text-[10px] uppercase tracking-wide">
              news {newsBadge(s.news_state)}
              {s.news_score != null ? ` · ${s.news_score.toFixed(2)}` : ""}
            </span>
          </div>
          <ul className="mt-2 space-y-1 font-mono text-xs text-muted-foreground">
            {s.reasons.map((r) => (
              <li key={r}>· {r}</li>
            ))}
          </ul>
          {!compact && Object.keys(s.indicators).length > 0 ? (
            <div className="mt-2 flex flex-wrap gap-3 font-mono text-[10px] text-muted-foreground">
              {Object.entries(s.indicators).map(([k, v]) => (
                <span key={k}>
                  {k} {v == null ? "—" : typeof v === "number" ? v.toFixed(4) : String(v)}
                </span>
              ))}
            </div>
          ) : null}
          {!compact && s.headlines.length > 0 ? (
            <div className="mt-2 space-y-1 border-t border-border/60 pt-2">
              {s.headlines.map((h) => (
                <a
                  key={h.id}
                  href={h.url}
                  target="_blank"
                  rel="noreferrer"
                  className="block truncate font-mono text-[11px] text-cyan-400/90 hover:underline"
                >
                  [{h.source}] {h.title}
                </a>
              ))}
            </div>
          ) : null}
          {s.order ? (
            <div className="mt-2 font-mono text-[10px] text-muted-foreground">
              order {s.order.status}
              {s.order.reject_reason ? ` — ${s.order.reject_reason}` : ""}
            </div>
          ) : null}
        </div>
      ))}
    </div>
  );
}
