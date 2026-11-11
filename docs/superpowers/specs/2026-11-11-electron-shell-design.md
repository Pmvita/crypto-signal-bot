# Crypto Signal Bot — Electron Desktop Shell Design

Date: 2026-11-11  
Status: **approved — implementing**  
Related: [phase 1 design](./2026-11-10-crypto-signal-bot-design.md), reference product `solana-sniper-bot` (architectural ideas only; no proprietary code copy)

## 1. Goal / non-goals

### Goal

Ship a **Windows-first Electron desktop app** so the user runs paper trading without juggling terminals and CLI commands. One install (or one `npm run desktop:dev` for developers) starts the desk, starts/stops the Python engine, and exposes first-class actions that today require CLI (`backfill`, engine start).

The shell wraps the existing phase-1 product:

- FastAPI paper engine on `127.0.0.1:8787` (trading loop, risk, kill switch, backtest API)
- Existing Next.js desk UI (desk / signals / trades / news / backtest / settings)
- Local `.env` for secrets; SQLite under `data/` (or AppData when packaged)

### Non-goals (this shell pass)

- **No live trading.** No exchange order-placement path, no live-broker UI, no “go live” toggle that implies real money.
- No macOS/Linux installers in the first packaging slice (Windows NSIS ± portable first; other platforms later if wanted).
- No rewrite of the trading strategy, risk model, or dashboard visual language.
- No remote / non-loopback binding of the engine or desk.
- No committing secrets, `.env`, keys, or user SQLite into git or release artifacts.
- No wholesale copy of `solana-sniper-bot` proprietary desktop/renderer code — reuse patterns (main owns child process, preload IPC, graceful stop, electron-builder Releases), not source.

## 2. Architecture

### Current shape (unchanged contract)

```
exchange/RSS ──► Python engine (csb serve) ──► SQLite
                      │ FastAPI :8787
                      ▼
              Next desk :3000 (polls API)
```

Electron adds a **main process** that owns lifecycle; the desk remains the UI surface.

### Options considered

| Option | How UI loads | Child processes | Packaging | Notes |
|---|---|---|---|---|
| **A. Dual server** | BrowserWindow → `http://127.0.0.1:3000` with full `next start` / `next dev` | Python + Node (Next) | Ship Node runtime or Next standalone + Python | Least UI change; heaviest runtime (two servers + Electron) |
| **B. Static desk host (recommended)** | Build Next as static export; Electron main serves files on `127.0.0.1:3000` via a tiny loopback static server; Window loads that URL | Python only (+ Electron) | Ship static `out/` + engine + Python strategy | Keeps existing `ENGINE_URL` / CORS (`localhost:3000`); no Next server in production |
| **C. Engine-hosted UI** | Static export mounted by FastAPI; Window → `http://127.0.0.1:8787` | Python only | Couple dashboard build into engine packaging | Simplest Electron; couples UI deploy to API process; CORS/origin changes |

### Decision: **Option B preferred; Option A fallback is approved**

Ship toward Option B (static export + loopback host). If Next 16 flags (`cacheComponents` / turbopack CSS) break static export, **Option A** (spawn `next dev` in desktop:dev, `next start` / standalone when packaged) is explicitly OK for v1. Implementation may land on A first if B blocks the pass.

**Dev mode:** Main may spawn `next dev` (or reuse an already-running desk on `:3000`) and still spawn `csb serve`.

**IPC surface (preload, contextIsolation, no nodeIntegration):** e.g. `csb.engine.start|stop|status`, `csb.jobs.backfill`, `csb.setup.getState`, `csb.updates.check|apply` — renderer never sees API keys or raw `.env` contents.

```
┌──────────────────── Electron main ────────────────────┐
│  desk :3000 (next or static) │ spawn/stop Python engine │
│  IPC ← preload ← renderer    │ graceful shutdown hooks  │
│  Check for updates (git)     │ first-run venv setup     │
└─────────────┬─────────────────────────┬───────────────┘
              │ loadURL                 │ child_process
              ▼                         ▼
     Desk (Next / static)        python -m csb serve
                                 (+ backfill subprocess)
```

## 3. Locked product decisions

