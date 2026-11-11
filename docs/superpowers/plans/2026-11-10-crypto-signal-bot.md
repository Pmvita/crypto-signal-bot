# Crypto Signal Bot (Phase 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a paper-trading crypto bot (market data, news scoring, strategy, backtester, risk limits, paper broker) with a local API and a Next.js dashboard.

**Architecture:** One Python process (`engine/csb`) runs a FastAPI app on `127.0.0.1:8787` and a background trading loop, storing everything in one SQLite file. A Next.js dashboard on `127.0.0.1:3000` polls the API. The JSON API in spec section 10 is the only contract between them, so engine tasks (1–12) and dashboard tasks (13–15) can proceed in parallel once Task 11 fixes the response shapes.

**Tech Stack:** Python 3.12, ccxt, FastAPI, uvicorn, httpx, feedparser, python-dotenv, SQLite, pytest, ruff. Next.js (App Router), TypeScript, Tailwind CSS v4, shadcn/ui, SWR, Recharts.

**Spec:** `docs/superpowers/specs/2026-11-10-crypto-signal-bot-design.md`

**Format note:** This plan gives every task its files, exact interfaces, the failing tests to write first (code for the behaviour-defining ones, names for the rest), the rules the implementation must satisfy, the commands, and the commit. It does not reproduce every implementation body in full, which the writing-plans skill asks for; the plan was executed immediately by its author, so the bodies live in the commits instead.

## Global Constraints

- Project root: `C:\Users\user\Desktop\MAIN\Projects\6) AI\crypto-signal-bot`. Run installs, tests and builds through the junction `C:\Users\user\Desktop\csb-build` (the real path contains `)`, which hangs npm and vitest on this machine).
- Python: `C:\Users\user\AppData\Local\Programs\Python\Python312\python.exe` creates `.venv` in the project root. Always invoke `.\.venv\Scripts\python.exe -m ...`.
- No live order placement anywhere. `PaperBroker` is the only broker.
- Nothing fake presented as real: real exchange data only; no LLM key means scoring is off and shown as off; stub scorers only under `engine/tests`.
- Never read `.env` files outside this project. Ship `.env.example` with names only.
- API and dashboard bind to `127.0.0.1`.
- Strategy constants are those in spec section 6 and are not changed after the first backtest run.
- Python imports at the top of the module, never inside functions (ruff rule `PLC0415` enforces it). TypeScript switches over unions end with a `never` check.
- Git: local repository only; no remote, no push. Never commit `.env*` (except `.env.example`), `node_modules`, `.next`, `.venv`, `data/`.
- UI: dark trading desk, amber accent, green/red only for P&L, no purple, no gradients, no cream or terracotta.
- Timestamps are Unix milliseconds UTC everywhere in the engine and API.

## File Structure

```
crypto-signal-bot/
├── .env.example                  names only
├── .gitignore
├── README.md
├── .github/workflows/ci.yml      engine tests + dashboard typecheck/lint/build
├── docs/
│   ├── superpowers/specs/2026-11-10-crypto-signal-bot-design.md
│   ├── superpowers/plans/2026-11-10-crypto-signal-bot.md
│   └── screenshots/              dashboard screenshots from verification
├── data/                         SQLite file (gitignored)
├── engine/
│   ├── pyproject.toml            pytest + ruff config
│   ├── requirements.txt          runtime pins
│   ├── requirements-dev.txt      pytest, ruff
│   ├── csb/
│   │   ├── __init__.py
│   │   ├── __main__.py           python -m csb → cli.main()
│   │   ├── config.py             Settings, load_settings()
│   │   ├── db.py                 connect(), init_schema()
│   │   ├── models.py             Candle, Quote, Side, Position, Fill, OrderRequest, Headline, HeadlineScore, NewsView …
│   │   ├── indicators.py         ema(), atr(), prior_highest()
│   │   ├── candles.py            upsert_candles(), load_candles(), latest_ts(), aggregate()
│   │   ├── marketdata.py         MarketData (ccxt wrapper)
│   │   ├── strategy.py           StrategyParams, build_snapshots(), decide(), position_size()
│   │   ├── news_feeds.py         FEEDS, parse_feed(), fetch_feeds()
│   │   ├── news_scoring.py       Scorer, OpenAIScorer, AnthropicScorer, parse_scores(), build_scorer()
│   │   ├── news_store.py         save_headlines(), pending_headlines(), save_scores(), news_view()
│   │   ├── risk.py               RiskLimits, RiskState, MemoryRiskStore, SqliteRiskStore, RiskManager
│   │   ├── broker.py             Broker protocol, PaperBroker
│   │   ├── portfolio.py          Portfolio, load_portfolio(), save_portfolio()
│   │   ├── execution.py          OrderRouter, OrderResult
│   │   ├── backtest.py           run_backtest(), BacktestResult
│   │   ├── service.py            TradingService (run_cycle, run_forever)
│   │   ├── api.py                create_app()
│   │   └── cli.py                backfill | backtest | news | cycle | serve
│   └── tests/                    one test module per source module
└── dashboard/
    ├── package.json              scripts: dev, build, start, lint, typecheck (all bound to 127.0.0.1)
    └── src/
        ├── app/                  layout.tsx, globals.css, page.tsx, signals/, trades/, news/, backtest/, settings/
        ├── components/           desk shell, status bar, tables, charts, ui/ (shadcn)
        └── lib/                  types.ts (API contract), api.ts (fetchers), format.ts
```

