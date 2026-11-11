"use strict";

const fs = require("node:fs");
const path = require("node:path");
const { app } = require("electron");

const DEV_JUNCTION_CANDIDATES = [
  process.env.CSB_BUILD_ROOT,
  "C:\\Users\\user\\Desktop\\csb-build",
].filter(Boolean);

/**
 * Repo / install root: project root in unpackaged dev.
 * Prefer a short junction (e.g. Desktop\\csb-build) when the real path contains `)`,
 * because npm/Next often hang on Windows paren paths.
 * Packaged: electron-builder `extraResources` land in `process.resourcesPath`.
 */
function getAppRoot() {
  if (!app.isPackaged) {
    const real = path.join(__dirname, "..", "..");
    try {
      const realResolved = fs.realpathSync(real).toLowerCase();
      for (const candidate of DEV_JUNCTION_CANDIDATES) {
        if (!fs.existsSync(candidate)) continue;
        const candResolved = fs.realpathSync(candidate).toLowerCase();
        if (candResolved === realResolved) {
          return candidate;
        }
      }
    } catch {
      // fall through to real path
    }
    return real;
  }
  return process.resourcesPath;
}

/**
 * Writable data root for the desktop app: always Electron userData
 * (`%APPDATA%\Crypto Signal Bot\` on Windows when app name is set).
 * CLI/dev without Electron still uses the repo `.env`; desktop path of truth is AppData.
 */
function getDataRoot() {
  return app.getPath("userData");
}

function getEngineDir() {
  return path.join(getAppRoot(), "engine");
}

function getDashboardDir() {
  return path.join(getAppRoot(), "dashboard");
}

function getVenvDir() {
  return path.join(getDataRoot(), ".venv");
}

function getVenvPython() {
  const venv = getVenvDir();
  if (process.platform === "win32") {
    return path.join(venv, "Scripts", "python.exe");
  }
  return path.join(venv, "bin", "python");
}

function getEnvFilePath() {
  return path.join(getDataRoot(), ".env");
}

function getEnvExamplePath() {
  return path.join(getAppRoot(), ".env.example");
}

function getDbPath() {
  return path.join(getDataRoot(), "data", "csb.sqlite3");
}

function isGitCheckout(root = getAppRoot()) {
  return fs.existsSync(path.join(root, ".git"));
}

function engineChildEnv(extra = {}) {
  const dataRoot = getDataRoot();
  return {
    ...process.env,
    PYTHONPATH: getEngineDir(),
    CSB_PROJECT_ROOT: dataRoot,
    CSB_DB_PATH: getDbPath(),
    ...extra,
  };
}

module.exports = {
  getAppRoot,
  getDataRoot,
  getEngineDir,
  getDashboardDir,
  getVenvDir,
  getVenvPython,
  getEnvFilePath,
  getEnvExamplePath,
  getDbPath,
  isGitCheckout,
  engineChildEnv,
};
