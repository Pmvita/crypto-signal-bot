"use client";

import { useEffect, useState } from "react";

export type EngineShellStatus = {
  running: boolean;
  pid: number | null;
  port: number;
  host: string;
  healthy?: boolean;
  reused?: boolean;
  error?: string;
  lastExit?: { code: number | null; signal: NodeJS.Signals | null; at: number } | null;
};

export type SetupState = {
  ready: boolean;
  error: string | null;
  dataRoot: string | null;
  appRoot: string | null;
  packaged: boolean;
  gitCheckout: boolean;
  envPath: string | null;
  venvPython: string | null;
  engine: EngineShellStatus;
  backfillRunning: boolean;
};

export type UpdateCheckResult = {
  mode: "git" | "packaged";
  updateAvailable: boolean;
  canApply: boolean;
  dirty?: boolean;
  message: string;
  releasesUrl: string;
  localSha: string | null;
  remoteSha: string | null;
  aheadBehind?: string;
  remoteTip?: { sha: string; message: string; htmlUrl: string; releasesUrl: string } | null;
};

export type UpdateApplyResult = UpdateCheckResult & {
  ok: boolean;
  restartRequired?: boolean;
  engineRestartSuggested?: boolean;
  engineRestarted?: boolean;
  engineRestartError?: string;
  previousSha?: string;
};

export type MaskedSecret = {
  present: boolean;
  masked: string;
  last4: string;
};

export type LlmSettingsPublic = {
  path: string;
  provider: string;
  openaiBaseUrl: string;
  openaiModel: string;
  anthropicModel: string;
  openaiApiKey: MaskedSecret;
  anthropicApiKey: MaskedSecret;
};

export type LlmSettingsSaveInput = {
  provider?: string;
  openaiBaseUrl?: string;
  openaiModel?: string;
  anthropicModel?: string;
  openaiApiKey?: string;
  anthropicApiKey?: string;
  clearOpenaiApiKey?: boolean;
  clearAnthropicApiKey?: boolean;
};

export type LlmSettingsSaveResult = {
  settings: LlmSettingsPublic;
  engineRestarted: boolean;
  engineStatus: EngineShellStatus | null;
  engineRestartError: string | null;
};

export type CsbDesktopApi = {
  isElectron: true;
  engine: {
    start: () => Promise<EngineShellStatus>;
    stop: () => Promise<EngineShellStatus>;
    status: () => Promise<EngineShellStatus>;
    onEvent: (cb: (payload: unknown) => void) => () => void;
  };
  jobs: {
    backfill: (opts?: { days?: number }) => Promise<{ ok: boolean; code: number }>;
    onLog: (cb: (payload: { type: string; text?: string; message?: string; ok?: boolean }) => void) => () => void;
  };
  setup: {
    getState: () => Promise<SetupState>;
  };
  settings: {
    getLlm: () => Promise<LlmSettingsPublic>;
    saveLlm: (input: LlmSettingsSaveInput) => Promise<LlmSettingsSaveResult>;
  };
  shell: {
    openDataFolder: () => Promise<string>;
    openEnvLocation: () => Promise<{ ok: boolean; path: string; message?: string }>;
    openExternal: (url: string) => Promise<{ ok: boolean }>;
    restartApp: () => Promise<void>;
  };
  updates: {
    check: () => Promise<UpdateCheckResult>;
    apply: () => Promise<UpdateApplyResult>;
    onProgress: (cb: (payload: { message: string; ts: number }) => void) => () => void;
  };
};

declare global {
  interface Window {
    csb?: CsbDesktopApi;
  }
}

export function getCsbShell(): CsbDesktopApi | null {
  if (typeof window === "undefined") return null;
  return window.csb ?? null;
}

export function isElectronShell(): boolean {
  return Boolean(getCsbShell()?.isElectron);
}

/** Client-only: false on SSR / first paint, then true inside Electron after mount. */
export function useElectronShell(): boolean {
  const [electron, setElectron] = useState(false);
  useEffect(() => {
    setElectron(isElectronShell());
  }, []);
  return electron;
}