---

### Task 1: Project skeleton, configuration and database

**Files:**
- Create: `.gitignore`, `.env.example`, `engine/pyproject.toml`, `engine/requirements.txt`, `engine/requirements-dev.txt`
- Create: `engine/csb/__init__.py`, `engine/csb/config.py`, `engine/csb/db.py`, `engine/csb/models.py`
- Test: `engine/tests/test_config.py`, `engine/tests/test_db.py`

**Interfaces:**
- Produces:
  - `config.Settings` (frozen dataclass): `exchange: str`, `symbols: tuple[str, ...]`, `backfill_days: int`, `starting_cash: float`, `fee_bps: float`, `slippage_bps: float`, `cycle_seconds: int`, `news_refresh_seconds: int`, `api_port: int`, `db_path: Path`, `llm_provider: str`, `openai_api_key: str`, `openai_model: str`, `anthropic_api_key: str`, `anthropic_model: str`; property `coins -> tuple[str, ...]` (base assets).
  - `config.load_settings(env: Mapping[str, str] | None = None) -> Settings` (reads the project `.env` only when `env` is None).
  - `config.API_HOST = "127.0.0.1"`, `config.PROJECT_ROOT: Path`.
  - `db.connect(path: Path | str) -> sqlite3.Connection` (WAL, `row_factory=sqlite3.Row`, foreign keys on), `db.init_schema(conn) -> None` (idempotent).
  - `models`: `Side` (`BUY`, `SELL`), `Action` (`ENTER`, `EXIT`, `HOLD`), `NewsState` (`OFF`, `NO_HEADLINES`, `NEUTRAL`, `BOOST`, `VETO`), dataclasses `Candle(ts, open, high, low, close, volume)`, `Quote(symbol, bid, ask, last, ts)`, `Position(symbol, qty, entry_price, entry_ts, stop_price, highest_close)`, `Fill(symbol, side, qty, price, fee, ts, broker)`, `OrderRequest(symbol, side, qty, signal_id=None)`, `Headline(source, kind, title, url, published_at)`, `HeadlineScore(coin, direction, strength, confidence, rationale)`, `ScoredHeadline(id, source, title, url, published_at, score: HeadlineScore)`, `NewsView(state, score, headlines)`.

- [ ] **Step 1: Write the failing tests**

```python
# engine/tests/test_config.py
from csb.config import API_HOST, load_settings


def test_defaults_use_keyless_public_exchange_and_paper_values():
    s = load_settings({})
    assert s.exchange == "coinbaseexchange"
    assert s.symbols == ("BTC/USD", "ETH/USD", "SOL/USD")
    assert s.coins == ("BTC", "ETH", "SOL")
    assert s.fee_bps == 40 and s.slippage_bps == 5
    assert s.openai_api_key == "" and s.anthropic_api_key == ""


def test_api_host_is_loopback_and_not_configurable():
    s = load_settings({"CSB_API_HOST": "0.0.0.0"})
    assert API_HOST == "127.0.0.1"
    assert not hasattr(s, "api_host")
```

```python
# engine/tests/test_db.py
from csb.db import connect, init_schema

TABLES = {"candles", "news_items", "news_scores", "news_sources", "signals", "orders", "positions",
          "account", "equity_snapshots", "risk_settings", "risk_state", "cycles", "backtest_runs", "quotes", "meta"}


def test_init_schema_creates_all_tables_and_is_idempotent(tmp_path):
    conn = connect(tmp_path / "t.sqlite3")
    init_schema(conn)
    init_schema(conn)
    names = {r["name"] for r in conn.execute("select name from sqlite_master where type='table'")}
    assert TABLES <= names
```

- [ ] **Step 2: Run to verify they fail** — `.\.venv\Scripts\python.exe -m pytest engine/tests/test_config.py engine/tests/test_db.py -q` from the junction; expected: `ModuleNotFoundError: No module named 'csb.config'`.
- [ ] **Step 3: Implement** `config.py`, `db.py`, `models.py` to the interfaces above; `pyproject.toml` sets `pythonpath = ["."]`, `testpaths = ["tests"]` and ruff `select = ["E", "F", "I", "B", "UP", "PLC0415"]`.
- [ ] **Step 4: Run to verify they pass** — same command, expected `3 passed`.
- [ ] **Step 5: Commit** — `git add -A && git commit -m "chore: project skeleton, config and schema"`.

---

### Task 2: Indicators and candle aggregation

**Files:**
- Create: `engine/csb/indicators.py`, `engine/csb/candles.py`
- Test: `engine/tests/test_indicators.py`, `engine/tests/test_candles.py`

