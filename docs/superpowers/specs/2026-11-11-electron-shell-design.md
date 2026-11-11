# Crypto Signal Bot — Electron Desktop Shell Design

Date: 2026-11-11  
Status: **draft — awaiting user approval** (do not implement until approved)  
Related: [phase 1 design](./2026-11-10-crypto-signal-bot-design.md), reference product `solana-sniper-bot` (architectural ideas only; no proprietary code copy)

## 1. Goal / non-goals

### Goal

Ship a **Windows-first Electron desktop app** so the user runs paper trading without juggling terminals and CLI commands. One install (or one `npm run desktop` for developers) starts the desk, starts/stops the Python engine, and exposes first-class actions that today require CLI (`backfill`, engine start).

The shell wraps the existing phase-1 product:

- FastAPI paper engine on `127.0.0.1:8787` (trading loop, risk, kill switch, backtest API)
- Existing Next.js desk UI (desk / signals / trades / news / backtest / settings)
- Local `.env` for secrets; SQLite under `data/`

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
| **A. Dual server** | BrowserWindow → `http://127.0.0.1:3000` with full `next start` | Python + Node (Next) | Ship Node runtime or Next standalone + Python | Least UI change; heaviest runtime (two servers + Electron) |
| **B. Static desk host (recommended)** | Build Next as static export; Electron main serves files on `127.0.0.1:3000` via a tiny loopback static server; Window loads that URL | Python only (+ Electron) | Ship static `out/` + engine + Python strategy | Keeps existing `ENGINE_URL` / CORS (`localhost:3000`); no Next server in production |
| **C. Engine-hosted UI** | Static export mounted by FastAPI; Window → `http://127.0.0.1:8787` | Python only | Couple dashboard build into engine packaging | Simplest Electron; couples UI deploy to API process; CORS/origin changes |

### Recommendation: **Option B — Electron main + static desk host + Python engine child**

**Why:** The desk is already client-side (SWR → `http://127.0.0.1:8787`). Production does not need a Next server if we static-export the App Router app (or an equivalent client build). Serving that export from Electron main on **127.0.0.1:3000** preserves today’s CORS allowlist and `NEXT_PUBLIC_ENGINE_URL` defaults. Main only has to manage **one** meaningful child (Python), which matches the solana-sniper pattern of “main owns the bot process.” Option A is the fallback if static export proves incompatible with current Next 16 flags (`cacheComponents` / turbopack CSS). Option C is a later optimization if we want a single port.

**Dev mode:** Main may spawn `next dev` (or expect it) and still spawn `csb serve`, so the existing dashboard DX stays available during shell development.

**IPC surface (preload, contextIsolation, no nodeIntegration):** e.g. `csb.engine.start|stop|status`, `csb.jobs.backfill`, `csb.setup.getState` — renderer never sees API keys or raw `.env` contents.

```
┌──────────────────── Electron main ────────────────────┐
│  static host :3000 (prod) │ spawn/stop Python engine   │
│  IPC ← preload ← renderer │ graceful shutdown hooks    │
└─────────────┬─────────────────────────┬───────────────┘
              │ loadURL                 │ child_process
              ▼                         ▼
     Desk (static / next)        python -m csb serve
                                 (+ backfill subprocess)
```

## 3. Process lifecycle

### First launch / setup

1. Resolve **app root** (dev: repo root; packaged: `app.asar.unpacked` or equivalent so Python and data are writable outside asar — same idea as sniper’s `getAppRoot`).
2. Ensure **user data / project data paths**:
   - Prefer packaged installs writing SQLite + `.env` under Electron `userData` (e.g. `%APPDATA%/Crypto Signal Bot/`), with `CSB_DB_PATH` pointing there.
   - Dev continues to use repo-root `.env` and `data/csb.sqlite3` (current `config.PROJECT_ROOT` behavior).
3. If `.env` missing: copy from `.env.example` (names only); surface a short Settings/setup pane (“optional LLM keys”). Never invent keys.
4. **Python runtime (decision — see open questions):**
   - **Path A (recommended default for v1):** require a local Python 3.12+ on PATH (or configured path); create/reuse a venv under `userData` or repo `.venv`; `pip install -r engine/requirements.txt` on first run / version bump.
   - **Path B (better end-user UX, larger artifact):** ship Windows embeddable Python + preinstalled deps inside the installer (`extraResources`), no system Python required.
5. Auto-start engine after setup succeeds (health-check `GET /api/status`).
6. Paren-path builds: keep using junction `C:\Users\user\Desktop\csb-build` for npm/electron-builder when the real path contains `)`.

### `.env` location

| Mode | Location | Rules |
|---|---|---|
| Dev | `<repo>/.env` | gitignored; keys only from project `.env` (existing `project_env` behavior) |
| Packaged | `<userData>/.env` | created from example; never shipped in the installer payload with secrets |

Main sets cwd / env so `csb` resolves the correct root (may need a small, approved config tweak later: `CSB_PROJECT_ROOT` or pass env only for packaged mode — call out in implementation; do not change secrets-from-shell rules).

### Auto-start / stop

- **On ready:** create window → start static host (prod) → start engine child (`python -m csb serve` with `PYTHONPATH=engine`).
- **Health:** poll `/api/status` from main; push status to renderer via IPC for Start/Stop chrome.
- **Graceful shutdown:** on `before-quit` / `window-all-closed`: SIGTERM/terminate uvicorn child; wait briefly; force-kill if needed (mirror sniper `stopBotProcess` discipline). Stop static host. Do not leave orphan Python on 8787.
- **Crash:** if engine exits unexpectedly, mark status offline in UI; offer Restart (do not silently restart forever).

