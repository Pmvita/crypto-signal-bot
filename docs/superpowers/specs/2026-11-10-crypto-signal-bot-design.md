# Crypto Signal Bot — Phase 1 Design

Date: 2026-11-10
Status: approved by the user; phase 1 (data, backtester, paper trading, dashboard)

## 1. Purpose

A background service that reads market data and crypto news and trades automatically in **paper mode**, with a local web dashboard. It trades liquid coins on a multi-hour to multi-day horizon. It cannot compete on reaction speed, so news is a filter and booster on top of price signals, and it trades infrequently to keep fees small.

User decisions that shape the design:

| Question | Decision |
|---|---|
| Exchange | Undecided. Build exchange-agnostic on `ccxt`; start in paper mode. |
| Form | Background service plus local web dashboard; movable to a server later. |
| News interpretation | An LLM scores each headline. |
| Autonomy | Fully automatic within risk limits. |

## 2. Scope

In scope for phase 1: historical and live market data, news collection, LLM headline scoring, strategy, backtester, paper broker, risk limits, local API, dashboard.

Out of scope for phase 1:

- **Live order placement.** No code path sends an order to an exchange. The dashboard and README state that live trading is not available.
- **Backtesting the news overlay.** Clean historical news is not available, so the backtest validates the price side only. This is stated in the README and next to every backtest result in the dashboard.
- Short selling, leverage, derivatives, limit orders, partial fills.
- Remote access. The API and dashboard bind to `127.0.0.1` only.

Honesty rules (hard requirements):

- Market data comes only from the real exchange feed. There is no synthetic or seeded market data outside the test suite.
- If no LLM API key is configured, news scoring is off, headlines are stored and shown as unscored, and the dashboard says so. No invented scores. Stub scorers exist only in tests.
- Strategy parameters are fixed in this document before any backtest is run and are not tuned afterwards. Whatever the backtest shows is reported, including a loss.

## 3. Architecture

```
            ┌────────────────────── engine (Python, one process) ──────────────────────┐
 exchange ──► MarketData (ccxt) ──► candles ─┐                                          │
 (public)                                    ├─► Strategy ─► OrderRouter ─► Broker      │
 RSS feeds ─► NewsFeeds ─► headlines ─► Scorer (LLM) ─► news score ─┘        │   (PaperBroker)
                                                                  RiskManager ┘      │
                         SQLite (data/csb.sqlite3)  ◄── Portfolio ledger ◄── fills ──┘ │
            │            FastAPI on 127.0.0.1:8787  (read state, set limits, kill switch)│
            └───────────────────────────────────────────────────────────────────────────┘
                                         ▲ HTTP (CORS: localhost:3000 only)
                          Next.js dashboard on 127.0.0.1:3000
```

- **Engine**: Python 3.12 package `csb` in `engine/`. FastAPI serves the local API; the trading loop runs in a background thread of the same process. Storage is one SQLite file in WAL mode.
- **Dashboard**: Next.js (App Router, TypeScript, Tailwind, shadcn/ui) in `dashboard/`. Client-side polling of the engine API.
- **Contract**: the JSON API in section 10 is the only coupling between the two.

### Module boundaries (engine)