**Interfaces:**
- Consumes: `models.Candle`, `db.connect`, `db.init_schema`.
- Produces:
  - `indicators.ema(values: Sequence[float], period: int) -> list[float | None]` (first `period-1` entries `None`; entry `period-1` is the SMA seed).
  - `indicators.atr(candles: Sequence[Candle], period: int) -> list[float | None]` (Wilder; first value at index `period`).
  - `indicators.prior_highest(highs: Sequence[float], period: int) -> list[float | None]` (index `i` = max of `highs[i-period:i]`; `None` while `i < period`).
  - `candles.upsert_candles(conn, exchange, symbol, timeframe, candles) -> int`, `candles.load_candles(conn, exchange, symbol, timeframe, since_ms=None) -> list[Candle]`, `candles.latest_ts(conn, exchange, symbol, timeframe) -> int | None`.
  - `candles.aggregate(candles: Sequence[Candle], hours: int, now_ms: int) -> list[Candle]` (UTC-aligned buckets; a bucket is emitted only when `bucket_start + hours*3600_000 <= now_ms`).
  - `candles.HOUR_MS = 3_600_000`.

- [ ] **Step 1: Write the failing tests**

```python
# engine/tests/test_indicators.py (behaviour-defining cases)
def test_ema_seeds_with_simple_average_then_smooths():
    out = ema([1, 2, 3, 4, 5], 3)
    assert out[:2] == [None, None]
    assert out[2] == pytest.approx(2.0)           # SMA of 1,2,3
    assert out[3] == pytest.approx(3.0)           # 2 + 0.5*(4-2)
    assert out[4] == pytest.approx(4.0)


def test_prior_highest_excludes_current_bar():
    assert prior_highest([1, 5, 2, 9], 2) == [None, None, 5, 5]


def test_atr_uses_true_range_including_gaps():
    cs = [Candle(0, 10, 11, 9, 10, 0), Candle(1, 10, 12, 10, 11, 0), Candle(2, 14, 15, 13, 14, 0)]
    out = atr(cs, 2)
    assert out[:2] == [None, None]
    assert out[2] == pytest.approx((2 + 4) / 2)   # TR1 = 12-10 = 2, TR2 = 15-11 = 4 (gap up)
```

```python
# engine/tests/test_candles.py (behaviour-defining cases)
def test_aggregate_builds_utc_aligned_4h_bars_and_drops_unfinished_bucket(): ...
    # 6 hourly candles from 00:00; now = 05:30 → exactly one 4h bar (00:00) with open of the first,
    # close of the fourth, max high, min low, summed volume
def test_upsert_is_idempotent_and_load_returns_sorted(tmp_path): ...
```

- [ ] **Step 2: Run** — `pytest engine/tests/test_indicators.py engine/tests/test_candles.py -q`; expected `ModuleNotFoundError`.
- [ ] **Step 3: Implement** to the interfaces.
- [ ] **Step 4: Run** — expected all pass.
- [ ] **Step 5: Commit** — `git commit -m "feat: indicators and candle storage/aggregation"`.

---

### Task 3: Strategy

**Files:**
- Create: `engine/csb/strategy.py`
- Test: `engine/tests/test_strategy.py`

**Interfaces:**
- Consumes: `indicators.*`, `models.Candle`, `models.Position`, `models.NewsView`, `models.Action`, `models.NewsState`.
- Produces:
  - `StrategyParams` (frozen dataclass, defaults): `ema_fast=50`, `ema_slow=200`, `breakout_bars=20`, `atr_period=14`, `stop_atr_mult=3.0`, `risk_per_trade=0.01`, `news_veto=-0.30`, `news_boost=0.30`, `news_boost_mult=1.25`, `min_notional=10.0`.
  - `Snapshot(ts, close, ema_fast, ema_slow, prior_high, atr)`.
  - `build_snapshots(candles, params) -> list[Snapshot | None]` (`None` during warm-up).
  - `Decision(action, reasons: list[str], size_multiplier: float, stop_price: float | None, highest_close: float | None)`.
  - `decide(snap: Snapshot, position: Position | None, news: NewsView, params: StrategyParams) -> Decision`.
  - `position_size(equity: float, atr: float, size_multiplier: float, params) -> float` (quantity; 0 when ATR ≤ 0).
  - `news_state_for(score: float | None, enabled: bool, params) -> NewsState`.

- [ ] **Step 1: Write the failing tests**

