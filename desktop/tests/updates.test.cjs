"use strict";

const { describe, it, before } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { execFileSync } = require("node:child_process");

const updates = require("../lib/updates.cjs");

function git(cwd, args) {
  return execFileSync("git", args, { cwd, encoding: "utf8", windowsHide: true }).trim();
}

describe("updates helpers", () => {
  it("detects missing .git as packaged mode", async () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "csb-nongit-"));
    const result = await updates.checkForUpdates(dir);
    assert.equal(result.mode, "packaged");
    assert.equal(result.canApply, false);
    assert.match(result.message, /development\/checkout/i);
    assert.ok(result.releasesUrl.includes("releases"));
  });

  it("refuses apply when checkResult says dirty", async () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "csb-dirty-"));
    git(dir, ["init"]);
    git(dir, ["config", "user.email", "test@example.com"]);
    git(dir, ["config", "user.name", "Test"]);
    fs.writeFileSync(path.join(dir, "README.md"), "one\n", "utf8");
    git(dir, ["add", "README.md"]);
    git(dir, ["commit", "-m", "init"]);
    fs.writeFileSync(path.join(dir, "dirty.txt"), "local change\n", "utf8");

    assert.equal(await updates.getWorkingTreeDirty(dir), true);

    const applied = await updates.applyUpdates(dir, {
      checkResult: {
        mode: "git",
        updateAvailable: true,
        canApply: false,
        dirty: true,
        message:
          "Updates are available, but the working tree has local changes. Commit, stash, or discard them before updating — refusing to overwrite your work.",
        localSha: "aaa",
        remoteSha: "bbb",
        releasesUrl: updates.RELEASES_URL,
      },
    });
    assert.equal(applied.ok, false);
    assert.match(applied.message, /local changes/i);
  });
});

describe("updates helpers (isolated clone)", () => {
  let work;

  before(() => {
    const bare = fs.mkdtempSync(path.join(os.tmpdir(), "csb-bare2-"));
    git(bare, ["init", "--bare", "-b", "main"]);

    const seed = fs.mkdtempSync(path.join(os.tmpdir(), "csb-seed-"));
    git(seed, ["init", "-b", "main"]);
    git(seed, ["config", "user.email", "test@example.com"]);
    git(seed, ["config", "user.name", "Test"]);
    fs.writeFileSync(path.join(seed, "a.txt"), "1\n", "utf8");
    git(seed, ["add", "a.txt"]);
    git(seed, ["commit", "-m", "one"]);
    git(seed, ["remote", "add", "origin", bare]);
    git(seed, ["push", "-u", "origin", "main"]);

    work = fs.mkdtempSync(path.join(os.tmpdir(), "csb-work-"));
    execFileSync("git", ["clone", "-b", "main", bare, work], {
      encoding: "utf8",
      windowsHide: true,
    });
    git(work, ["config", "user.email", "test@example.com"]);
    git(work, ["config", "user.name", "Test"]);

    fs.mkdirSync(path.join(seed, "desktop"), { recursive: true });
    fs.writeFileSync(path.join(seed, "a.txt"), "2\n", "utf8");
    fs.writeFileSync(path.join(seed, "desktop", "main.cjs"), "// shell\n", "utf8");
    git(seed, ["add", "a.txt", "desktop/main.cjs"]);
    git(seed, ["commit", "-m", "two"]);
    git(seed, ["push", "origin", "main"]);
  });

  it("check reports update available then apply ff-only succeeds", async () => {
    const check = await updates.checkForUpdates(work);
    assert.equal(check.mode, "git");
    assert.equal(check.updateAvailable, true);
    assert.equal(check.canApply, true);
    assert.notEqual(check.localSha, check.remoteSha);

    const applied = await updates.applyUpdates(work, { checkResult: check });
    assert.equal(applied.ok, true);
    assert.equal(applied.localSha, check.remoteSha);
    assert.equal(applied.restartRequired, true);
    assert.match(fs.readFileSync(path.join(work, "a.txt"), "utf8"), /2/);
  });
});