| Module | Responsibility | Depends on |
|---|---|---|
| `config.py` | Read settings from the project's own `.env` and environment | — |
| `db.py` | SQLite connection, schema | — |
| `models.py` | Dataclasses and enums shared by all modules | — |
| `indicators.py` | EMA, ATR, prior highest high (pure functions) | — |
| `candles.py` | Candle storage, 1h → 4h aggregation | `db`, `models` |
| `marketdata.py` | ccxt wrapper: paginated backfill, incremental update, ticker | `candles` |
| `strategy.py` | Pure decision and sizing functions | `indicators`, `models` |
| `news_feeds.py` | Feed list, fetch, parse | `models` |
| `news_scoring.py` | `Scorer` protocol, OpenAI and Anthropic scorers, response validation | `models` |
| `news_store.py` | Headline and score persistence, per-coin aggregate | `db`, `models` |
| `risk.py` | Limits, persisted state, order checks, kill switch | `models` |
| `broker.py` | `Broker` protocol and `PaperBroker` | `models` |
| `portfolio.py` | Cash and position ledger, persistence | `db`, `models` |
| `execution.py` | `OrderRouter`: the only path from a decision to a broker | `risk`, `broker`, `portfolio` |
| `backtest.py` | Historical replay using the same strategy, sizing, risk and ledger code | `strategy`, `risk`, `portfolio`, `broker` |
| `service.py` | One trading cycle and the loop | everything above |
| `api.py` | FastAPI app | `service`, stores |
| `cli.py` | `python -m csb backfill | backtest | news | cycle | serve` | everything above |

The strategy never sees a broker. The risk manager never sees an exchange. Adding a live broker in phase 2 means writing one class that satisfies `Broker` and selecting it in `service.py`.

## 4. Market data

- Library: `ccxt`. The exchange id is the setting `CSB_EXCHANGE`. No API key is used; only public endpoints are called.
- **Default exchange: `coinbaseexchange`** (Coinbase Exchange public API). Reason: verified from this machine on 2026-11-10 that Kraken's public OHLC endpoint returns only the most recent 720 candles regardless of the `since` parameter (30 days of 1h data), which is too short to backtest a strategy whose slow average needs 33 days to warm up. Coinbase Exchange and Bitstamp both served 1h candles two years back without a key. Kraken remains selectable with `CSB_EXCHANGE=kraken`; it works for live operation and a 30-day history.
- Default symbols: `BTC/USD`, `ETH/USD`, `SOL/USD` (`CSB_SYMBOLS`).
- Stored timeframe: **1h** candles, closed candles only (a candle is stored once `ts + 1h <= now`).
- Signal timeframe: **4h**, built locally by aggregating 1h candles into UTC-aligned buckets (00, 04, 08, 12, 16, 20). A 4h bar exists only when its end time has passed. This works on every exchange, including those without a native 4h interval.
- Backfill: `python -m csb backfill` pages forward from `now - CSB_BACKFILL_DAYS` (default 730) using `fetch_ohlcv(symbol, "1h", since, limit)` until it reaches the present, upserting on `(exchange, symbol, timeframe, ts)`.
- Live feed: each cycle fetches 1h candles after the newest stored timestamp and a ticker (bid, ask, last) per symbol. Polling, not websockets: the strategy acts on 4h bars, so a 60 second poll is ample and keeps the code exchange-agnostic.
- Stale data guard: a symbol is not evaluated when the newest closed 4h bar ended more than 4 hours ago (a newer bar should exist, so the feed is behind).

## 5. News

### Sources

Chosen after checking each from this machine on 2026-11-10. All are public RSS feeds that need no key.

| Name | Kind | URL |
|---|---|---|
| CoinDesk | news | `https://www.coindesk.com/arc/outboundfeeds/rss/` |
| Cointelegraph | news | `https://cointelegraph.com/rss` |
| Decrypt | news | `https://decrypt.co/feed` |
| The Block | news | `https://www.theblock.co/rss.xml` |
| Kraken Blog | exchange | `https://blog.kraken.com/feed` |
| Bitfinex Blog | exchange | `https://blog.bitfinex.com/feed/` |

Dropped as unreachable or unusable: Coinbase blog RSS (HTTP 403), CryptoPanic RSS (HTTP 410), Bitstamp blog RSS (404), Gemini blog RSS (404), OKX help RSS (404), Binance blog RSS (HTTP 202 bot challenge, no entries), BitMEX blog feed (redirects to an HTML page). Binance's announcement JSON endpoint responded but is an undocumented internal web API, so it is not used.