```python
UP = dict(ema_fast=110.0, ema_slow=100.0)
OFF = NewsView(NewsState.OFF, None, [])

def snap(close, prior_high=120.0, atr=2.0, **kw):
    return Snapshot(ts=0, close=close, prior_high=prior_high, atr=atr, **{**UP, **kw})

def test_enters_on_breakout_in_uptrend_with_initial_stop_three_atr_below_close():
    d = decide(snap(121.0), None, OFF, P)
    assert d.action is Action.ENTER and d.stop_price == pytest.approx(121.0 - 6.0)

def test_no_entry_when_trend_is_down_even_on_breakout():
    assert decide(snap(121.0, ema_fast=90.0), None, OFF, P).action is Action.HOLD

def test_no_entry_without_breakout():
    assert decide(snap(119.0), None, OFF, P).action is Action.HOLD

def test_bearish_news_vetoes_entry():
    d = decide(snap(121.0), None, NewsView(NewsState.VETO, -0.5, []), P)
    assert d.action is Action.HOLD and any("news" in r.lower() for r in d.reasons)

def test_bullish_news_boosts_size_but_does_not_create_entry():
    boost = NewsView(NewsState.BOOST, 0.6, [])
    assert decide(snap(121.0), None, boost, P).size_multiplier == 1.25
    assert decide(snap(119.0), None, boost, P).action is Action.HOLD

def test_bearish_news_alone_does_not_exit_a_position():
    pos = Position("BTC/USD", 1.0, 100.0, 0, stop_price=90.0, highest_close=118.0)
    assert decide(snap(119.0), pos, NewsView(NewsState.VETO, -0.9, []), P).action is Action.HOLD

def test_exits_when_close_falls_below_stop():  ...
def test_exits_when_trend_turns_down():  ...
def test_trailing_stop_ratchets_up_and_never_down():  ...
def test_position_size_risks_one_percent_at_three_atr():
    assert position_size(10_000, 2.0, 1.0, P) == pytest.approx(100 / 6.0)
def test_build_snapshots_is_none_until_slow_ema_is_seeded():  ...
```

- [ ] **Step 2: Run** — `pytest engine/tests/test_strategy.py -q`; expected `ModuleNotFoundError`.
- [ ] **Step 3: Implement** the rules in spec section 6 exactly. Exit check order: stop first, then trend. Reasons are plain sentences containing the numbers used.
- [ ] **Step 4: Run** — expected all pass.
- [ ] **Step 5: Commit** — `git commit -m "feat: trend/breakout strategy with news filter and volatility sizing"`.

---

### Task 4: Risk manager

**Files:**
- Create: `engine/csb/risk.py`
- Test: `engine/tests/test_risk.py`

**Interfaces:**
- Consumes: `models.Side`, `db`.
- Produces:
  - `RiskLimits(max_position_pct=25.0, max_open_positions=3, daily_loss_limit_pct=3.0)` with `validate()` raising `ValueError` outside 1–100, 1–20, 0.5–50.
  - `RiskState(kill_switch: bool, day: str | None, day_start_equity: float | None, halted: bool, halted_at: int | None)`.
  - `MemoryRiskStore` and `SqliteRiskStore(conn)`, both with `load_limits()`, `save_limits(limits)`, `load_state()`, `save_state(state)`.
  - `RiskDecision(approved: bool, qty: float, reason: str | None, notes: list[str])`.
  - `RiskManager(store)`: `limits` and `state` properties; `update_limits(limits)`; `set_kill_switch(engaged: bool)`; `update_equity(equity: float, now_ms: int) -> RiskState` (rolls the UTC day, trips the halt); `check_order(side, qty, price, equity, cash, open_positions, has_position, fee_rate) -> RiskDecision`.

- [ ] **Step 1: Write the failing tests**

```python
def test_kill_switch_rejects_buys_and_sells():
    rm = RiskManager(MemoryRiskStore()); rm.set_kill_switch(True)
    for side in (Side.BUY, Side.SELL):
        d = rm.check_order(side, 1, 100, equity=10_000, cash=10_000, open_positions=0, has_position=side is Side.SELL, fee_rate=0)
        assert not d.approved and "kill switch" in d.reason

def test_daily_loss_limit_halts_entries_but_allows_exits():
    rm = RiskManager(MemoryRiskStore())
    rm.update_equity(10_000, DAY1)
    rm.update_equity(9_690, DAY1 + 60_000)            # −3.1%
    assert rm.state.halted
    assert not rm.check_order(Side.BUY, 1, 100, 9_690, 9_690, 0, False, 0).approved
    assert rm.check_order(Side.SELL, 1, 100, 9_690, 0, 1, True, 0).approved

def test_halt_clears_on_next_utc_day():  ...
def test_entry_is_clamped_to_max_position_size():
    d = RiskManager(MemoryRiskStore()).check_order(Side.BUY, 100, 100, 10_000, 10_000, 0, False, 0)
    assert d.approved and d.qty == pytest.approx(25.0)   # 25% of 10k at price 100
def test_entry_is_clamped_to_available_cash_including_fee():  ...
def test_entry_rejected_at_max_open_positions():  ...
def test_limits_kill_switch_and_halt_survive_restart(tmp_path):
    # set limits + kill switch + trip halt with SqliteRiskStore, close the connection,
    # reopen the same file with a new RiskManager, assert all three persisted
def test_invalid_limits_are_rejected():  ...
```

- [ ] **Step 2: Run** — `pytest engine/tests/test_risk.py -q`; expected `ModuleNotFoundError`.
- [ ] **Step 3: Implement.** Check order: kill switch → (BUY only) halted → has_position → max open positions → clamp to max position → clamp to cash. SELL passes after the kill-switch check. Every state change is saved through the store immediately.
- [ ] **Step 4: Run** — expected all pass.
- [ ] **Step 5: Commit** — `git commit -m "feat: persisted risk limits, daily loss halt and kill switch"`.

---

### Task 5: Paper broker, portfolio ledger and order router

