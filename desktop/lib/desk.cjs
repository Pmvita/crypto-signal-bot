"use strict";

/**
 * Desk host: Option A fallback — spawn Next on 127.0.0.1:3000 when needed.
 * Reuses an already-running desk if / responds.
 */

const { spawn } = require("node:child_process");
const http = require("node:http");
const fs = require("node:fs");
const path = require("node:path");

const paths = require("./paths.cjs");

const DESK_HOST = "127.0.0.1";
const DESK_PORT = 3000;

let deskProc = null;
let deskMode = null; // "reused" | "dev" | "start" | null

function probeDesk(timeoutMs = 1500) {
  return new Promise((resolve) => {
    const req = http.get(
      {
        host: DESK_HOST,
        port: DESK_PORT,
        path: "/",
        timeout: timeoutMs,
      },
      (res) => {
        res.resume();
        resolve({ ok: res.statusCode != null && res.statusCode < 500, statusCode: res.statusCode });
      },
    );
    req.on("error", () => resolve({ ok: false }));
    req.on("timeout", () => {
      req.destroy();
      resolve({ ok: false });
    });
  });
}

async function waitForDesk(timeoutMs = 120000, onProgress = () => {}) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    const health = await probeDesk();
    if (health.ok) return true;
    onProgress("Waiting for desk on 127.0.0.1:3000…");
    await new Promise((r) => setTimeout(r, 750));
  }
  return false;
}

function npmCommand() {
  return process.platform === "win32" ? "npm.cmd" : "npm";
}

function npxCommand() {
  return process.platform === "win32" ? "npx.cmd" : "npx";
}

/**
 * @param {{ isPackaged: boolean, onLog?: (line: string) => void }} opts
 */
async function ensureDesk(opts) {
  const onLog = opts.onLog || (() => {});
  const existing = await probeDesk();
  if (existing.ok) {
    deskMode = "reused";
    onLog("Reusing desk already listening on 127.0.0.1:3000");
    return { url: `http://${DESK_HOST}:${DESK_PORT}`, mode: deskMode, reused: true };
  }

  const dashboardDir = paths.getDashboardDir();
  if (!fs.existsSync(dashboardDir)) {
    throw new Error(`Dashboard directory missing: ${dashboardDir}`);
  }

  if (!opts.isPackaged) {
    onLog(`Starting Next.js desk (npm run dev) in ${dashboardDir}…`);
    deskProc = spawn(npmCommand(), ["run", "dev"], {
      cwd: dashboardDir,
      env: { ...process.env, FORCE_COLOR: "0" },
      windowsHide: true,
      stdio: ["ignore", "pipe", "pipe"],
      // Windows needs a shell to resolve npm.cmd reliably.
      shell: process.platform === "win32",
    });
    deskMode = "dev";
  } else {
    const standaloneServer = path.join(dashboardDir, "server.js");
    const nextBin = path.join(dashboardDir, "node_modules", "next", "dist", "bin", "next");
    if (fs.existsSync(standaloneServer)) {
      onLog("Starting Next.js desk (standalone server.js)…");
      deskProc = spawn(process.execPath, [standaloneServer], {
        cwd: dashboardDir,
        env: {
          ...process.env,
          ELECTRON_RUN_AS_NODE: "1",
          PORT: String(DESK_PORT),
          HOSTNAME: DESK_HOST,
          FORCE_COLOR: "0",
        },
        windowsHide: true,
        stdio: ["ignore", "pipe", "pipe"],
      });
      deskMode = "start";
    } else if (fs.existsSync(nextBin)) {
      onLog("Starting Next.js desk (next start)…");
      deskProc = spawn(process.execPath, [nextBin, "start", "-H", DESK_HOST, "-p", String(DESK_PORT)], {
        cwd: dashboardDir,
        env: { ...process.env, ELECTRON_RUN_AS_NODE: "1", FORCE_COLOR: "0" },
        windowsHide: true,
        stdio: ["ignore", "pipe", "pipe"],
      });
      deskMode = "start";
    } else {
      onLog("Starting Next.js desk (npx next start)…");
      deskProc = spawn(npxCommand(), ["next", "start", "-H", DESK_HOST, "-p", String(DESK_PORT)], {
        cwd: dashboardDir,
        env: { ...process.env, FORCE_COLOR: "0" },
        windowsHide: true,
        stdio: ["ignore", "pipe", "pipe"],
        shell: process.platform === "win32",
      });
      deskMode = "start";
    }
  }

  deskProc.stdout.on("data", (buf) => onLog(buf.toString().trimEnd()));
  deskProc.stderr.on("data", (buf) => onLog(buf.toString().trimEnd()));
  deskProc.on("exit", (code) => {
    onLog(`Desk process exited (${code})`);
    deskProc = null;
  });

  const ok = await waitForDesk(180000, onLog);
  if (!ok) {
    await stopDesk();
    throw new Error("Desk failed to become ready on 127.0.0.1:3000");
  }
  return { url: `http://${DESK_HOST}:${DESK_PORT}`, mode: deskMode, reused: false };
}

function stopDesk() {
  return new Promise((resolve) => {
    if (!deskProc) {
      resolve();
      return;
    }
    const proc = deskProc;
    deskProc = null;
    let settled = false;
    const done = () => {
      if (settled) return;
      settled = true;
      resolve();
    };
    proc.once("exit", done);
    try {
      if (process.platform === "win32") {
        spawn("taskkill", ["/pid", String(proc.pid), "/T", "/F"], { windowsHide: true });
      } else {
        proc.kill("SIGTERM");
      }
    } catch {
      // ignore
    }
    setTimeout(done, 3000);
  });
}

function getDeskUrl() {
  return `http://${DESK_HOST}:${DESK_PORT}`;
}

module.exports = {
  DESK_HOST,
  DESK_PORT,
  probeDesk,
  ensureDesk,
  stopDesk,
  getDeskUrl,
};
