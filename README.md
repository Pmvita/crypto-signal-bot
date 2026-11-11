# Crypto Signal Bot (phase 1)

Local **paper-trading** crypto signal bot: public market data via [ccxt](https://github.com/ccxt/ccxt), RSS news with optional LLM headline scoring, a trend/momentum strategy, price-only backtester, risk limits + kill switch, a FastAPI engine on `127.0.0.1:8787`, and a Next.js desk on `127.0.0.1:3000`.

**Live trading is not available in phase 1.** No code path places orders on an exchange.

**Live demo URL:** N/A (localhost only)

**License:** proprietary / all rights reserved (see `LICENSE`)

## Download (end users — no npm)

Get Windows installers from **[GitHub Releases](https://github.com/Pmvita/crypto-signal-bot/releases)** (latest: [v0.1.0](https://github.com/Pmvita/crypto-signal-bot/releases/tag/v0.1.0)):

| File | What it is |
|---|---|
| [`Crypto.Signal.Bot-0.1.0-Windows-x64.exe`](https://github.com/Pmvita/crypto-signal-bot/releases/download/v0.1.0/Crypto.Signal.Bot-0.1.0-Windows-x64.exe) | NSIS installer (recommended) |
| [`Crypto.Signal.Bot-0.1.0-Windows-x64-portable.exe`](https://github.com/Pmvita/crypto-signal-bot/releases/download/v0.1.0/Crypto.Signal.Bot-0.1.0-Windows-x64-portable.exe) | Portable exe (no install) |

**Requirements:** Windows x64, **Python 3.12+** on PATH (first run creates a venv under AppData). Phase 1 is **paper trading only** — no live exchange orders.

**Config / secrets:** `%APPDATA%\Crypto Signal Bot\` (`.env`, SQLite, `.venv`). Put LLM / OpenRouter API keys in **Settings** inside the app (never commit `.env`).

**Code signing:** builds are **unsigned** (no Authenticode cert on the build machine). Windows SmartScreen may warn on first open — use More info → Run anyway when you trust the GitHub Release asset. Default Electron icon until a custom CSB icon ships.

**License:** proprietary / all rights reserved (`LICENSE`).

## Desktop app (preferred daily path)

Windows Electron shell wraps the engine + desk: **Start/Stop engine** (API + market/news supervisor only), Run backfill, Settings **Check for updates** (git pull for local checkouts), and first-run Python venv setup. **Paper trading** is separate: open the **Trading** page and press Start/Stop trading (`POST /api/trading/start|stop`). The loop starts **stopped** after every engine start (safer); the paper portfolio is not reset. Live watch (positions, signals, paper tape) is on Trading.

Design: [`docs/superpowers/specs/2026-11-11-electron-shell-design.md`](docs/superpowers/specs/2026-11-11-electron-shell-design.md).

### Run from source (developers)

If the project path contains `)`, use the junction (recommended on this machine):

```powershell
# one-time (from junction or repo)
cd C:\Users\user\Desktop\csb-build
npm install
cd dashboard; npm ci; cd ..

# daily
npm run desktop:dev
```

That starts Electron, ensures AppData `.venv` + `.env`, starts the desk on `127.0.0.1:3000`, and starts `csb serve` on `127.0.0.1:8787` with the paper trading loop paused until you start it on Trading.

| Mode | Data / `.env` / venv |
|---|---|
| Desktop (`desktop:dev` or packaged) | `%APPDATA%\Crypto Signal Bot\` (path of truth for secrets + DB) |
| CLI without Electron | Repo root (`.env`, `data/`, `.venv`) |

**LLM / OpenRouter key:** set it in Settings inside the desktop app (masked in UI). It persists in AppData `.env` across close/reopen; saving restarts the engine. Never commit keys.

### Check for updates (Settings)

For the **local git checkout / test loop** only:

1. Settings → **Check for updates** fetches `origin/main` on `Pmvita/crypto-signal-bot`.
2. If newer commits exist and the working tree is **clean**, **Apply update** runs `git pull --ff-only`.
3. Dirty trees are refused (no force, no secret commits).
4. Packaged installs without `.git` cannot self-update via git — the UI says so and can open GitHub Releases.

Never overwrites `.env`.

### Build Windows installers (maintainers)

```powershell
cd C:\Users\user\Desktop\csb-build
npm run desktop:dist:win
```

Builds a Next.js standalone desk into `packaging/` (gitignored), then NSIS + portable under `release/` (gitignored). Unsigned by default (`CSC_IDENTITY_AUTO_DISCOVERY=false`).

## Status

Phase 1 works end-to-end on this machine (verified 2026-11-10 / 2026-11-11):

- Backfill 15m candles (Coinbase Exchange public data) for `BTC/USD`, `ETH/USD`, `SOL/USD` (re-backfill after upgrading from the old 1h/4h store)
- Price-only backtest on stored 15m candles (long + short; see numbers below after re-run)
- Paper trading cycle with live quotes + RSS fetch; loop default `CSB_CYCLE_SECONDS=20`
- Dashboard desk / signals / news / backtest / settings with real API data
- Kill switch engage/disengage via API; daily-loss halt covered by unit tests
- Engine: `pytest` + `ruff`; dashboard: `typecheck` + `lint` + `build`
- Desktop: `npm run desktop:test` (update helpers); `desktop:dev` for the shell

Screenshots: [`docs/screenshots/`](docs/screenshots/)

## Strategy (fixed constants)

Paper **long + short** on closed **15m** candles (not HFT — still bar-close decisions, not tick scalping):

- **Long:** EMA50 > EMA200 and close breaks the prior 20-bar high
- **Short:** EMA50 < EMA200 and close breaks the prior 20-bar low
- Trail stop: long = favorable extreme − 3×ATR14 (ratchets up); short = favorable extreme + 3×ATR14 (ratchets down); exit on stop or opposite trend
- News (when an LLM key is configured) can **veto** or **boost** size (polarity inverted for shorts); it never opens/closes alone
- Risk: max position % of equity, max open positions, daily loss halt (exits still allowed), kill switch (blocks everything)
- Loop cadence: `CSB_CYCLE_SECONDS` (default **20**) so new 15m closes are noticed quickly

**Portfolio migration:** existing AppData long-only positions get `side=long` via schema migrate. Shorts need the new `positions.side` column (added automatically on engine start). Re-backfill 15m history — old 1h rows are a different timeframe key and are not reused.

News is **not** included in the backtester (no clean historical headline archive).

## Verified backtest (price rules only)

Run after `python -m csb backfill --days 90` then `python -m csb backtest` against Coinbase Exchange **15m** history (~8,640 bars/symbol). Honest result — not tuned:

| Metric | Value |
|---|---|
| Symbols | BTC/USD, ETH/USD, SOL/USD |
| Timeframe | 15m |
| Bars (equity points) | 8,441 |
| Starting cash | $10,000.00 |
| Final equity | $4,860.48 |
| Total return | **−51.40%** |
| Max drawdown | 56.76% |
| Trades | 359 (167 long / 192 short) |
| Win rate | ~15.3% |
| Profit factor | ~0.35 |
| Total fees | $5,299.48 |
| Equal-weight buy & hold | ~+13.4% |
| News included | false |

Strategy constants were not tuned after this run. More history (`CSB_BACKFILL_DAYS=730`) is supported; expect fee drag on 15m churn.

## News sources

Public RSS (no keys): CoinDesk, Cointelegraph, Decrypt, The Block, Kraken Blog, Bitfinex Blog.

LLM scoring is **off** until `OPENAI_API_KEY` + `OPENAI_MODEL` (or Anthropic equivalents) are set in the project `.env`. Keys are read from that file only, never from the shell environment. Keep `.env` local — it is gitignored and must not be committed.

### OpenRouter (optional)

Use any OpenAI-compatible endpoint by setting `OPENAI_BASE_URL` (default `https://api.openai.com/v1`). For [OpenRouter](https://openrouter.ai):

```env
CSB_LLM_PROVIDER=openai
OPENAI_BASE_URL=https://openrouter.ai/api/v1
OPENAI_API_KEY=your-openrouter-key
OPENAI_MODEL=openai/gpt-4o-mini
```

Copy names from `.env.example`; put real keys only in your local `.env`.

## CLI quick start (power users / CI)

Python 3.12+ and Node 22+ recommended. Prefer the [Desktop app](#desktop-app-preferred-daily-path) for daily use. If the project path contains `)`, use junction `C:\Users\user\Desktop\csb-build`.

```powershell
# one-time
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r engine\requirements-dev.txt
Copy-Item .env.example .env
cd dashboard; npm ci; cd ..

# engine commands (PYTHONPATH must include engine/)
$env:PYTHONPATH = "$PWD\engine"
.\.venv\Scripts\python.exe -m csb backfill
.\.venv\Scripts\python.exe -m csb backtest
.\.venv\Scripts\python.exe -m csb news
.\.venv\Scripts\python.exe -m csb cycle
.\.venv\Scripts\python.exe -m csb serve   # API + data supervisor; trading paused until /api/trading/start

# dashboard (second terminal)
cd dashboard
npm run dev    # http://127.0.0.1:3000
```

## What works / what does not

| Works | Does not (phase 1) |
|---|---|
| Public 15m candle + ticker data | Live exchange order placement |
| Paper broker with fees/slippage; paper long + short | Leverage / live derivatives / HFT |
| RSS ingest + optional LLM scores | News overlay in the backtester |
| Risk limits, kill switch, daily halt | Remote / non-loopback API access |
| Local dashboard + Electron shell + Windows Release installers | Hosted public demo URL; Authenticode-signed installer (unsigned OK; SmartScreen may warn) |

## Tests

```powershell
$env:PYTHONPATH = "$PWD\engine"
.\.venv\Scripts\python.exe -m pytest engine
.\.venv\Scripts\python.exe -m ruff check engine\csb engine\tests
cd dashboard; npm run typecheck; npm run lint; npm run build
npm run desktop:test
```

CI: GitHub Actions workflow at [`.github/workflows/ci.yml`](.github/workflows/ci.yml) (engine + dashboard + desktop unit tests).

## Layout

```
crypto-signal-bot/
├── desktop/             Electron main / preload / lifecycle / updates
├── engine/csb/          FastAPI + trading loop + backtester
├── dashboard/           Next.js desk (App Router)
├── docs/                Spec, plan, screenshots
├── data/                Local SQLite (gitignored)
├── package.json         Electron + builder scripts
└── .env.example         Config names only
```

## Disclaimer

Not financial advice. Paper results do not predict live performance. Trading digital assets involves substantial risk of loss.
