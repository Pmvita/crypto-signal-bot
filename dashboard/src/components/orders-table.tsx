import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { pnlClass, qty, timeUtc, usd } from "@/lib/format";
import type { OrderRow } from "@/lib/types";

export function OrdersTable({ rows }: { rows: OrderRow[] }) {
  if (rows.length === 0) {
    return <p className="font-mono text-xs text-muted-foreground">No orders yet</p>;
  }
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>When</TableHead>
          <TableHead>Symbol</TableHead>
          <TableHead>Side</TableHead>
          <TableHead>Status</TableHead>
          <TableHead className="text-right">Qty</TableHead>
          <TableHead className="text-right">Fill</TableHead>
          <TableHead className="text-right">Fee</TableHead>
          <TableHead className="text-right">PnL</TableHead>
          <TableHead>Notes</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((r) => (
          <TableRow key={r.id}>
            <TableCell className="font-mono text-[10px] text-muted-foreground">
              {timeUtc(r.created_at)}
            </TableCell>
            <TableCell className="font-mono text-[var(--amber)]">{r.symbol}</TableCell>
            <TableCell className="font-mono uppercase">{r.side}</TableCell>
            <TableCell
              className={`font-mono text-xs ${
                r.status === "filled" ? "text-[var(--gain)]" : "text-[var(--loss)]"
              }`}
            >
              {r.status}
            </TableCell>
            <TableCell className="text-right font-mono">{qty(r.qty)}</TableCell>
            <TableCell className="text-right font-mono">{usd(r.fill_price)}</TableCell>
            <TableCell className="text-right font-mono">{usd(r.fee)}</TableCell>
            <TableCell className={`text-right font-mono ${pnlClass(r.realized_pnl)}`}>
              {usd(r.realized_pnl)}
            </TableCell>
            <TableCell className="max-w-[220px] truncate font-mono text-[10px] text-muted-foreground">
              {r.reject_reason || r.notes.join("; ") || "—"}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