**Files:**
- Create: `engine/csb/broker.py`, `engine/csb/portfolio.py`, `engine/csb/execution.py`
- Test: `engine/tests/test_broker.py`, `engine/tests/test_portfolio.py`, `engine/tests/test_execution.py`

**Interfaces:**
- Consumes: `models.*`, `risk.RiskManager`.
- Produces:
  - `broker.Broker` (Protocol): `name: str`; `market_order(symbol, side, qty, quote: Quote, ts_ms) -> Fill`.
  - `broker.PaperBroker(fee_bps: float, slippage_bps: float)`, `name = "paper"`.
  - `portfolio.Portfolio(cash, starting_cash, positions: dict[str, Position], realized_pnl=0.0, fees_paid=0.0)`: `apply_fill(fill, stop_price=None) -> float | None` (realised P&L for sells, net of both fees), `equity(prices: Mapping[str, float]) -> float`.
  - `portfolio.load_portfolio(conn, starting_cash) -> Portfolio`, `portfolio.save_portfolio(conn, portfolio) -> None`.
  - `execution.OrderResult(status: "filled" | "rejected", fill: Fill | None, reason: str | None, realized_pnl: float | None, requested_qty, qty)`.
  - `execution.OrderRouter(risk, broker, portfolio, fee_bps, recorder=None)`: `submit(request: OrderRequest, quote: Quote, equity: float, ts_ms: int, stop_price: float | None = None) -> OrderResult`. `recorder(request, result, quote, ts_ms)` is called for every submission.

- [ ] **Step 1: Write the failing tests**

```python
def test_paper_buy_fills_at_ask_plus_slippage_and_charges_fee():
    f = PaperBroker(fee_bps=40, slippage_bps=5).market_order("BTC/USD", Side.BUY, 0.5, Quote("BTC/USD", 99, 101, 100, 0), 0)
    assert f.price == pytest.approx(101 * 1.0005)
    assert f.fee == pytest.approx(0.5 * 101 * 1.0005 * 0.004)

def test_paper_sell_fills_at_bid_minus_slippage():  ...
def test_paper_falls_back_to_last_when_bid_ask_missing():  ...
def test_round_trip_realised_pnl_is_net_of_both_fees():  ...
def test_equity_marks_positions_at_given_prices():  ...
def test_portfolio_round_trips_through_sqlite(tmp_path):  ...
def test_router_does_not_call_broker_when_risk_rejects():
    broker = RecordingBroker(); rm = RiskManager(MemoryRiskStore()); rm.set_kill_switch(True)
    res = OrderRouter(rm, broker, pf, fee_bps=40).submit(OrderRequest("BTC/USD", Side.BUY, 1), QUOTE, 10_000, 0)
    assert res.status == "rejected" and broker.calls == [] and pf.cash == 10_000
def test_router_applies_fill_to_portfolio_and_reports_clamped_qty():  ...
def test_router_rejects_sell_without_position():  ...
```

- [ ] **Step 2: Run** — expected `ModuleNotFoundError`.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** — expected all pass.
- [ ] **Step 5: Commit** — `git commit -m "feat: paper broker, portfolio ledger and risk-gated order router"`.

---

### Task 6: Backtester

**Files:**
- Create: `engine/csb/backtest.py`
- Test: `engine/tests/test_backtest.py`

**Interfaces:**
- Consumes: `strategy.*`, `risk.RiskManager`, `risk.MemoryRiskStore`, `portfolio.Portfolio`, `broker.PaperBroker`, `execution.OrderRouter`.
- Produces:
  - `run_backtest(bars_by_symbol: Mapping[str, Sequence[Candle]], params: StrategyParams, limits: RiskLimits, starting_cash: float, fee_bps: float, slippage_bps: float) -> BacktestResult`.
  - `BacktestResult` dataclass with `to_dict()`: `data_start`, `period_start`, `period_end`, `bars`, `symbols`, `starting_cash`, `final_equity`, `total_return_pct`, `max_drawdown_pct`, `trades` (closed count), `wins`, `win_rate_pct`, `profit_factor`, `total_fees`, `buy_hold_return_pct`, `open_positions`, `trade_list`, `equity_curve`, `fee_bps`, `slippage_bps`, `news_included = False`.

- [ ] **Step 1: Write the failing tests** (synthetic bars built by helpers; small `StrategyParams` such as `ema_fast=3, ema_slow=6, breakout_bars=3, atr_period=3` so cases stay readable)

```python
def test_fills_at_next_bar_open_not_signal_bar_close():
    # rising series that breaks out on bar k; assert first trade entry_ts == bars[k+1].ts
    # and entry_price == bars[k+1].open * (1 + slippage)
def test_fees_and_slippage_reduce_return():
    free = run_backtest(BARS, P, LIMITS, 10_000, fee_bps=0, slippage_bps=0)
    paid = run_backtest(BARS, P, LIMITS, 10_000, fee_bps=40, slippage_bps=5)
    assert paid.final_equity < free.final_equity and paid.total_fees > 0
def test_flat_market_makes_no_trades_and_zero_return():  ...
def test_max_drawdown_is_peak_to_trough_of_equity_curve():  ...
def test_signal_on_last_bar_is_not_executed():  ...
def test_result_is_marked_price_only():
    assert run_backtest(BARS, P, LIMITS, 10_000, 40, 5).news_included is False
def test_max_open_positions_limit_applies_in_backtest():  ...
```

