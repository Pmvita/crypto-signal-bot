"use client";

import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  getCsbShell,
  type LlmSettingsPublic,
} from "@/lib/csb-shell";

export function ShellLlmForm({ onSaved }: { onSaved?: () => void }) {
  const shell = getCsbShell();
  const [loaded, setLoaded] = useState<LlmSettingsPublic | null>(null);
  const [provider, setProvider] = useState("openai");
  const [openaiBaseUrl, setOpenaiBaseUrl] = useState("https://api.openai.com/v1");
  const [openaiModel, setOpenaiModel] = useState("");
  const [anthropicModel, setAnthropicModel] = useState("");
  const [openaiApiKey, setOpenaiApiKey] = useState("");
  const [anthropicApiKey, setAnthropicApiKey] = useState("");
  const [replaceOpenai, setReplaceOpenai] = useState(false);
  const [replaceAnthropic, setReplaceAnthropic] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!shell) return;
    void shell.settings
      .getLlm()
      .then((settings) => {
        setLoaded(settings);
        setProvider(settings.provider || "openai");
        setOpenaiBaseUrl(settings.openaiBaseUrl || "https://api.openai.com/v1");
        setOpenaiModel(settings.openaiModel || "");
        setAnthropicModel(settings.anthropicModel || "");
        setOpenaiApiKey("");
        setAnthropicApiKey("");
        setReplaceOpenai(false);
        setReplaceAnthropic(false);
      })
      .catch((err) => setError(err instanceof Error ? err.message : String(err)));
  }, [shell]);

  if (!shell) return null;
  if (!loaded && !error) {
    return <p className="font-mono text-xs text-muted-foreground">Loading AppData LLM settings…</p>;
  }

  const save = async (opts?: { clearOpenai?: boolean; clearAnthropic?: boolean }) => {
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const result = await shell.settings.saveLlm({
        provider,
        openaiBaseUrl,
        openaiModel,
        anthropicModel,
        openaiApiKey: replaceOpenai ? openaiApiKey : undefined,
        anthropicApiKey: replaceAnthropic ? anthropicApiKey : undefined,
        clearOpenaiApiKey: opts?.clearOpenai,
        clearAnthropicApiKey: opts?.clearAnthropic,
      });
      setLoaded(result.settings);
      setOpenaiApiKey("");
      setAnthropicApiKey("");
      setReplaceOpenai(false);
      setReplaceAnthropic(false);
      const bits = [
        `Saved to ${result.settings.path}`,
        result.engineRestarted ? "engine restarted" : "engine restart pending",
      ];
      if (result.engineRestartError) bits.push(`engine error: ${result.engineRestartError}`);
      setMessage(bits.join(" · "));
      onSaved?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-4">
      <p className="font-mono text-xs text-muted-foreground">
        Desktop path of truth:{" "}
        <code className="text-[var(--amber)]">%APPDATA%\Crypto Signal Bot\.env</code>. Keys are
        masked here, never committed to git. Saving restarts the engine so news scoring picks up the
        new values. CLI without Electron still uses the repo <code>.env</code>.
      </p>

      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label htmlFor="llm-provider" className="font-mono text-[11px] uppercase tracking-[0.14em]">
            Provider
          </Label>
          <select
            id="llm-provider"
            className="h-8 w-full rounded-lg border border-input bg-transparent px-2.5 font-mono text-sm"
            value={provider}
            onChange={(e) => setProvider(e.target.value)}
          >
            <option value="openai">openai (incl. OpenRouter)</option>
            <option value="anthropic">anthropic</option>
          </select>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="openai-base" className="font-mono text-[11px] uppercase tracking-[0.14em]">
            OPENAI_BASE_URL
          </Label>
          <Input
            id="openai-base"
            className="font-mono text-xs"
            value={openaiBaseUrl}
            onChange={(e) => setOpenaiBaseUrl(e.target.value)}
            placeholder="https://openrouter.ai/api/v1"
          />
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label htmlFor="openai-model" className="font-mono text-[11px] uppercase tracking-[0.14em]">
            OPENAI_MODEL
          </Label>
          <Input
            id="openai-model"
            className="font-mono text-xs"
            value={openaiModel}
            onChange={(e) => setOpenaiModel(e.target.value)}
            placeholder="openai/gpt-4o-mini"
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="anthropic-model" className="font-mono text-[11px] uppercase tracking-[0.14em]">
            ANTHROPIC_MODEL
          </Label>
          <Input
            id="anthropic-model"
            className="font-mono text-xs"
            value={anthropicModel}
            onChange={(e) => setAnthropicModel(e.target.value)}
            placeholder="claude-…"
          />
        </div>
      </div>

      <div className="space-y-2 border border-border/60 p-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <Label className="font-mono text-[11px] uppercase tracking-[0.14em]">OPENAI_API_KEY</Label>
          <span className="font-mono text-[10px] text-muted-foreground">
            {loaded?.openaiApiKey.present
              ? `stored · ${loaded.openaiApiKey.masked}`
              : "not set"}
          </span>
        </div>
        {replaceOpenai ? (
          <Input
            type="password"
            autoComplete="off"
            className="font-mono text-xs"
            value={openaiApiKey}
            onChange={(e) => setOpenaiApiKey(e.target.value)}
            placeholder="Paste new key (OpenAI or OpenRouter)"
          />
        ) : (
          <div className="flex flex-wrap gap-2">
            <Button type="button" size="sm" variant="outline" onClick={() => setReplaceOpenai(true)}>
              {loaded?.openaiApiKey.present ? "Replace key" : "Set key"}
            </Button>
            {loaded?.openaiApiKey.present ? (
              <Button
                type="button"
                size="sm"
                variant="outline"
                disabled={busy}
                onClick={() => void save({ clearOpenai: true })}
              >
                Clear key
              </Button>
            ) : null}
          </div>
        )}
      </div>

      <div className="space-y-2 border border-border/60 p-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <Label className="font-mono text-[11px] uppercase tracking-[0.14em]">ANTHROPIC_API_KEY</Label>
          <span className="font-mono text-[10px] text-muted-foreground">
            {loaded?.anthropicApiKey.present
              ? `stored · ${loaded.anthropicApiKey.masked}`
              : "not set"}
          </span>
        </div>
        {replaceAnthropic ? (
          <Input
            type="password"
            autoComplete="off"
            className="font-mono text-xs"
            value={anthropicApiKey}
            onChange={(e) => setAnthropicApiKey(e.target.value)}
            placeholder="Paste new Anthropic key"
          />
        ) : (
          <div className="flex flex-wrap gap-2">
            <Button type="button" size="sm" variant="outline" onClick={() => setReplaceAnthropic(true)}>
              {loaded?.anthropicApiKey.present ? "Replace key" : "Set key"}
            </Button>
            {loaded?.anthropicApiKey.present ? (
              <Button
                type="button"
                size="sm"
                variant="outline"
                disabled={busy}
                onClick={() => void save({ clearAnthropic: true })}
              >
                Clear key
              </Button>
            ) : null}
          </div>
        )}
      </div>

      <div className="flex flex-wrap gap-2">
        <Button type="button" disabled={busy} onClick={() => void save()}>
          {busy ? "Saving…" : "Save LLM settings"}
        </Button>
      </div>
      {message ? <p className="font-mono text-xs text-[var(--gain)]">{message}</p> : null}
      {error ? <p className="font-mono text-xs text-[var(--loss)]">{error}</p> : null}
    </div>
  );
}
