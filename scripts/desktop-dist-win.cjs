"use strict";

/**
 * Windows electron-builder entry: unsigned OK (no code-signing cert on this machine).
 */

const { spawnSync } = require("node:child_process");
const path = require("node:path");

const ROOT = path.resolve(__dirname, "..");

const pre = spawnSync(process.execPath, [path.join(__dirname, "desktop-predist.cjs")], {
  cwd: ROOT,
  stdio: "inherit",
  env: process.env,
});
if (pre.status !== 0) {
  process.exit(pre.status ?? 1);
}

const env = {
  ...process.env,
  CSC_IDENTITY_AUTO_DISCOVERY: "false",
};

const build = spawnSync(
  process.platform === "win32" ? "npx.cmd" : "npx",
  ["electron-builder", "--win", "--publish", "never"],
  {
    cwd: ROOT,
    stdio: "inherit",
    shell: process.platform === "win32",
    env,
  },
);
process.exit(build.status ?? 1);
