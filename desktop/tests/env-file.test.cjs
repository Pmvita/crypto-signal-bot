"use strict";

const { describe, it } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const envFile = require("../lib/env-file.cjs");

describe("env-file helpers", () => {
  it("masks secrets without exposing the full key", () => {
    const masked = envFile.maskSecret("sk-or-v1-abcdefghijklmnop");
    assert.equal(masked.present, true);
    assert.equal(masked.last4, "mnop");
    assert.equal(masked.masked, "••••••••mnop");
    assert.ok(!masked.masked.includes("sk-or"));
  });

  it("persists LLM settings across read/write and keeps existing key when blank", () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "csb-env-"));
    const file = path.join(dir, ".env");
    fs.writeFileSync(file, "CSB_EXCHANGE=coinbaseexchange\nOPENAI_API_KEY=keep-me-secret\n", "utf8");

    const first = envFile.saveLlmSettings(file, {
      provider: "openai",
      openaiBaseUrl: "https://openrouter.ai/api/v1",
      openaiModel: "openai/gpt-4o-mini",
      openaiApiKey: "", // keep
    });
    assert.equal(first.openaiApiKey.present, true);
    assert.equal(first.openaiApiKey.last4, "cret");
    assert.equal(first.openaiBaseUrl, "https://openrouter.ai/api/v1");
    assert.equal(first.openaiModel, "openai/gpt-4o-mini");

    const raw = fs.readFileSync(file, "utf8");
    assert.match(raw, /OPENAI_API_KEY=keep-me-secret/);
    assert.match(raw, /CSB_EXCHANGE=coinbaseexchange/);
    assert.doesNotMatch(raw, /••••/);

    const second = envFile.saveLlmSettings(file, {
      openaiApiKey: "••••••••cret", // masked re-submit ignored
      openaiModel: "openai/gpt-4o",
    });
    assert.equal(second.openaiModel, "openai/gpt-4o");
    assert.match(fs.readFileSync(file, "utf8"), /OPENAI_API_KEY=keep-me-secret/);

    const third = envFile.saveLlmSettings(file, {
      openaiApiKey: "new-secret-key-9999",
    });
    assert.equal(third.openaiApiKey.last4, "9999");
    assert.match(fs.readFileSync(file, "utf8"), /OPENAI_API_KEY=new-secret-key-9999/);

    envFile.saveLlmSettings(file, { clearOpenaiApiKey: true });
    assert.equal(envFile.getLlmSettingsPublic(file).openaiApiKey.present, false);
  });
});
