import type { Metadata } from "next";
import { IBM_Plex_Mono, IBM_Plex_Sans_Condensed } from "next/font/google";

import { DeskShell } from "@/components/desk-shell";

import "./globals.css";

const plexSans = IBM_Plex_Sans_Condensed({
  variable: "--font-heading",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
});

const plexMono = IBM_Plex_Mono({
  variable: "--font-mono",
  subsets: ["latin"],
  weight: ["400", "500"],
});

export const metadata: Metadata = {
  title: "CSB — Crypto Signal Bot",
  description: "Local paper-trading crypto signal desk (phase 1).",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${plexSans.variable} ${plexMono.variable} dark h-full`}
    >
      <body
        className="min-h-full font-sans antialiased"
        style={
          {
            "--font-sans": "var(--font-heading)",
          } as React.CSSProperties
        }
      >
        <DeskShell>{children}</DeskShell>
      </body>
    </html>
  );
}