Each fetch records per-source success or failure. A failing source does not stop the others, and its error is visible in the dashboard.

### Collection

Every `CSB_NEWS_REFRESH_SECONDS` (default 600) the engine fetches all feeds with `httpx` (redirects followed, 20 s timeout), parses them with `feedparser`, and inserts new headlines keyed by URL. Stored fields: source, title, URL, published time, fetched time, score status.

### Scoring

- Provider is `CSB_LLM_PROVIDER` (`openai` or `anthropic`, default `openai`). Scoring is enabled only when the selected provider's key (`OPENAI_API_KEY` or `ANTHROPIC_API_KEY`) is set in the project's `.env`. Model names come from `OPENAI_MODEL` / `ANTHROPIC_MODEL`.
- Calls go straight to the providers' HTTPS APIs with `httpx` (no vendor SDKs).
- Headlines published in the last 48 hours and not yet scored are sent in batches of 20. Headline text is untrusted input: the prompt tells the model to treat it as data, and the response is accepted only if it is valid JSON matching the schema below. Anything else marks the batch as `error`.
- Per headline the model returns zero or more entries, one per affected tracked coin:
  - `coin`: base asset of a tracked symbol (for example `BTC`). Market-wide news lists every tracked coin it affects.
  - `direction`: `-1` bearish, `0` neutral, `1` bullish.
  - `strength`: 0 to 1, how large the expected effect is.
  - `confidence`: 0 to 1, how sure the model is.
  - `rationale`: one short sentence.
- Values outside the ranges are clamped; unknown coins are discarded.

### Per-coin news score

For a coin at time `t`, over scored entries from headlines published in the last 24 hours:

```
weight_i = confidence_i × (1 − age_i / 24h)
score    = Σ(weight_i × direction_i × strength_i) / max(Σ weight_i, 1.0)      range −1 … +1
```

The `max(…, 1.0)` stops a single low-confidence headline from producing an extreme score. The headlines that contributed are recorded with the signal.

News state passed to the strategy:

| State | Condition | Effect |
|---|---|---|
| `off` | scoring disabled (no key) | none |
| `no_headlines` | scoring on, nothing scored for the coin in 24 h | none |
| `veto` | score ≤ −0.30 | new entries blocked |
| `boost` | score ≥ +0.30 | entry size × 1.25 (risk limits still cap it) |
| `neutral` | otherwise | none |

News never opens or closes a position by itself. It only blocks or enlarges an entry that the price rules already produced. Exits are driven by price alone.

## 6. Strategy

Long-only trend following on 4h bars. One position per symbol, no pyramiding. All parameters are fixed constants in `strategy.py`; none are exposed for tuning in the dashboard.

Indicators on closed 4h bars:

- `EMA50`, `EMA200` of closes (seeded with the simple average of the first N closes).
- `HH20`: highest high of the previous 20 bars, not including the current bar.
- `ATR14`: Wilder average true range.

Rules, evaluated once per newly closed 4h bar per symbol:

- **Entry** (flat): `EMA50 > EMA200` (uptrend) and `close > HH20` (breakout to a 20-bar high) and news state is not `veto`.
- **Stop**: on entry, `stop = close − 3 × ATR14`. On each later bar, `stop = max(previous stop, highest close since entry − 3 × ATR14)`. The stop only moves up.
- **Exit** (in position): `close < stop`, or `EMA50 < EMA200` (trend ended).
- Otherwise hold.

Position size (volatility-adjusted): risk 1% of equity between entry and the initial stop.

```
qty = (equity × 0.01 × news_multiplier) / (3 × ATR14)
```

The risk manager then caps the notional at the maximum position size and at available cash. Orders below 10 USD notional are skipped.

Every evaluation is stored as a signal (`enter`, `exit` or `hold`) with the reasons in plain language, the indicator values, the news state and score, and the contributing headlines.

Warm-up: 200 4h bars (about 33 days) are needed before the first signal.

