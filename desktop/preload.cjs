"use strict";

const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("csb", {
  isElectron: true,
  engine: {
    start: () => ipcRenderer.invoke("csb:engine:start"),
    stop: () => ipcRenderer.invoke("csb:engine:stop"),
    status: () => ipcRenderer.invoke("csb:engine:status"),
    onEvent: (cb) => {
      const listener = (_event, payload) => cb(payload);
      ipcRenderer.on("csb:engine:event", listener);
      return () => ipcRenderer.removeListener("csb:engine:event", listener);
    },
  },
  jobs: {
    backfill: (opts) => ipcRenderer.invoke("csb:jobs:backfill", opts || {}),
    onLog: (cb) => {
      const listener = (_event, payload) => cb(payload);
      ipcRenderer.on("csb:jobs:log", listener);
      return () => ipcRenderer.removeListener("csb:jobs:log", listener);
    },
  },
  setup: {
    getState: () => ipcRenderer.invoke("csb:setup:getState"),
  },
  settings: {
    getLlm: () => ipcRenderer.invoke("csb:settings:getLlm"),
    saveLlm: (input) => ipcRenderer.invoke("csb:settings:saveLlm", input || {}),
  },
  shell: {
    openDataFolder: () => ipcRenderer.invoke("csb:shell:openDataFolder"),
    openEnvLocation: () => ipcRenderer.invoke("csb:shell:openEnvLocation"),
    openExternal: (url) => ipcRenderer.invoke("csb:shell:openExternal", url),
    restartApp: () => ipcRenderer.invoke("csb:shell:restartApp"),
  },
  updates: {
    check: () => ipcRenderer.invoke("csb:updates:check"),
    apply: () => ipcRenderer.invoke("csb:updates:apply"),
    onProgress: (cb) => {
      const listener = (_event, payload) => cb(payload);
      ipcRenderer.on("csb:updates:progress", listener);
      return () => ipcRenderer.removeListener("csb:updates:progress", listener);
    },
  },
});
