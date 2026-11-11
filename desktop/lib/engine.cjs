"use strict";

const { spawn } = require("node:child_process");
const http = require("node:http");

const paths = require("./paths.cjs");

const ENGINE_PORT = 8787;
const ENGINE_HOST = "127.0.0.1";

let engineProc = null;
let backfillProc = null;
let lastExit = null;

function getStatusSnapshot() {
  return {
    running: Boolean(engineProc && engineProc.exitCode === null && !engineProc.killed),
    pid: engineProc?.pid ?? null,
    port: ENGINE_PORT,
    host: ENGINE_HOST,
    lastExit,
  };
}

function probeHealth(timeoutMs = 1500) {
  return new Promise((resolve) => {
    const req = http.get(
      {
        host: ENGINE_HOST,
        port: ENGINE_PORT,
        path: "/api/status",
        timeout: timeoutMs,
      },
      (res) => {
        let body = "";
        res.on("data", (c) => {
          body += c;
        });
        res.on("end", () => {
          resolve({
            ok: res.statusCode === 200,
            statusCode: res.statusCode,
            body,
          });
        });
      },
    );
    req.on("error", () => resolve({ ok: false }));
    req.on("timeout", () => {
      req.destroy();
      resolve({ ok: false });
    });
  });
}

async function waitForHealthy(timeoutMs = 45000, onProgress = () => {}) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    const health = await probeHealth();
    if (health.ok) return true;
    onProgress("Waiting for engine health…");
    await new Promise((r) => setTimeout(r, 500));
  }
  return false;
}

function stopEngine() {
  return new Promise((resolve) => {
    if (!engineProc) {
      resolve(getStatusSnapshot());
      return;
    }
    const proc = engineProc;
    engineProc = null;
    let settled = false;
    const done = () => {
      if (settled) return;
      settled = true;
      resolve(getStatusSnapshot());
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
    setTimeout(() => {
      try {
        proc.kill("SIGKILL");
      } catch {
        // ignore
      }
      done();
    }, 2500);
  });
}

/**
 * @param {string} pythonPath
 * @param {{ onLog?: (line: string, stream: string) => void, onExit?: (code: number|null) => void }} [hooks]
 */
async function startEngine(pythonPath, hooks = {}) {
  const onLog = hooks.onLog || (() => {});
  const onExit = hooks.onExit || (() => {});

  if (engineProc && engineProc.exitCode === null) {
    const healthy = await probeHealth();
    if (healthy.ok) return getStatusSnapshot();
    await stopEngine();
  }

  const already = await probeHealth();
  if (already.ok) {
    onLog("Engine already responding on 127.0.0.1:8787 — reusing.", "system");
    return { ...getStatusSnapshot(), running: true, reused: true };
  }

  const env = paths.engineChildEnv();
  engineProc = spawn(pythonPath, ["-m", "csb", "serve"], {
    cwd: paths.getDataRoot(),
    env,
    windowsHide: true,
    stdio: ["ignore", "pipe", "pipe"],
  });
  lastExit = null;

  const attach = (stream) => {
    engineProc[stream].on("data", (buf) => {
      const text = buf.toString();
      for (const line of text.split(/\r?\n/)) {
        if (line.trim()) onLog(line, stream);
      }
    });
  };
  attach("stdout");
  attach("stderr");

  engineProc.on("exit", (code, signal) => {
    lastExit = { code, signal, at: Date.now() };
    engineProc = null;
    onExit(code);
  });

  const ok = await waitForHealthy(45000, (msg) => onLog(msg, "system"));
  if (!ok) {
    await stopEngine();
    throw new Error("Engine failed to become healthy on 127.0.0.1:8787");
  }
  return getStatusSnapshot();
}

/**
 * @param {string} pythonPath
 * @param {{ days?: number, onLog?: (line: string) => void }} [opts]
 */
function runBackfill(pythonPath, opts = {}) {
  if (backfillProc) {
    return Promise.reject(new Error("Backfill already running"));
  }
  const onLog = opts.onLog || (() => {});
  const args = ["-m", "csb", "backfill"];
  if (opts.days != null) {
    args.push("--days", String(opts.days));
  }
  return new Promise((resolve, reject) => {
    backfillProc = spawn(pythonPath, args, {
      cwd: paths.getDataRoot(),
      env: paths.engineChildEnv(),
      windowsHide: true,
      stdio: ["ignore", "pipe", "pipe"],
    });
    backfillProc.stdout.on("data", (buf) => onLog(buf.toString()));
    backfillProc.stderr.on("data", (buf) => onLog(buf.toString()));
    backfillProc.on("error", (err) => {
      backfillProc = null;
      reject(err);
    });
    backfillProc.on("exit", (code) => {
      backfillProc = null;
      if (code === 0) resolve({ ok: true, code });
      else reject(new Error(`Backfill exited with code ${code}`));
    });
  });
}

function isBackfillRunning() {
  return Boolean(backfillProc);
}

module.exports = {
  ENGINE_PORT,
  ENGINE_HOST,
  getStatusSnapshot,
  probeHealth,
  waitForHealthy,
  startEngine,
  stopEngine,
  runBackfill,
  isBackfillRunning,
};