## 7. Backtester

- Input: stored 1h candles aggregated to 4h, for all configured symbols, sharing one portfolio.
- Uses the same `strategy.decide`, sizing, `RiskManager` (with in-memory state) and `Portfolio` ledger as live paper trading.
- No lookahead: decisions use the bar that just closed; orders fill at the **next bar's open**. Decisions on the final bar are not executed.
- Costs: buys fill at `open × (1 + slippage)`, sells at `open × (1 − slippage)`; a fee of `fee_bps` is charged on the notional of every fill. Defaults: `CSB_FEE_BPS=40` (0.40% per side, the entry-tier taker fee at Kraken Pro), `CSB_SLIPPAGE_BPS=5`.
- Within a bar, exits are processed before entries, and entries in configured symbol order.
- News state is `off` for the whole replay. **The backtest validates price rules only.**
- Positions still open at the end are valued at the last close and reported as open; they are not counted as closed trades.
- Reported: data range, tested period (from the first bar with complete indicators), starting and final equity, total return after fees and slippage, maximum drawdown (peak to trough of bar-close equity), number of closed trades, win rate, profit factor, total fees, equal-weight buy-and-hold return over the same period for context (no costs), the trade list, and a down-sampled equity curve.
- Results are stored in `backtest_runs`; the dashboard shows the latest.

## 8. Execution

```python
class Broker(Protocol):
    name: str
    def market_order(self, symbol: str, side: Side, qty: float, quote: Quote, ts_ms: int) -> Fill: ...
```

- `PaperBroker` is the only implementation. Buys fill at the ask and sells at the bid from the live ticker (falling back to last), moved by `slippage_bps` against the trader, with `fee_bps` charged on notional. It never contacts an exchange.
- `OrderRouter.submit(request)` is the only caller of a broker: it asks `RiskManager` first, then the broker, then applies the fill to the `Portfolio` ledger and records the order. Rejected orders are recorded with the reason.
- Paper account: `CSB_STARTING_CASH` (default 10,000 USD). Cash, positions, realised P&L and fees persist in SQLite.
- A phase 2 `CcxtBroker` implements `market_order` by placing a real order and returning the exchange's fill. Strategy, risk and router code do not change.

## 9. Risk limits

Checked by `RiskManager` for every order, live and backtest. Settings and state persist in SQLite and survive restarts.

| Limit | Default | Behaviour |
|---|---|---|
| Maximum position size | 25% of equity | Entry quantity is reduced so notional ≤ limit. |
| Maximum open positions | 3 | An entry beyond the limit is rejected. |
| Daily loss limit | 3% of equity at the start of the UTC day | When equity falls to `day start × (1 − limit)` trading is halted until the next UTC day. While halted, **entries are rejected; exits are still allowed** so stops keep protecting open positions. The halt survives restarts and is not cleared by raising the limit. |
| Kill switch | off | While engaged, **every order is rejected, exits included**. Open positions are left as they are. Data collection and mark-to-market continue. |

Equity for the daily limit includes unrealised P&L and is evaluated every cycle. Sells are never blocked by the position-size or position-count limits. The limits are editable in the dashboard within validated ranges (position size 1–100%, open positions 1–20, daily loss 0.5–50%).

## 10. Local API

FastAPI on `127.0.0.1:8787` (`CSB_API_PORT` changes the port; the host is not configurable in phase 1). CORS allows `http://localhost:3000` and `http://127.0.0.1:3000`. The `Host` header must be `127.0.0.1` or `localhost`. Timestamps are Unix milliseconds, UTC.

