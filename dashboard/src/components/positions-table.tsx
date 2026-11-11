import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { pnlClass, qty, timeUtc, usd } from "@/lib/format";
import type { PositionRow } from "@/lib/types";

export function PositionsTable({ rows }: { rows: PositionRow[] }) {
  if (rows.length === 0) {
    return <p className="font-mono text-xs text-muted-foreground">No open positions</p>;
  }
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Symbol</TableHead>
          <TableHead className="text-right">Qty</TableHead>
          <TableHead className="text-right">Entry</TableHead>
          <TableHead className="text-right">Last</TableHead>
          <TableHead className="text-right">Stop</TableHead>
          <TableHead className="text-right">uPnL</TableHead>
          <TableHead>Opened</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((r) => (
          <TableRow key={r.symbol}>
            <TableCell className="font-mono text-[var(--amber)]">{r.symbol}</TableCell>
            <TableCell className="text-right font-mono">{qty(r.qty)}</TableCell>
            <TableCell className="text-right font-mono">{usd(r.entry_price)}</TableCell>
            <TableCell className="text-right font-mono">{usd(r.last)}</TableCell>
            <TableCell className="text-right font-mono">{usd(r.stop_price)}</TableCell>
            <TableCell className={`text-right font-mono ${pnlClass(r.unrealized_pnl)}`}>
              {usd(r.unrealized_pnl)}
            </TableCell>
            <TableCell className="font-mono text-[10px] text-muted-foreground">
              {timeUtc(r.entry_ts)}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