- [ ] **Step 2: Run** — expected `ModuleNotFoundError`.
- [ ] **Step 3: Implement** per spec section 7: precompute snapshots per symbol; walk the sorted union of timestamps; at each timestamp fill pending orders at the open (exits first), mark equity at the close, call `risk.update_equity`, decide, queue orders.
- [ ] **Step 4: Run** — expected all pass.
- [ ] **Step 5: Commit** — `git commit -m "feat: backtester with fees, slippage and next-open fills"`.

---

### Task 7: Market data (ccxt wrapper)

**Files:**
- Create: `engine/csb/marketdata.py`
- Test: `engine/tests/test_marketdata.py`

**Interfaces:**
- Consumes: `candles.*`, `models.Quote`.
- Produces:
  - `marketdata.create_exchange(exchange_id: str)` → ccxt instance with `enableRateLimit=True`, no credentials.
  - `MarketData(exchange, exchange_id: str, conn, clock=now_ms)`: `backfill(symbol, days, progress=None) -> int`, `update(symbol) -> int`, `quote(symbol) -> Quote`.

- [ ] **Step 1: Write the failing tests** with a `FakeExchange` exposing `fetch_ohlcv(symbol, timeframe, since, limit)` and `fetch_ticker(symbol)`:

```python
def test_backfill_pages_until_present_and_stores_only_closed_candles():  ...
def test_backfill_stops_when_exchange_ignores_since():      # Kraken-style: always returns the same latest page
def test_update_fetches_only_after_latest_stored_ts():  ...
def test_quote_maps_ticker_fields():  ...
```

- [ ] **Step 2: Run** — expected `ModuleNotFoundError`.
- [ ] **Step 3: Implement.** Page size 300. Advance `since` to `last_ts + HOUR_MS`; stop when a page adds no candle newer than the previous page or `since` passes now.
- [ ] **Step 4: Run** — expected all pass.
- [ ] **Step 5: Commit** — `git commit -m "feat: exchange-agnostic market data via ccxt"`.

---

### Task 8: News feeds, scoring and store

**Files:**
- Create: `engine/csb/news_feeds.py`, `engine/csb/news_scoring.py`, `engine/csb/news_store.py`
- Test: `engine/tests/test_news_feeds.py`, `engine/tests/test_news_scoring.py`, `engine/tests/test_news_store.py`

**Interfaces:**
- Consumes: `models.Headline`, `models.HeadlineScore`, `models.NewsView`, `config.Settings`.
- Produces:
  - `news_feeds.FEEDS: tuple[Feed, ...]` (`Feed(name, kind, url)`), `parse_feed(feed, content: bytes) -> list[Headline]`, `fetch_feeds(client: httpx.Client, feeds=FEEDS) -> list[FeedResult]` (`FeedResult(feed, headlines, error)`).
  - `news_scoring.Scorer` (Protocol): `provider: str`, `model: str`, `score(headlines: Sequence[tuple[int, str]], coins: Sequence[str]) -> dict[int, list[HeadlineScore]]`.
  - `news_scoring.build_prompt(headlines, coins) -> str`, `parse_scores(text, ids, coins) -> dict[int, list[HeadlineScore]]` (raises `ScoringError` on invalid JSON or shape).
  - `news_scoring.OpenAIScorer(api_key, model, client=None)`, `AnthropicScorer(api_key, model, client=None)`.
  - `news_scoring.build_scorer(settings) -> tuple[Scorer | None, str | None]` (scorer or the reason scoring is off).
  - `news_store.save_headlines(conn, headlines, now_ms) -> int`, `record_source(conn, feed, ok, error, count, now_ms)`, `pending_headlines(conn, now_ms, max_age_ms, limit) -> list[tuple[int, str]]`, `save_scores(conn, scores, provider, model, now_ms)`, `mark_error(conn, ids, error)`, `news_view(conn, coin, now_ms, enabled, params) -> NewsView`.

- [ ] **Step 1: Write the failing tests**

```python
def test_parse_feed_extracts_title_url_and_utc_published_time():  ...      # inline RSS fixture
def test_fetch_feeds_reports_failure_per_source_without_stopping():  ...   # httpx.MockTransport: one 200, one 403
def test_parse_scores_clamps_ranges_and_drops_unknown_coins():  ...
def test_parse_scores_rejects_non_json():  ...
def test_openai_scorer_sends_bearer_key_and_parses_response():  ...        # httpx.MockTransport
def test_anthropic_scorer_sends_x_api_key_and_parses_response():  ...     # httpx.MockTransport
def test_build_scorer_is_off_without_key_and_says_why():
    scorer, reason = build_scorer(load_settings({}))
    assert scorer is None and "OPENAI_API_KEY" in reason
def test_news_view_off_when_scoring_disabled():  ...
def test_news_view_weights_by_confidence_and_recency():  ...
def test_single_weak_headline_cannot_produce_extreme_score():  ...
def test_save_headlines_dedupes_by_url():  ...
```