| # | Topic | Decision |
|---|---|---|
| 1 | Python runtime | **System Python 3.12+** + first-run venv (not bundled embeddable Python in this pass) |
| 2 | Packaged data / config / DB / `.env` | **`%APPDATA%\Crypto Signal Bot\`** (Electron `userData`) |
| 3 | Static export failure | **Option A fallback OK** |
| 4 | Product name / appId | **`Crypto Signal Bot`** / **`com.pmvita.crypto-signal-bot`** |

### Path layout

| Mode | Code root | `.env` / SQLite / venv |
|---|---|---|
| **Desktop** (`desktop:dev` or packaged Electron) | Repo / install resources | **Always** `%APPDATA%\Crypto Signal Bot\`: `.env`, `data\`, `.venv` |
| **CLI** (no Electron) | Repo root | Repo: `.env`, `data/csb.sqlite3`, `.venv` |

Desktop path of truth for secrets and DB is AppData (app name `Crypto Signal Bot`). CLI without Electron keeps reading the project `.env`. Main sets `CSB_PROJECT_ROOT` + absolute `CSB_DB_PATH` for the engine child. `PYTHONPATH` always points at the **code** `engine/` directory.

First-run (desktop): detect system Python → create AppData venv → `pip install -r engine/requirements.txt` → seed AppData `.env` from project `.env` (local machine only) or `.env.example` placeholders — never into git.

### Settings: LLM / OpenRouter API key

Settings UI (Electron only) edits AppData `.env` fields: `CSB_LLM_PROVIDER`, `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL`, plus Anthropic equivalents. Keys are **masked** in the renderer (last 4 chars). Save writes AppData `.env` via main-process IPC (never commits, never logs full secrets) and **restarts the engine child** so news scoring reloads config.

Paren-path builds: use junction `C:\Users\user\Desktop\csb-build`.

### Auto-start / stop

- **On ready:** create window → ensure desk on `:3000` → start engine child (`python -m csb serve` with `PYTHONPATH=engine`).
- **Health:** poll `/api/status` from main; push status to renderer via IPC for Start/Stop chrome.
- **Graceful shutdown:** on `before-quit` / `window-all-closed`: terminate uvicorn child; wait briefly; force-kill if needed. Stop desk child if main spawned it. Do not leave orphan Python on 8787.
- **Crash:** if engine exits unexpectedly, mark status offline in UI; offer Restart (do not silently restart forever).

### Backfill

Shell v1: main spawns `csb backfill` as a **job subprocess** (stdout → IPC log / progress). Optional later: `POST /api/backfill`.

## 4. UI additions the shell enables

Keep existing desk features (wired today):

- Kill switch engage/disengage
- Risk limits save
- Run backtest (`POST /api/backtests`)
- Live-trading-unavailable notice

Add **shell chrome** (StatusBar / Settings; not a second dashboard):

| Control | Behavior |
|---|---|
| **Engine Start / Stop** | IPC → main spawn/kill `csb serve`; status badge online/offline |
| **Run backfill** | IPC → main runs `csb backfill`; progress/log; disable while running |
| **Engine status** | Port, PID/running flag, last heartbeat from `/api/status` |
| **Open data folder / Open .env location** | `shell.openPath` convenience |
| **Check for updates** | See §5 — local git test loop |
| Offline copy | Prefer “Start engine” when running inside Electron |

## 5. Check for updates (Settings) — local test loop

Explicitly for the user’s **local checkout / development test loop**, not a substitute for signed Release installers.

| Context | Behavior |
|---|---|
| **Git working tree** (dev / checkout build) | Prefer `git fetch` + compare local `HEAD` to `origin/main`. If newer commits exist, `git pull --ff-only origin main` when the working tree is **clean**. Surface progress/errors in Settings. After success, say whether restart is required; offer/restart engine (and Electron if main/preload changed). |
| **Dirty working tree** | **Refuse** with a clear message — never destroy local changes, never force-push, never commit secrets. |
| **Packaged install (no `.git`)** | Explain that git self-update is only for development/checkout builds; optionally open GitHub Releases. Do **not** pretend `git pull` works on an NSIS install. |
| **API fallback** | If not a git tree but network is available, may query GitHub `commits/main` (or `gh`) for informational “newer exists” only — apply still requires a git checkout. |

Never overwrite or upload `.env`. Never stage/commit secrets.

## 6. Packaging

| Item | Plan |
|---|---|
| Tooling | `electron` + `electron-builder` at repo root; `desktop/` main + preload |
| Windows first | NSIS installer x64 + optional portable exe |
| Artifacts | GitHub Releases (`Pmvita/crypto-signal-bot`), proprietary LICENSE unchanged |
| UI payload | Dashboard build (static `out/` if Option B, else Next standalone / `.next` for Option A) |
| Engine payload | `engine/csb`, `requirements.txt`, `.env.example` — **not** `.venv`, **not** `.env`, **not** `data/*.sqlite3` |
| Python | System 3.12+ + first-run venv under AppData (packaged) or repo `.venv` (dev) |
| Build path | Junction `C:\Users\user\Desktop\csb-build` when paren path hangs npm |
| Icons | Distinct CSB icon later; placeholder acceptable for first internal dist |
| CI | Unit-test update helpers; full Electron E2E not required in CI |

`asarUnpack` / `extraResources` must leave Python-invoked files on a real filesystem path.

## 7. Security

- Engine remains **127.0.0.1 only** (`API_HOST` fixed); TrustedHostMiddleware stays.
- Desk binds **127.0.0.1:3000** only (not `0.0.0.0`).
- Preload: `contextIsolation: true`, `nodeIntegration: false`, `sandbox: true` where compatible.
- Secrets stay in local `.env` / userData; never in repo, never baked into release zips, never sent to renderer IPC.
- LLM keys continue to be read from the project/userData `.env` only.
- No live-trading credentials or wallet flows in this pass.
- CORS: keep localhost:3000 allowlist. Do not enable `webSecurity: false` as the primary fix.

## 8. Migration path

| Today | After shell (dev) | After shell (end user) |
|---|---|---|
| Terminal A: `python -m csb serve` | `npm run desktop:dev` (main starts engine + desk) | Install from GitHub Release → open app |
| Terminal B: `npm run dev` | Main loads/spawns desk | Desk inside app |
| `python -m csb backfill` | UI **Run backfill** | Same |
| Kill switch / risk | Unchanged via API | Unchanged |
| Manual `git pull` | Settings **Check for updates** (checkout builds) | Releases page (packaged) |

CLI remains supported for power users and CI. The desktop app is the **preferred** daily path.

## 9. Implementation phases

1. Scaffold `desktop/` + root package scripts; Window loads `http://127.0.0.1:3000`.
2. Engine lifecycle — spawn/stop, health, Start/Stop UI, graceful quit.
3. Backfill job — IPC → CLI subprocess + progress UI.
4. Desk host — Option B static if feasible; else Option A `next` child.
5. First-run setup — `.env` seed, Python/venv check.
6. **Check for updates** — git helpers + Settings UI + unit tests.
7. electron-builder Windows scripts; Release artifacts when ready.
8. Optional later — bundled Python; `POST /api/backfill`; macOS.

---

**Approval:** locked by user answers on 2026-11-11 (Python system+venv, AppData paths, Option A fallback OK, product name/appId as above) plus Check-for-updates requirement for the local test loop.
