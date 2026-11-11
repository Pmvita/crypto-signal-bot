"use strict";

const { app, BrowserWindow, ipcMain, shell } = require("electron");
const path = require("node:path");
const fs = require("node:fs");

// Must run before ready so userData is %APPDATA%\Crypto Signal Bot\
app.setName("Crypto Signal Bot");

const paths = require("./lib/paths.cjs");
const python = require("./lib/python.cjs");
const engine = require("./lib/engine.cjs");
const desk = require("./lib/desk.cjs");
const updates = require("./lib/updates.cjs");
const envFile = require("./lib/env-file.cjs");

let mainWindow = null;
let pythonPath = null;
let setupState = {
  ready: false,
  error: null,
  dataRoot: null,
  appRoot: null,
  packaged: false,
  gitCheckout: false,
  envPath: null,
  venvPython: null,
};
let quitting = false;

function send(channel, payload) {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send(channel, payload);
  }
}

function createWindow(deskUrl) {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 840,
    minWidth: 960,
    minHeight: 640,
    title: "Crypto Signal Bot",
    backgroundColor: "#0a0a0a",
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  const load = () => {
    mainWindow.loadURL(deskUrl).catch(() => {
      // Desk may still be compiling; retry a few times.
    });
  };
  load();
  mainWindow.webContents.on("did-fail-load", (_e, code, _desc, url, isMainFrame) => {
    if (!isMainFrame || quitting) return;
    if (url && url.startsWith(deskUrl)) {
      setTimeout(load, 1500);
    }
  });
  mainWindow.on("closed", () => {
    mainWindow = null;
  });
}

async function bootstrap() {
  setupState.packaged = app.isPackaged;
  setupState.appRoot = paths.getAppRoot();
  setupState.dataRoot = paths.getDataRoot();
  setupState.gitCheckout = paths.isGitCheckout();
  setupState.envPath = paths.getEnvFilePath();

  const log = (msg) => send("csb:engine:event", { type: "log", message: String(msg), ts: Date.now() });

  try {
    python.ensureDataDir();
    const envInfo = python.ensureEnvFile(log);
    setupState.envPath = envInfo.path;

    const py = await python.ensurePythonEnv(log);
    pythonPath = py.pythonPath;
    setupState.venvPython = pythonPath;

    const deskInfo = await desk.ensureDesk({
      isPackaged: app.isPackaged,
      onLog: log,
    });

    createWindow(deskInfo.url);

    try {
      await engine.startEngine(pythonPath, {
        onLog: (line, stream) =>
          send("csb:engine:event", { type: "log", message: line, stream, ts: Date.now() }),
        onExit: (code) =>
          send("csb:engine:event", {
            type: "exit",
            code,
            status: engine.getStatusSnapshot(),
            ts: Date.now(),
          }),
      });
      send("csb:engine:event", {
        type: "status",
        status: { ...engine.getStatusSnapshot(), healthy: true },
        ts: Date.now(),
      });
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      log(`Engine start deferred: ${message}`);
      send("csb:engine:event", {
        type: "status",
        status: { ...engine.getStatusSnapshot(), healthy: false, error: message },
        ts: Date.now(),
      });
    }

    setupState.ready = true;
    setupState.error = null;
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    setupState.ready = false;
    setupState.error = message;
    if (!mainWindow) {
      createWindow(desk.getDeskUrl());
    }
    send("csb:engine:event", { type: "setup-error", message, ts: Date.now() });
  }
}

async function ensurePythonPath() {
  if (pythonPath) return pythonPath;
  const py = await python.ensurePythonEnv((msg) =>
    send("csb:engine:event", { type: "log", message: msg, ts: Date.now() }),
  );
  pythonPath = py.pythonPath;
  setupState.venvPython = pythonPath;
  return pythonPath;
}

async function restartEngineChild() {
  const py = await ensurePythonPath();
  await engine.stopEngine();
  const status = await engine.startEngine(py, {
    onLog: (line, stream) =>
      send("csb:engine:event", { type: "log", message: line, stream, ts: Date.now() }),
    onExit: (code) =>
      send("csb:engine:event", {
        type: "exit",
        code,
        status: engine.getStatusSnapshot(),
        ts: Date.now(),
      }),
  });
  const health = await engine.probeHealth();
  const payload = { ...status, healthy: health.ok };
  send("csb:engine:event", { type: "status", status: payload, ts: Date.now() });
  return payload;
}