| Method and path | Purpose |
|---|---|
| `GET /api/status` | Mode, live-trading availability (always `false`), exchange, symbols, engine heartbeat, news scoring state, risk state |
| `GET /api/portfolio` | Cash, equity, P&L, open positions with live prices |
| `GET /api/equity` | Equity curve points |
| `GET /api/signals?limit=` | Signals with reasons, indicators, news state, headlines and scores, resulting order |
| `GET /api/trades?limit=` | Order log including rejections |
| `GET /api/news?limit=` | Headlines, their scores or unscored status, per-source fetch status |
| `GET /api/backtests/latest` | Latest backtest run or `null` |
| `POST /api/backtests` | Run a backtest on stored candles and return it |
| `GET /api/risk` | Limits, kill switch, daily state |
| `PUT /api/risk` | Update limits |
| `POST /api/kill-switch` | `{ "engaged": true | false }` |

There is no endpoint that places an order or changes strategy parameters.

## 11. Dashboard

A dense trading-desk interface: dark, monospaced numerals, amber as the single accent, green and red reserved for gains and losses. No purple, no gradients, no cream or terracotta. Built from shadcn/ui components.

A persistent status bar shows: `PAPER` mode, "Live trading: not available", exchange, engine heartbeat, news scoring on or off, and the kill switch state. If the engine is unreachable every view says so instead of showing stale numbers.

| Route | Content |
|---|---|
| `/` Desk | Equity, cash, day and total P&L, open positions, watchlist with live prices and trend state, equity curve, latest signals and headlines |
| `/signals` | Every signal with reasons, indicator values, news state, contributing headlines and their scores |
| `/trades` | Order log with fills, fees, realised P&L and rejection reasons |
| `/news` | Headlines by source with scores, or "unscored" when scoring is off; source health |
| `/backtest` | Latest result with the price-only notice, metrics, equity curve, trades, run button |
| `/settings` | Risk limits form, kill switch, live-trading "not available in phase 1" notice |

## 12. Configuration

`.env` in the project root (never committed; `.env.example` lists the names):

```
CSB_EXCHANGE=coinbaseexchange
CSB_SYMBOLS=BTC/USD,ETH/USD,SOL/USD
CSB_BACKFILL_DAYS=730
CSB_STARTING_CASH=10000
CSB_FEE_BPS=40
CSB_SLIPPAGE_BPS=5
CSB_CYCLE_SECONDS=60
CSB_NEWS_REFRESH_SECONDS=600
CSB_API_PORT=8787
CSB_DB_PATH=data/csb.sqlite3
CSB_LLM_PROVIDER=openai
OPENAI_API_KEY=
OPENAI_MODEL=
ANTHROPIC_API_KEY=
ANTHROPIC_MODEL=
```

## 13. Trading cycle

Every `CSB_CYCLE_SECONDS`:

1. Fetch new 1h candles for each symbol.
2. If due, fetch news; if scoring is enabled, score pending headlines.
3. Fetch tickers, value the portfolio, store an equity point, update the daily-loss state.
4. For each symbol with a newly closed 4h bar: compute indicators, news state and the decision; store the signal; update the trailing stop.
5. Submit exits, then entries, through `OrderRouter`.
6. Record the cycle (start, end, status, error, summary) as the heartbeat.

If the engine was down, only the newest closed bar is evaluated on restart; missed bars are not replayed. An exception in one cycle is recorded and the loop continues.

## 14. Testing and verification

- `pytest` for indicators, candle aggregation, strategy, sizing, news parsing, score validation, score aggregation, both LLM scorers against a mocked HTTP transport, risk limits and persistence, paper broker, portfolio ledger, order router, backtester, service cycle (fake exchange, stub scorer), and API.
- Dashboard: `tsc --noEmit`, ESLint, `next build`.
- GitHub Actions workflow runs both jobs.
- Manual verification with real data: backfill, backtest, one live paper cycle, real headline fetch, dashboard screenshots, kill switch and daily-loss halt.

## 15. Phase 2 (not built)

Live `CcxtBroker` with exchange keys, order reconciliation, an authenticated remote deployment for 24/7 running, and an archive of scored headlines so the news overlay can eventually be backtested.