- [ ] **Step 2: Run** — expected `ModuleNotFoundError`.
- [ ] **Step 3: Implement** per spec section 5.
- [ ] **Step 4: Run** — expected all pass.
- [ ] **Step 5: Commit** — `git commit -m "feat: news feeds, LLM headline scoring and per-coin news score"`.

---

### Task 9: Trading service

**Files:**
- Create: `engine/csb/service.py`
- Test: `engine/tests/test_service.py`

**Interfaces:**
- Consumes: everything from Tasks 1–8.
- Produces: `TradingService(settings, conn, market, scorer, scorer_reason, http_client=None, clock=now_ms, feeds=FEEDS)` with `run_cycle() -> dict` (the cycle summary), `run_forever(stop: threading.Event) -> None`, `news_status() -> dict`.

- [ ] **Step 1: Write the failing tests** (fake `MarketData`-compatible object fed with synthetic candles; stub scorer)

```python
def test_cycle_records_signal_and_fills_entry_at_live_quote():  ...
def test_bar_is_evaluated_once_across_cycles():  ...
def test_kill_switch_stops_all_orders_but_signals_still_recorded():
    # arrange an entry signal, engage kill switch, run cycle →
    # one signal row, one order row with status "rejected" and reason containing "kill switch", no position
def test_daily_loss_halt_rejects_entry():  ...
def test_stale_bar_is_not_evaluated():  ...
def test_news_veto_from_stub_scorer_blocks_entry_and_links_headlines():  ...
def test_without_scorer_headlines_stay_unscored_and_news_state_is_off():  ...
def test_cycle_error_is_recorded_and_raised_summary_has_status_error():  ...
```

- [ ] **Step 2: Run** — expected `ModuleNotFoundError`.
- [ ] **Step 3: Implement** per spec section 13.
- [ ] **Step 4: Run** — expected all pass.
- [ ] **Step 5: Commit** — `git commit -m "feat: trading cycle service"`.

---

### Task 10: CLI

**Files:**
- Create: `engine/csb/cli.py`, `engine/csb/__main__.py`
- Test: `engine/tests/test_cli.py`

**Interfaces:**
- Produces: `cli.main(argv: list[str] | None = None) -> int` with subcommands `backfill [--days N]`, `backtest`, `news`, `cycle`, `serve`. `cli.run_stored_backtest(settings, conn) -> dict` (aggregates stored candles, runs, stores a `backtest_runs` row, returns it).

- [ ] **Step 1: Failing test** — `test_run_stored_backtest_persists_a_run_from_stored_candles(tmp_path)` inserts hourly candles, calls `run_stored_backtest`, asserts a row exists and `result["news_included"] is False`.
- [ ] **Step 2: Run** — expected `ModuleNotFoundError`.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** — expected pass.
- [ ] **Step 5: Commit** — `git commit -m "feat: CLI for backfill, backtest, news, cycle and serve"`.

---

### Task 11: Local API

**Files:**
- Create: `engine/csb/api.py`
- Test: `engine/tests/test_api.py`

**Interfaces:**
- Produces: `api.create_app(settings: Settings, start_loop: bool = True, service_factory=None) -> FastAPI`. Routes and shapes exactly as spec section 10 and `dashboard/src/lib/types.ts` (Task 13).

- [ ] **Step 1: Write the failing tests** (FastAPI `TestClient`, `start_loop=False`, temp database)

```python
def test_status_reports_paper_mode_and_live_trading_unavailable():
    body = client.get("/api/status").json()
    assert body["mode"] == "paper" and body["live_trading"]["available"] is False

def test_status_reports_scoring_off_without_key():
    ns = client.get("/api/status").json()["news_scoring"]
    assert ns["enabled"] is False and "OPENAI_API_KEY" in ns["reason"]

def test_kill_switch_round_trip_and_persists():  ...
def test_put_risk_validates_ranges():           # 422 for max_position_pct=0
def test_rejects_foreign_host_header():         # Host: evil.example → 400
def test_no_route_places_orders():
    paths = {r.path for r in app.routes}
    assert not any("order" in p for p in paths)
def test_news_endpoint_marks_headlines_unscored():  ...
def test_backtest_latest_is_null_before_any_run():  ...
```

- [ ] **Step 2: Run** — expected `ModuleNotFoundError`.
- [ ] **Step 3: Implement.** `TrustedHostMiddleware(allowed_hosts=["127.0.0.1", "localhost", "testserver"])`, `CORSMiddleware(allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"])`. Each request opens its own SQLite connection. The loop thread is started in the lifespan handler and stopped on shutdown.
- [ ] **Step 4: Run** — full suite `pytest engine -q` and `ruff check engine`; expected all pass, no lint errors.
- [ ] **Step 5: Commit** — `git commit -m "feat: local FastAPI for dashboard"`.

---

### Task 12: Real-data verification of the engine

- [ ] `python -m csb backfill` — expect two years of 1h candles per symbol from the default exchange.
- [ ] `python -m csb backtest` — record period, trades, return after fees, max drawdown exactly as printed. Do not change strategy constants afterwards.
- [ ] `python -m csb news` — expect headlines from each source; note failures.
- [ ] `python -m csb cycle` — one full cycle against live prices; expect `status: ok`.
- [ ] Commit any fixes with tests that reproduce the defect first.

