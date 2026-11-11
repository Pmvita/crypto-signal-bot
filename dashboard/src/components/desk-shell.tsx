"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { EngineControlStrip } from "@/components/engine-control-strip";
import { StatusBar } from "@/components/status-bar";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/", label: "Desk" },
  { href: "/signals", label: "Signals" },
  { href: "/trades", label: "Trades" },
  { href: "/news", label: "News" },
  { href: "/backtest", label: "Backtest" },
  { href: "/settings", label: "Settings" },
] as const;

export function DeskShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  return (
    <div className="flex min-h-screen bg-background text-foreground">
      <aside className="flex w-44 shrink-0 flex-col border-r border-border bg-[#080808]">
        <div className="border-b border-border px-4 py-5">
          <div className="font-heading text-lg font-semibold tracking-[0.08em] text-[var(--amber)]">
            CSB
          </div>
          <div className="mt-1 font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
            Crypto Signal Bot
          </div>
        </div>
        <nav className="flex flex-1 flex-col gap-0.5 p-2">
          {NAV.map((item) => {
            const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "rounded-md px-3 py-2 font-mono text-xs tracking-wide transition-colors",
                  active
                    ? "bg-[var(--amber)]/15 text-[var(--amber)]"
                    : "text-muted-foreground hover:bg-muted hover:text-foreground",
                )}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>
        <div className="border-t border-border px-4 py-3 font-mono text-[10px] text-muted-foreground">
          Phase 1 · paper only
        </div>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <StatusBar />
        <EngineControlStrip />
        <main className="flex-1 overflow-auto p-5">{children}</main>
      </div>
    </div>
  );
}
