import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { timeUtc, usd } from "@/lib/format";
import type { WatchlistRow } from "@/lib/types";

export function Watchlist({ rows }: { rows: WatchlistRow[] }) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Symbol</TableHead>
          <TableHead className="text-right">Last</TableHead>
          <TableHead>Trend</TableHead>
          <TableHead>Quote</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((r) => (
          <TableRow key={r.symbol}>
            <TableCell className="font-mono text-[var(--amber)]">{r.symbol}</TableCell>
            <TableCell className="text-right font-mono">{usd(r.last)}</TableCell>
            <TableCell className="font-mono text-xs uppercase">
              {r.trend === "up" ? (
                <span className="text-[var(--gain)]">up</span>
              ) : r.trend === "down" ? (
                <span className="text-[var(--loss)]">down</span>
              ) : (
                <span className="text-muted-foreground">—</span>
              )}
            </TableCell>
            <TableCell className="font-mono text-[10px] text-muted-foreground">
              {timeUtc(r.ts)}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