---

### Task 13: Dashboard foundation

**Files:**
- Create (scaffold): `dashboard/` via `create-next-app` (TypeScript, Tailwind, ESLint, App Router, `src/`), shadcn init, components `button card table badge alert separator skeleton tooltip input label switch alert-dialog chart sonner empty field`.
- Create: `dashboard/src/lib/types.ts` (API contract), `dashboard/src/lib/api.ts` (`ENGINE_URL`, `fetcher`, `putRisk`, `setKillSwitch`, `runBacktest`), `dashboard/src/lib/format.ts` (`usd`, `pct`, `qty`, `timeUtc`, `ago`), `dashboard/src/app/globals.css` (tokens), `dashboard/src/app/layout.tsx`, `dashboard/src/components/desk-shell.tsx`, `status-bar.tsx`, `engine-offline.tsx`.
- Modify: `dashboard/package.json` scripts: `"dev": "next dev -H 127.0.0.1 -p 3000"`, `"start": "next start -H 127.0.0.1 -p 3000"`, `"typecheck": "tsc --noEmit"`.

**Interfaces:**
- Consumes: API from Task 11.
- Produces: `types.ts` exports `Status`, `Portfolio`, `PositionRow`, `EquityPoint`, `SignalRow`, `OrderRow`, `NewsResponse`, `HeadlineRow`, `BacktestRun`, `BacktestResult`, `RiskResponse`, `RiskLimits`; hook `useEngine<T>(path, refreshMs)` returning `{ data, error, isLoading, mutate }`.

- [ ] Scaffold, add tokens (background near-black, amber accent, gain green, loss red; IBM Plex Sans + IBM Plex Mono via `next/font`), shell with left rail and status bar.
- [ ] Verify: `npm run typecheck`, `npm run lint`, `npm run build` all exit 0 through the junction.
- [ ] Commit — `git commit -m "feat(dashboard): shell, tokens and API client"`.

---

### Task 14: Dashboard views

**Files:**
- Create: `dashboard/src/app/page.tsx` (Desk), `signals/page.tsx`, `trades/page.tsx`, `news/page.tsx`, `backtest/page.tsx`, `settings/page.tsx`, and components `kpi.tsx`, `positions-table.tsx`, `watchlist.tsx`, `equity-chart.tsx`, `signal-list.tsx`, `orders-table.tsx`, `headline-list.tsx`, `backtest-report.tsx`, `risk-form.tsx`, `kill-switch.tsx`, `live-trading-notice.tsx`.

Requirements checked per view:
- Every view handles loading, engine-offline and empty states without invented numbers.
- `/backtest` and the Desk backtest summary show "Price rules only — news scoring is not part of this backtest".
- News views show "Scoring off — no LLM API key configured" and label headlines `unscored` when disabled.
- `/settings` shows live trading as not available in phase 1; the kill switch needs a confirmation dialog to engage.
- Switches over `action`, `status`, `news.state` end in a `never` check.

- [ ] Build each view, then `npm run typecheck && npm run lint && npm run build`.
- [ ] Commit — `git commit -m "feat(dashboard): desk, signals, trades, news, backtest and settings views"`.

---

### Task 15: CI, README and end-to-end verification

**Files:**
- Create: `.github/workflows/ci.yml`, `README.md`, `docs/screenshots/*.png`

- [ ] CI: job `engine` (Python 3.12: `pip install -r engine/requirements-dev.txt`, `ruff check engine`, `pytest engine`), job `dashboard` (Node 22: `npm ci`, `npm run typecheck`, `npm run lint`, `npm run build`).
- [ ] Start the engine (`python -m csb serve`) and the dashboard (`npm run start`); confirm a full paper cycle; load each route in a browser and save screenshots to `docs/screenshots/`.
- [ ] Controlled run: engage the kill switch through the API and confirm the next entry is rejected; trip the daily loss limit in the automated tests.
- [ ] README: status, Windows install and run, what works, what does not (live trading, news backtesting), no live URL, CI not yet run because the project is not pushed. Only verified claims.
- [ ] Stop all servers. Final `pytest`, `ruff`, `typecheck`, `lint`, `build`. Commit — `git commit -m "docs: README, CI workflow and verification screenshots"`.

## Self-Review

- **Spec coverage:** market data → Tasks 2, 7; news → Task 8; strategy → Task 3; backtester → Tasks 6, 10; executor → Task 5; risk → Task 4; cycle → Task 9; API → Task 11; dashboard → Tasks 13, 14; configuration → Task 1; testing and verification → Tasks 12, 15. No section of the spec is without a task.
- **Placeholders:** test bodies marked `...` are named behaviours with the assertion described in the name or comment; implementation bodies are intentionally not reproduced (see the format note).
- **Type consistency:** `Quote`, `Fill`, `Position`, `NewsView`, `RiskDecision`, `OrderResult` and `BacktestResult` are named once in the task that produces them and used with the same names in Tasks 5, 6, 9, 10 and 11.
