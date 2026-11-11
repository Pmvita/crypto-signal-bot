"use strict";

/**
 * Build a relocatable Next.js standalone desk into packaging/dashboard
 * without clobbering a live `next dev` session's `.next` folder.
 */

const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");

const ROOT = path.resolve(__dirname, "..");
const DASHBOARD = path.join(ROOT, "dashboard");
const DIST_DIR_NAME = ".next-pack";
const DIST_DIR = path.join(DASHBOARD, DIST_DIR_NAME);
const STANDALONE = path.join(DIST_DIR, "standalone");
const STAGING = path.join(ROOT, "packaging", "dashboard");

function fail(message, code = 1) {
  console.error(`[desktop-predist] ${message}`);
  process.exit(code);
}

function run(command, args, opts) {
  const result = spawnSync(command, args, {
    stdio: "inherit",
    shell: process.platform === "win32",
    ...opts,
  });
  if (result.status !== 0) {
    fail(`${command} ${args.join(" ")} exited ${result.status ?? "null"}`);
  }
}

function resolveStandaloneRoot() {
  const direct = path.join(STANDALONE, "server.js");
  if (fs.existsSync(direct)) return STANDALONE;
  const nested = path.join(STANDALONE, "dashboard", "server.js");
  if (fs.existsSync(nested)) return path.join(STANDALONE, "dashboard");
  fail(`standalone server.js not found under ${STANDALONE}`);
}

if (!fs.existsSync(path.join(DASHBOARD, "package.json"))) {
  fail(`dashboard package missing at ${DASHBOARD}`);
}

console.log(`[desktop-predist] Building desk with CSB_DIST_DIR=${DIST_DIR_NAME}…`);
run(process.platform === "win32" ? "npm.cmd" : "npm", ["run", "build"], {
  cwd: DASHBOARD,
  env: { ...process.env, CSB_DIST_DIR: DIST_DIR_NAME },
});

const standaloneRoot = resolveStandaloneRoot();
console.log(`[desktop-predist] Staging from ${standaloneRoot} → ${STAGING}`);

fs.rmSync(STAGING, { recursive: true, force: true });
fs.mkdirSync(path.dirname(STAGING), { recursive: true });
fs.cpSync(standaloneRoot, STAGING, { recursive: true, verbatimSymlinks: false });

// server.js serializes distDir from CSB_DIST_DIR ("./.next-pack"), so static
 // assets must land under that folder — not the default ".next".
const staticSrc = path.join(DIST_DIR, "static");
const staticDest = path.join(STAGING, DIST_DIR_NAME, "static");
fs.mkdirSync(path.join(STAGING, DIST_DIR_NAME), { recursive: true });
if (!fs.existsSync(staticSrc)) {
  fail(`missing ${staticSrc}`);
}
fs.cpSync(staticSrc, staticDest, { recursive: true, verbatimSymlinks: false });

const publicSrc = path.join(DASHBOARD, "public");
if (fs.existsSync(publicSrc)) {
  fs.cpSync(publicSrc, path.join(STAGING, "public"), { recursive: true, verbatimSymlinks: false });
}

if (!fs.existsSync(path.join(STAGING, "server.js"))) {
  fail(`staged server.js missing at ${STAGING}`);
}
if (!fs.existsSync(path.join(STAGING, DIST_DIR_NAME, "server"))) {
  fail(`staged ${DIST_DIR_NAME}/server missing — standalone incomplete`);
}
if (!fs.existsSync(staticDest)) {
  fail(`staged static assets missing at ${staticDest}`);
}

console.log("[desktop-predist] Desk packaging stage ready.");
