"use strict";

/**
 * Git-based self-update helpers for local checkout / desktop:dev test loops.
 * Never force-push, never commit, never touch .env contents.
 */

const { execFile } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");
const { promisify } = require("node:util");

const execFileAsync = promisify(execFile);

const DEFAULT_REPO = "Pmvita/crypto-signal-bot";
const DEFAULT_BRANCH = "main";
const RELEASES_URL = `https://github.com/${DEFAULT_REPO}/releases`;

function isGitCheckout(root) {
  try {
    return fs.existsSync(path.join(root, ".git"));
  } catch {
    return false;
  }
}

async function runGit(root, args, opts = {}) {
  const { stdout, stderr } = await execFileAsync("git", args, {
    cwd: root,
    windowsHide: true,
    maxBuffer: 8 * 1024 * 1024,
    ...opts,
  });
  return {
    stdout: String(stdout || "").trim(),
    stderr: String(stderr || "").trim(),
  };
}

async function getLocalHead(root) {
  const { stdout } = await runGit(root, ["rev-parse", "HEAD"]);
  return stdout;
}

async function getWorkingTreeDirty(root) {
  const { stdout } = await runGit(root, ["status", "--porcelain"]);
  return stdout.length > 0;
}

/**
 * @param {string} root
 * @param {{ onProgress?: (msg: string) => void, branch?: string }} [options]
 */
async function checkForUpdates(root, options = {}) {
  const onProgress = options.onProgress || (() => {});
  const branch = options.branch || DEFAULT_BRANCH;

  if (!isGitCheckout(root)) {
    return {
      mode: "packaged",
      updateAvailable: false,
      canApply: false,
      message:
        "Git self-update is only available in a development/checkout build. Packaged installs should use GitHub Releases.",
      releasesUrl: RELEASES_URL,
      localSha: null,
      remoteSha: null,
    };
  }

  onProgress("Fetching origin…");
  try {
    await runGit(root, ["fetch", "origin", branch]);
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    return {
      mode: "git",
      updateAvailable: false,
      canApply: false,
      message: `git fetch failed: ${message}`,
      releasesUrl: RELEASES_URL,
      localSha: null,
      remoteSha: null,
    };
  }

  const localSha = await getLocalHead(root);
  let remoteSha;
  try {
    const { stdout } = await runGit(root, ["rev-parse", `origin/${branch}`]);
    remoteSha = stdout;
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    return {
      mode: "git",
      updateAvailable: false,
      canApply: false,
      message: `Could not resolve origin/${branch}: ${message}`,
      releasesUrl: RELEASES_URL,
      localSha,
      remoteSha: null,
    };
  }

  const dirty = await getWorkingTreeDirty(root);
  const updateAvailable = localSha !== remoteSha;

  let aheadBehind = "";
  try {
    const { stdout } = await runGit(root, [
      "rev-list",
      "--left-right",
      "--count",
      `HEAD...origin/${branch}`,
    ]);
    const [behindLocal, aheadRemote] = stdout.split(/\s+/).map((n) => Number(n) || 0);
    // left = commits reachable from HEAD not in origin (local-only)
    // right = commits on origin not in HEAD (to pull)
    aheadBehind = `${aheadRemote} incoming / ${behindLocal} local-only`;
  } catch {
    aheadBehind = "";
  }

  if (!updateAvailable) {
    return {
      mode: "git",
      updateAvailable: false,
      canApply: false,
      dirty,
      message: `Already up to date with origin/${branch} (${localSha.slice(0, 7)}).`,
      releasesUrl: RELEASES_URL,
      localSha,
      remoteSha,
      aheadBehind,
    };
  }

  if (dirty) {
    return {
      mode: "git",
      updateAvailable: true,
      canApply: false,
      dirty: true,
      message:
        "Updates are available, but the working tree has local changes. Commit, stash, or discard them before updating — refusing to overwrite your work.",
      releasesUrl: RELEASES_URL,
      localSha,
      remoteSha,
      aheadBehind,
    };
  }

  return {
    mode: "git",
    updateAvailable: true,
    canApply: true,
    dirty: false,
    message: `Update available: ${localSha.slice(0, 7)} → ${remoteSha.slice(0, 7)}${aheadBehind ? ` (${aheadBehind})` : ""}.`,
    releasesUrl: RELEASES_URL,
    localSha,
    remoteSha,
    aheadBehind,
  };
}

