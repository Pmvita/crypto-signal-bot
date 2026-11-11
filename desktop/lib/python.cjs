"use strict";

const { execFile, spawn } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");
const { promisify } = require("node:util");

const paths = require("./paths.cjs");

const execFileAsync = promisify(execFile);

const KNOWN_WIN_PYTHON = [
  process.env.CSB_PYTHON,
  "C:\\Users\\user\\AppData\\Local\\Programs\\Python\\Python312\\python.exe",
  "C:\\Users\\user\\AppData\\Local\\Programs\\Python\\Python313\\python.exe",
].filter(Boolean);

async function pythonVersion(pythonPath) {
  try {
    const { stdout } = await execFileAsync(pythonPath, ["-c", "import sys; print(f'{sys.version_info[0]}.{sys.version_info[1]}')"], {
      windowsHide: true,
    });
    return stdout.trim();
  } catch {
    return null;
  }
}

function versionAtLeast(ver, major, minor) {
  if (!ver) return false;
  const [a, b] = ver.split(".").map((n) => Number(n) || 0);
  return a > major || (a === major && b >= minor);
}

async function findSystemPython() {
  const candidates = [...KNOWN_WIN_PYTHON];
  if (process.platform === "win32") {
    candidates.push("py");
  }
  candidates.push("python3", "python");

  for (const candidate of candidates) {
    if (candidate.includes("\\") || candidate.includes("/")) {
      if (!fs.existsSync(candidate)) continue;
      const ver = await pythonVersion(candidate);
      if (versionAtLeast(ver, 3, 12)) {
        return { path: candidate, version: ver, argsPrefix: [] };
      }
      continue;
    }
    if (candidate === "py") {
      try {
        const { stdout } = await execFileAsync("py", ["-3.12", "-c", "import sys; print(sys.executable)"], {
          windowsHide: true,
        });
        const resolved = stdout.trim();
        if (resolved && fs.existsSync(resolved)) {
          const ver = await pythonVersion(resolved);
          if (versionAtLeast(ver, 3, 12)) {
            return { path: resolved, version: ver, argsPrefix: [] };
          }
        }
      } catch {
        // try next
      }
      continue;
    }
    const ver = await pythonVersion(candidate);
    if (versionAtLeast(ver, 3, 12)) {
      return { path: candidate, version: ver, argsPrefix: [] };
    }
  }
  return null;
}

function run(command, args, opts = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, {
      windowsHide: true,
      stdio: ["ignore", "pipe", "pipe"],
      ...opts,
    });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (buf) => {
      stdout += buf.toString();
      if (opts.onOut) opts.onOut(buf.toString());
    });
    child.stderr.on("data", (buf) => {
      stderr += buf.toString();
      if (opts.onOut) opts.onOut(buf.toString());
    });
    child.on("error", reject);
    child.on("close", (code) => {
      if (code === 0) resolve({ stdout, stderr, code });
      else reject(new Error(`${command} exited ${code}: ${stderr || stdout}`));
    });
  });
}

/**
 * Ensure venv + requirements. Dev uses repo .venv; packaged uses AppData .venv.
 */
async function ensurePythonEnv(onProgress = () => {}) {
  const venvPython = paths.getVenvPython();
  const venvDir = paths.getVenvDir();
  const requirements = path.join(paths.getEngineDir(), "requirements.txt");
  const marker = path.join(venvDir, ".csb-requirements-stamp");
  const reqText = fs.existsSync(requirements) ? fs.readFileSync(requirements, "utf8") : "";

  if (fs.existsSync(venvPython)) {
    const ver = await pythonVersion(venvPython);
    if (!versionAtLeast(ver, 3, 12)) {
      throw new Error(`Existing venv Python is ${ver || "unknown"}; need 3.12+ at ${venvPython}`);
    }
    const stamp = fs.existsSync(marker) ? fs.readFileSync(marker, "utf8") : "";
    if (stamp === reqText) {
      onProgress(`Using existing venv (${ver})`);
      return { pythonPath: venvPython, created: false, installed: false };
    }
    onProgress("Updating venv packages…");
    await run(venvPython, ["-m", "pip", "install", "--upgrade", "pip"], { onOut: onProgress });
    await run(venvPython, ["-m", "pip", "install", "-r", requirements], { onOut: onProgress });
    fs.writeFileSync(marker, reqText, "utf8");
    return { pythonPath: venvPython, created: false, installed: true };
  }

  onProgress("Looking for system Python 3.12+…");
  const system = await findSystemPython();
  if (!system) {
    throw new Error(
      "Python 3.12+ not found. Install Python from python.org (full installer, not the Windows Store stub) and retry.",
    );
  }
  onProgress(`Creating venv with ${system.path} (${system.version})…`);
  fs.mkdirSync(path.dirname(venvDir), { recursive: true });
  await run(system.path, ["-m", "venv", venvDir], { onOut: onProgress });
  if (!fs.existsSync(venvPython)) {
    throw new Error(`venv created but python missing at ${venvPython}`);
  }
  onProgress("Installing engine requirements…");
  await run(venvPython, ["-m", "pip", "install", "--upgrade", "pip"], { onOut: onProgress });
  await run(venvPython, ["-m", "pip", "install", "-r", requirements], { onOut: onProgress });
  fs.writeFileSync(marker, reqText, "utf8");
  return { pythonPath: venvPython, created: true, installed: true, systemPython: system.path };
}

/**
 * Seed .env from example. Optionally copy project .env into AppData at runtime only.
 */
function ensureEnvFile(onProgress = () => {}) {
  const dest = paths.getEnvFilePath();
  if (fs.existsSync(dest)) {
    return { path: dest, created: false };
  }
  const dataRoot = paths.getDataRoot();
  const appRoot = paths.getAppRoot();
  fs.mkdirSync(dataRoot, { recursive: true });

  // Packaged / relocated data root: prefer copying an existing project .env on this machine.
  const projectEnv = path.join(appRoot, ".env");
  if (dataRoot !== appRoot && fs.existsSync(projectEnv)) {
    fs.copyFileSync(projectEnv, dest);
    onProgress(`Copied project .env into ${dest} (local machine only)`);
    return { path: dest, created: true, from: "project" };
  }

  const example = paths.getEnvExamplePath();
  if (fs.existsSync(example)) {
    fs.copyFileSync(example, dest);
    onProgress(`Created .env from .env.example at ${dest}`);
    return { path: dest, created: true, from: "example" };
  }

  fs.writeFileSync(dest, "# Crypto Signal Bot\nCSB_API_PORT=8787\n", "utf8");
  onProgress(`Created minimal .env at ${dest}`);
  return { path: dest, created: true, from: "minimal" };
}

function ensureDataDir() {
  const db = paths.getDbPath();
  fs.mkdirSync(path.dirname(db), { recursive: true });
  return db;
}

module.exports = {
  findSystemPython,
  ensurePythonEnv,
  ensureEnvFile,
  ensureDataDir,
  pythonVersion,
};
