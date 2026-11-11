"use strict";

/**
 * Read/write local .env without logging secret values.
 * Used by the desktop shell for AppData persistence.
 */

const fs = require("node:fs");
const path = require("node:path");

const LLM_KEYS = [
  "CSB_LLM_PROVIDER",
  "OPENAI_API_KEY",
  "OPENAI_BASE_URL",
  "OPENAI_MODEL",
  "ANTHROPIC_API_KEY",
  "ANTHROPIC_MODEL",
];

const SECRET_KEYS = new Set(["OPENAI_API_KEY", "ANTHROPIC_API_KEY"]);

function parseEnvFile(content) {
  const map = {};
  const lines = String(content || "").split(/\r?\n/);
  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;
    const eq = line.indexOf("=");
    if (eq < 0) continue;
    const key = line.slice(0, eq).trim();
    let value = line.slice(eq + 1);
    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1);
    }
    map[key] = value;
  }
  return map;
}

function readEnvMap(filePath) {
  if (!fs.existsSync(filePath)) return {};
  return parseEnvFile(fs.readFileSync(filePath, "utf8"));
}

function maskSecret(value) {
  if (!value) return { present: false, masked: "", last4: "" };
  const last4 = value.length <= 4 ? value : value.slice(-4);
  return {
    present: true,
    masked: `••••••••${last4}`,
    last4,
  };
}

/**
 * Upsert keys into an .env file, preserving unrelated lines/comments.
 * @param {string} filePath
 * @param {Record<string, string>} updates  empty string deletes / clears the value
 */
function upsertEnvKeys(filePath, updates) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  const existing = fs.existsSync(filePath) ? fs.readFileSync(filePath, "utf8") : "";
  const lines = existing.length ? existing.split(/\r?\n/) : [];
  const seen = new Set();
  const nextLines = lines.map((line) => {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) return line;
    const eq = line.indexOf("=");
    if (eq < 0) return line;
    const key = line.slice(0, eq).trim();
    if (!(key in updates)) return line;
    seen.add(key);
    return `${key}=${updates[key]}`;
  });

  for (const [key, value] of Object.entries(updates)) {
    if (seen.has(key)) continue;
    nextLines.push(`${key}=${value}`);
  }

  // Ensure trailing newline
  let out = nextLines.join("\n");
  if (!out.endsWith("\n")) out += "\n";
  fs.writeFileSync(filePath, out, "utf8");
  return readEnvMap(filePath);
}

function getLlmSettingsPublic(filePath) {
  const map = readEnvMap(filePath);
  const provider = (map.CSB_LLM_PROVIDER || "openai").toLowerCase();
  const openaiKey = maskSecret(map.OPENAI_API_KEY || "");
  const anthropicKey = maskSecret(map.ANTHROPIC_API_KEY || "");
  return {
    path: filePath,
    provider,
    openaiBaseUrl: map.OPENAI_BASE_URL || "https://api.openai.com/v1",
    openaiModel: map.OPENAI_MODEL || "",
    anthropicModel: map.ANTHROPIC_MODEL || "",
    openaiApiKey: openaiKey,
    anthropicApiKey: anthropicKey,
  };
}

/**
 * Save LLM fields. Secret fields:
 * - undefined / null / "" with keepExisting → leave unchanged
 * - explicit clearKey: true → wipe
 * - new non-empty string → replace
 */
function saveLlmSettings(filePath, input = {}) {
  const current = readEnvMap(filePath);
  const updates = {};

  if (typeof input.provider === "string" && input.provider.trim()) {
    updates.CSB_LLM_PROVIDER = input.provider.trim().toLowerCase();
  }
  if (typeof input.openaiBaseUrl === "string") {
    updates.OPENAI_BASE_URL = input.openaiBaseUrl.trim();
  }
  if (typeof input.openaiModel === "string") {
    updates.OPENAI_MODEL = input.openaiModel.trim();
  }
  if (typeof input.anthropicModel === "string") {
    updates.ANTHROPIC_MODEL = input.anthropicModel.trim();
  }

  const applySecret = (key, value, clear) => {
    if (clear) {
      updates[key] = "";
      return;
    }
    if (typeof value !== "string") return;
    const trimmed = value.trim();
    if (!trimmed) return; // keep existing
    // Ignore accidental re-submit of masked display value
    if (trimmed.startsWith("••••")) return;
    updates[key] = trimmed;
  };

  applySecret("OPENAI_API_KEY", input.openaiApiKey, Boolean(input.clearOpenaiApiKey));
  applySecret("ANTHROPIC_API_KEY", input.anthropicApiKey, Boolean(input.clearAnthropicApiKey));

  upsertEnvKeys(filePath, updates);
  return getLlmSettingsPublic(filePath);
}

module.exports = {
  LLM_KEYS,
  SECRET_KEYS,
  parseEnvFile,
  readEnvMap,
  maskSecret,
  upsertEnvKeys,
  getLlmSettingsPublic,
  saveLlmSettings,
};
