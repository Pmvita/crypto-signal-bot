# Crypto Signal Bot (phase 1)

Local **paper-trading** crypto signal bot: public market data via [ccxt](https://github.com/ccxt/ccxt), RSS news with optional LLM headline scoring, a trend/momentum strategy, price-only backtester, risk limits + kill switch, a FastAPI engine on `127.0.0.1:8787`, and a Next.js desk on `127.0.0.1:3000`.

**Live trading is not available in phase 1.** No code path places orders on an exchange.

**Live demo URL:** N/A (localhost only)

**License:** proprietary / all rights reserved (see `LICENSE`)

## Desktop app (planned)

A Windows Electron shell (engine start/stop, backfill from the UI, packaged installer) is **planned, not shipped**. Design draft for approval: [`docs/superpowers/specs/2026-11-11-electron-shell-design.md`](docs/superpowers/specs/2026-11-11-electron-shell-design.md). Until that lands, use the Quick start below (`csb serve` + `npm run dev`).

## Status

Phase 1 works end-to-end on this machine (verified 2026-11-10 / 2026-11-11):

- Backfill ~2 years of 1h candles (Coinbase Exchange public data) for `BTC/USD`, `ETH/USD`, `SOL/USD`
- Price-only backtest on stored candles (see numbers below)
- One paper trading cycle with live quotes + RSS fetch
- Dashboard desk / signals / news / backtest / settings with real API data
- Kill switch engage/disengage via API; daily-loss halt covered by unit tests
- Engine: `pytest` + `ruff`; dashboard: `typecheck` + `lint` + `build`

Screenshots: [`docs/screenshots/`](docs/screenshots/)

## Strategy (fixed constants)

Long-only on closed **4h** bars built from 1h candles:

- Enter when EMA50 > EMA200 and close breaks the prior 20-bar high
- Trail stop = highest close since entry − 3×ATR14; exit on stop or EMA50 < EMA200
- News (when an LLM key is configured) can **veto** or **boost** size; it never opens/closes alone
- Risk: max position % of equity, max open positions, daily loss halt (exits still allowed), kill switch (blocks everything)

News is **not** included in the backtester (no clean historical headline archive).

## Verified backtest (price rules only)

Run after `python -m csb backfill` then `python -m csb backtest` against Coinbase Exchange 1h history (~17,510 bars/symbol, ~730 days):

| Metric | Value |
|---|---|
| Symbols | BTC/USD, ETH/USD, SOL/USD |
| Bars (4h equity points) | 4,180 |
| Starting cash | $10,000.00 |
| Final equity | $9,899.92 |
| Total return | **−1.00%** |
| Max drawdown | 24.42% |
| Trades | 85 |
| Win rate | ~28.2% |
| Profit factor | ~0.98 |
| Total fees | $1,438.35 |
| Equal-weight buy & hold | ~−46.2% |
| News included | false |

Strategy constants were not tuned after this run.

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

## Quick start (Windows)

Python 3.12+ and Node 22+ recommended. If the project path contains `)`, use a short junction for npm (this repo was verified via `C:\Users\user\Desktop\csb-build`).

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
.\.venv\Scripts\python.exe -m csb serve   # http://127.0.0.1:8787

# dashboard (second terminal)
cd dashboard
npm run dev    # http://127.0.0.1:3000
```

## What works / what does not

| Works | Does not (phase 1) |
|---|---|
| Public candle + ticker data | Live exchange order placement |
| Paper broker with fees/slippage | Shorting / leverage / derivatives |
| RSS ingest + optional LLM scores | News overlay in the backtester |
| Risk limits, kill switch, daily halt | Remote / non-loopback API access |
| Local dashboard | Hosted public demo URL |

## Tests

```powershell
$env:PYTHONPATH = "$PWD\engine"
.\.venv\Scripts\python.exe -m pytest engine
.\.venv\Scripts\python.exe -m ruff check engine\csb engine\tests
cd dashboard; npm run typecheck; npm run lint; npm run build
```

CI: GitHub Actions workflow at [`.github/workflows/ci.yml`](.github/workflows/ci.yml) (engine + dashboard jobs).

## Layout

```
crypto-signal-bot/
├── engine/csb/          FastAPI + trading loop + backtester
├── dashboard/           Next.js desk (App Router)
├── docs/                Spec, plan, screenshots
├── data/                Local SQLite (gitignored)
└── .env.example         Config names only
```

## Disclaimer

Not financial advice. Paper results do not predict live performance. Trading digital assets involves substantial risk of loss.
