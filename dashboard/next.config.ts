import type { NextConfig } from "next";
import path from "node:path";

/**
 * CSB_DIST_DIR lets release packaging build into `.next-pack` so a running
 * `next dev` desk (`.next`) is not clobbered mid-session.
 */
const nextConfig: NextConfig = {
  output: "standalone",
  distDir: process.env.CSB_DIST_DIR || ".next",
  // Trace from the dashboard package so standalone stays relocatable.
  outputFileTracingRoot: path.join(__dirname),
  cacheComponents: true,
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