### Backfill

Today backfill is **CLI-only** (`python -m csb backfill`). Shell v1: main spawns that command as a **job subprocess** (stdout → IPC log / progress), not a second long-lived server. Optional later: `POST /api/backfill` with job status — not required to approve the shell.

## 4. UI additions the shell enables

Keep existing desk features (wired today):

- Kill switch engage/disengage
- Risk limits save
- Run backtest (`POST /api/backtests`)
- Live-trading-unavailable notice

Add **shell chrome** (minimal; can live in StatusBar / Settings / a thin Electron menu):

| Control | Behavior |
|---|---|
| **Engine Start / Stop** | IPC → main spawn/kill `csb serve`; status badge online/offline |
| **Run backfill** | IPC → main runs `csb backfill` (days from settings/default); progress/log; disable while running |
| **Engine status** | Port, PID/running flag, last heartbeat from `/api/status` — no CLI required |
| **Open data folder / Open .env location** | Optional convenience via `shell.openPath` |
| Offline copy | Replace “start with `python -m csb serve`” with “Start engine” when running inside Electron |

Do not turn the first viewport into a second dashboard; shell controls stay in the existing status/settings areas.

## 5. Packaging

| Item | Plan |
|---|---|
| Tooling | `electron` + `electron-builder` (same family as sniper); root or `desktop/` package entry |
| Windows first | NSIS installer x64 + optional portable exe |
| Artifacts | GitHub Releases (`Pmvita/crypto-signal-bot`), proprietary LICENSE unchanged |
| UI payload | `dashboard` static export (`out/`) as `extraResources` or unpacked files |
| Engine payload | `engine/csb`, `requirements.txt`, `.env.example` — **not** `.venv`, **not** `.env`, **not** `data/*.sqlite3` |
| Python | Per open question: system Python + first-run venv **or** bundled embeddable runtime |
| Build path | Prefer junction `C:\Users\user\Desktop\csb-build` if paren path hangs npm |
| Icons | Distinct CSB icon later; placeholder acceptable for first internal dist |
| CI | Optional follow-up: tag `v*` → Windows artifact (sniper-like); not blocking design approval |

`asarUnpack` (or `extraResources`) must leave Python-invoked files on a real filesystem path.

## 6. Security

- Engine remains **127.0.0.1 only** (`API_HOST` fixed); TrustedHostMiddleware stays.
- Desk static host binds **127.0.0.1:3000** only (not `0.0.0.0`).
- Preload: `contextIsolation: true`, `nodeIntegration: false`, `sandbox: true` where compatible.
- Secrets stay in local `.env` / userData; never in repo, never baked into release zips, never sent to renderer IPC.
- LLM keys continue to be read from the project/userData `.env` only (existing rule: do not inherit random shell `OPENAI_API_KEY`).
- No live-trading credentials or wallet flows in this pass.
- CORS: keep localhost:3000 allowlist; if static host uses that origin, no widening required. Do not enable `webSecurity: false` as the primary fix.

## 7. Migration path from current workflow

| Today | After shell (dev) | After shell (end user) |
|---|---|---|
| Terminal A: `python -m csb serve` | `npm run desktop` (main starts engine) | Install from GitHub Release → open app |
| Terminal B: `npm run dev` | Main loads Next dev or static host | Static desk inside app |
| `python -m csb backfill` | UI **Run backfill** | Same |
| `python -m csb backtest` / desk button | Desk button unchanged | Same |
| Kill switch / risk | Unchanged via API | Unchanged |

CLI remains supported for power users and CI (`pytest`, `ruff`, backfill/backtest scripts). The desktop app is the **preferred** path, not the only path.

Developer docs stay accurate: README “Quick start” keeps the two-terminal flow; a short **Desktop app (planned)** section points here until the app ships.

## 8. Implementation phases

Ordered, small steps (approve design → then implement):

1. **Scaffold** `desktop/` (main, preload, package scripts) without packaging; Window loads existing `http://127.0.0.1:3000` while user still runs Next manually — prove IPC status only.
2. **Engine lifecycle** — main spawns/stops `csb serve`; health + Start/Stop in UI; graceful quit.
3. **Backfill job** — IPC → CLI subprocess + progress UI.
4. **Static export** — enable Next `output: 'export'` (or fallback Option A standalone); main static host on :3000; fix any App Router/export breakages.
5. **First-run setup** — `.env` seed, Python/venv check, clear errors if missing.
6. **electron-builder Windows** — NSIS + portable; exclude secrets; smoke on a clean machine / junction build path.
7. **GitHub Release** — attach artifacts; README download section with **planned → available** language only when real.
8. **Optional** — bundled Python; `POST /api/backfill`; macOS later.

## 9. Open questions (for user)

1. **Python in the installer:** require system Python 3.12+ (smaller release, setup step) **or** bundle embeddable Python (larger download, one-click)? Recommendation if undecided: **system Python for first desktop slice**, bundle later.
2. **Data directory in packaged app:** keep files next to the install, or always under `%APPDATA%/Crypto Signal Bot/`? Recommendation: **userData**.
3. **If Next static export fights current Next 16 config**, OK to fall back to Option A (spawn `next start` / standalone) for v1?
4. **Product name string** for installer / `appId` (e.g. `Crypto Signal Bot` / `com.pmvita.crypto-signal-bot`) — confirm or rename.

---

**Approval gate:** no Electron implementation until this spec is explicitly approved (with answers to §9 where they affect packaging).