function registerIpc() {
  ipcMain.handle("csb:setup:getState", async () => ({
    ...setupState,
    engine: engine.getStatusSnapshot(),
    backfillRunning: engine.isBackfillRunning(),
  }));

  ipcMain.handle("csb:settings:getLlm", async () => {
    return envFile.getLlmSettingsPublic(paths.getEnvFilePath());
  });

  ipcMain.handle("csb:settings:saveLlm", async (_evt, input = {}) => {
    const envPath = paths.getEnvFilePath();
    const saved = envFile.saveLlmSettings(envPath, input || {});
    setupState.envPath = envPath;
    let engineStatus = null;
    let engineRestartError = null;
    try {
      engineStatus = await restartEngineChild();
    } catch (err) {
      engineRestartError = err instanceof Error ? err.message : String(err);
    }
    return {
      settings: saved,
      engineRestarted: Boolean(engineStatus?.healthy),
      engineStatus,
      engineRestartError,
    };
  });

  ipcMain.handle("csb:engine:status", async () => {
    const snap = engine.getStatusSnapshot();
    const health = await engine.probeHealth();
    return { ...snap, healthy: health.ok };
  });

  ipcMain.handle("csb:engine:start", async () => {
    await ensurePythonPath();
    const status = await engine.startEngine(pythonPath, {
      onLog: (line, stream) =>
        send("csb:engine:event", { type: "log", message: line, stream, ts: Date.now() }),
      onExit: (code) =>
        send("csb:engine:event", {
          type: "exit",
          code,
          status: engine.getStatusSnapshot(),
          ts: Date.now(),
        }),
    });
    const health = await engine.probeHealth();
    const payload = { ...status, healthy: health.ok };
    send("csb:engine:event", { type: "status", status: payload, ts: Date.now() });
    return payload;
  });

  ipcMain.handle("csb:engine:stop", async () => {
    const status = await engine.stopEngine();
    send("csb:engine:event", { type: "status", status: { ...status, healthy: false }, ts: Date.now() });
    return { ...status, healthy: false };
  });

  ipcMain.handle("csb:jobs:backfill", async (_evt, opts = {}) => {
    if (!pythonPath) throw new Error("Python environment is not ready");
    send("csb:jobs:log", { type: "start", ts: Date.now() });
    try {
      const result = await engine.runBackfill(pythonPath, {
        days: opts.days,
        onLog: (chunk) => send("csb:jobs:log", { type: "chunk", text: chunk, ts: Date.now() }),
      });
      send("csb:jobs:log", { type: "done", ok: true, ts: Date.now() });
      return result;
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      send("csb:jobs:log", { type: "done", ok: false, message, ts: Date.now() });
      throw err;
    }
  });

  ipcMain.handle("csb:shell:openDataFolder", async () => {
    const dir = paths.getDataRoot();
    fs.mkdirSync(dir, { recursive: true });
    return shell.openPath(dir);
  });

  ipcMain.handle("csb:shell:openEnvLocation", async () => {
    const envPath = paths.getEnvFilePath();
    if (fs.existsSync(envPath)) {
      shell.showItemInFolder(envPath);
      return { ok: true, path: envPath };
    }
    const dir = paths.getDataRoot();
    await shell.openPath(dir);
    return { ok: false, path: envPath, message: ".env not found yet" };
  });

  ipcMain.handle("csb:shell:openExternal", async (_evt, url) => {
    if (typeof url !== "string" || !/^https:\/\//i.test(url)) {
      throw new Error("Only https URLs are allowed");
    }
    await shell.openExternal(url);
    return { ok: true };
  });

  ipcMain.handle("csb:shell:restartApp", async () => {
    app.relaunch();
    app.exit(0);
  });

  ipcMain.handle("csb:updates:check", async () => {
    const root = paths.getAppRoot();
    const onProgress = (message) => send("csb:updates:progress", { message, ts: Date.now() });
    if (!updates.isGitCheckout(root)) {
      let tip = null;
      try {
        tip = await updates.checkRemoteTipViaApi();
      } catch {
        tip = null;
      }
      return {
        ...(await updates.checkForUpdates(root, { onProgress })),
        remoteTip: tip,
      };
    }
    return updates.checkForUpdates(root, { onProgress });
  });

  ipcMain.handle("csb:updates:apply", async () => {
    const root = paths.getAppRoot();
    const onProgress = (message) => send("csb:updates:progress", { message, ts: Date.now() });
    const result = await updates.applyUpdates(root, { onProgress });
    if (result.ok && result.engineRestartSuggested && pythonPath) {
      try {
        await engine.stopEngine();
        await engine.startEngine(pythonPath, {
          onLog: (line, stream) =>
            send("csb:engine:event", { type: "log", message: line, stream, ts: Date.now() }),
          onExit: (code) =>
            send("csb:engine:event", {
              type: "exit",
              code,
              status: engine.getStatusSnapshot(),
              ts: Date.now(),
            }),
        });
        result.engineRestarted = true;
      } catch (err) {
        result.engineRestarted = false;
        result.engineRestartError = err instanceof Error ? err.message : String(err);
      }
    }
    return result;
  });
}

app.whenReady().then(async () => {
  registerIpc();
  await bootstrap();
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});

app.on("before-quit", async (event) => {
  if (quitting) return;
  event.preventDefault();
  quitting = true;
  try {
    await engine.stopEngine();
  } catch {
    // ignore
  }
  try {
    await desk.stopDesk();
  } catch {
    // ignore
  }
  app.exit(0);
});