/**
 * Apply updates with git pull --ff-only. Refuses dirty trees.
 * @param {string} root
 * @param {{ onProgress?: (msg: string) => void, branch?: string, checkResult?: object }} [options]
 */
async function applyUpdates(root, options = {}) {
  const onProgress = options.onProgress || (() => {});
  const branch = options.branch || DEFAULT_BRANCH;

  const check = options.checkResult || (await checkForUpdates(root, { onProgress, branch }));
  if (check.mode === "packaged") {
    return {
      ok: false,
      ...check,
      restartRequired: false,
      engineRestartSuggested: false,
    };
  }
  if (!check.updateAvailable) {
    return {
      ok: true,
      ...check,
      restartRequired: false,
      engineRestartSuggested: false,
    };
  }
  if (!check.canApply) {
    return {
      ok: false,
      ...check,
      restartRequired: false,
      engineRestartSuggested: false,
    };
  }

  onProgress(`Pulling origin/${branch} (ff-only)…`);
  try {
    await runGit(root, ["pull", "--ff-only", "origin", branch]);
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    return {
      ok: false,
      mode: "git",
      updateAvailable: true,
      canApply: false,
      message: `git pull --ff-only failed: ${message}`,
      releasesUrl: RELEASES_URL,
      localSha: check.localSha,
      remoteSha: check.remoteSha,
      restartRequired: false,
      engineRestartSuggested: false,
    };
  }

  const newHead = await getLocalHead(root);
  onProgress(`Updated to ${newHead.slice(0, 7)}.`);

  // Heuristic: main/preload/package changes need Electron restart; otherwise engine restart often enough.
  let restartRequired = true;
  let engineRestartSuggested = true;
  try {
    const { stdout } = await runGit(root, [
      "diff",
      "--name-only",
      `${check.localSha}..${newHead}`,
    ]);
    const files = stdout.split(/\r?\n/).filter(Boolean);
    const touchesElectron = files.some(
      (f) =>
        f.startsWith("desktop/") ||
        f === "package.json" ||
        f === "package-lock.json",
    );
    const touchesEngine = files.some(
      (f) => f.startsWith("engine/") || f === "requirements.txt" || f.startsWith("engine/requirements"),
    );
    const touchesDashboard = files.some((f) => f.startsWith("dashboard/"));
    restartRequired = touchesElectron || touchesDashboard;
    engineRestartSuggested = touchesEngine || touchesDashboard || touchesElectron;
    if (!files.length) {
      restartRequired = false;
      engineRestartSuggested = false;
    }
  } catch {
    restartRequired = true;
    engineRestartSuggested = true;
  }

  return {
    ok: true,
    mode: "git",
    updateAvailable: false,
    canApply: false,
    message: `Successfully updated to ${newHead.slice(0, 7)}.${
      restartRequired
        ? " Restart the desktop app to load shell/desk changes."
        : engineRestartSuggested
          ? " Restart the engine to load engine changes."
          : " No restart required."
    }`,
    releasesUrl: RELEASES_URL,
    localSha: newHead,
    remoteSha: newHead,
    previousSha: check.localSha,
    restartRequired,
    engineRestartSuggested,
  };
}

/**
 * Informational check via GitHub API when not in a git tree (never applies).
 */
async function checkRemoteTipViaApi(options = {}) {
  const repo = options.repo || DEFAULT_REPO;
  const branch = options.branch || DEFAULT_BRANCH;
  const url = `https://api.github.com/repos/${repo}/commits/${branch}`;
  const res = await fetch(url, {
    headers: {
      Accept: "application/vnd.github+json",
      "User-Agent": "crypto-signal-bot-desktop",
    },
  });
  if (!res.ok) {
    throw new Error(`GitHub API ${res.status}: ${await res.text()}`);
  }
  const body = await res.json();
  return {
    sha: body.sha,
    message: body.commit?.message?.split("\n")[0] || "",
    htmlUrl: body.html_url,
    releasesUrl: RELEASES_URL,
  };
}

module.exports = {
  DEFAULT_REPO,
  DEFAULT_BRANCH,
  RELEASES_URL,
  isGitCheckout,
  runGit,
  getLocalHead,
  getWorkingTreeDirty,
  checkForUpdates,
  applyUpdates,
  checkRemoteTipViaApi,
};
