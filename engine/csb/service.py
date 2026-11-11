"""The trading cycle: data in, decisions out, orders through the risk-gated router. Paper only."""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx

from csb.broker import PaperBroker
from csb.candles import BASE_TIMEFRAME, HOUR_MS, SIGNAL_HOURS, aggregate, latest_ts, load_candles
from csb.config import Settings
from csb.db import get_meta, init_schema, now_ms, set_meta
from csb.execution import OrderResult, OrderRouter
from csb.models import Action, NewsView, OrderRequest, Quote, Side
from csb.news_feeds import FEEDS, Feed, fetch_feeds, new_http_client
from csb.news_scoring import Scorer, ScoringError
from csb.news_store import mark_error, news_view, pending_headlines, record_source, save_headlines, save_scores
from csb.portfolio import load_portfolio, save_portfolio
from csb.risk import RiskManager, SqliteRiskStore
from csb.strategy import Decision, Snapshot, StrategyParams, build_snapshots, decide, position_size

log = logging.getLogger("csb.service")

BAR_MS = SIGNAL_HOURS * HOUR_MS
SCORE_MAX_AGE_MS = 48 * HOUR_MS
SCORE_BATCH = 20
SCORE_LIMIT_PER_REFRESH = 60
META_SCORING_ERROR = "news_scoring_last_error"


def scoring_status(
    conn: sqlite3.Connection, settings: Settings, scorer: Scorer | None, reason: str | None
) -> dict[str, Any]:
    """Whether headline scoring is on, and if not, why. Shown as-is in the dashboard."""
    return {
        "enabled": scorer is not None,
        "provider": settings.llm_provider,
        "model": scorer.model if scorer is not None else None,
        "reason": reason,
        "last_error": get_meta(conn, META_SCORING_ERROR) or None,
    }


def _utc(ts_ms: int) -> str:
    return datetime.fromtimestamp(ts_ms / 1000, tz=UTC).strftime("%Y-%m-%d %H:%M UTC")


@dataclass
class _Evaluation:
    symbol: str
    snap: Snapshot
    decision: Decision
    signal_id: int


class TradingService:
    def __init__(
        self,
        settings: Settings,
        conn: sqlite3.Connection,
        market: Any,
        scorer: Scorer | None,
        scorer_reason: str | None,
        http_client: httpx.Client | None = None,
        clock: Callable[[], int] = now_ms,
        feeds: Sequence[Feed] = FEEDS,
        params: StrategyParams | None = None,
    ) -> None:
        init_schema(conn)
        self._settings = settings
        self._conn = conn
        self._market = market
        self._scorer = scorer
        self._scorer_reason = scorer_reason
        self._http = http_client
        self._clock = clock
        self._feeds = tuple(feeds)
        self._params = params or StrategyParams()
        self._risk = RiskManager(SqliteRiskStore(conn))
        self._broker = PaperBroker(settings.fee_bps, settings.slippage_bps)
        self._last_news_fetch: int | None = None

    # ------------------------------------------------------------------ loop

    def run_forever(self, stop: threading.Event) -> None:
        while not stop.is_set():
            summary = self.run_cycle()
            if summary["status"] != "ok":
                log.error("cycle %s failed: %s", summary["id"], summary["error"])
            stop.wait(self._settings.cycle_seconds)

    def run_cycle(self) -> dict[str, Any]:
        """One full cycle. Never raises: a failure is recorded on the cycle row and returned."""
        started = self._clock()
        cursor = self._conn.execute("insert into cycles (started_at, status) values (?, 'running')", (started,))
        self._conn.commit()
        cycle_id = cursor.lastrowid
        summary: dict[str, Any] = {"candles_added": {}, "news": None, "signals": [], "orders": [], "skipped": []}
        status, error = "ok", None
        try:
            self._cycle(started, summary)
        except Exception as exc:  # noqa: BLE001 - the loop must survive any single failed cycle
            self._conn.rollback()
            status, error = "error", f"{type(exc).__name__}: {exc}"[:500]
            log.exception("cycle failed")
        finished = max(self._clock(), started)
        self._conn.execute(
            "update cycles set finished_at = ?, status = ?, error = ?, summary = ? where id = ?",
            (finished, status, error, json.dumps(summary), cycle_id),
        )
        self._conn.commit()
        return {
            "id": cycle_id,
            "started_at": started,
            "finished_at": finished,
            "status": status,
            "error": error,
            **summary,
        }

    # ----------------------------------------------------------------- steps

    def _cycle(self, now: int, summary: dict[str, Any]) -> None:
        symbols = self._settings.symbols
        for symbol in symbols:
            summary["candles_added"][symbol] = self._market.update(symbol)

        if self._last_news_fetch is None or now - self._last_news_fetch >= self._settings.news_refresh_seconds * 1000:
            summary["news"] = self._refresh_news(now)

        quotes = {symbol: self._market.quote(symbol) for symbol in symbols}
        self._save_quotes(quotes)

        portfolio = load_portfolio(self._conn, self._settings.starting_cash)
        equity = portfolio.equity({symbol: quote.last for symbol, quote in quotes.items()})
        self._risk.update_equity(equity, now)
        self._conn.execute(
            "insert or replace into equity_snapshots (ts, equity, cash) values (?, ?, ?)",
            (now, equity, portfolio.cash),
        )

        evaluations: list[_Evaluation] = []
        for symbol in symbols:
            evaluation = self._evaluate(symbol, now, portfolio.positions.get(symbol), summary)
            if evaluation is not None:
                evaluations.append(evaluation)

        router = OrderRouter(
            self._risk,
            self._broker,
            portfolio,
            self._settings.fee_bps,
            self._settings.slippage_bps,
            recorder=lambda request, result, ts: self._record_order(request, result, ts, summary),
        )
        # Exits first so they free cash and position slots, then entries in configured symbol order.
        for ev in evaluations:
            position = portfolio.positions.get(ev.symbol)
            if position is None:
                continue
            if ev.decision.action is Action.EXIT:
                router.submit(
                    OrderRequest(ev.symbol, Side.SELL, position.qty, ev.signal_id), quotes[ev.symbol], equity, now
                )
            elif ev.decision.stop_price is not None and ev.decision.highest_close is not None:
                position.stop_price = ev.decision.stop_price
                position.highest_close = ev.decision.highest_close
        for ev in evaluations:
            if ev.decision.action is not Action.ENTER:
                continue
            qty = position_size(equity, ev.snap.atr, ev.decision.size_multiplier, self._params)
            if qty <= 0:
                continue
            router.submit(
                OrderRequest(ev.symbol, Side.BUY, qty, ev.signal_id),
                quotes[ev.symbol],
                equity,
                now,
                stop_price=ev.decision.stop_price,
                highest_close=ev.decision.highest_close,
            )
        save_portfolio(self._conn, portfolio)

    def _evaluate(self, symbol: str, now: int, position: Any, summary: dict[str, Any]) -> _Evaluation | None:
        """Evaluate the newest closed 4h bar once. Returns None when there is nothing new or data is behind."""
        bucket = now - now % BAR_MS - BAR_MS  # start of the newest 4h bucket that has fully elapsed
        meta_key = f"last_eval:{symbol}"
        if get_meta(self._conn, meta_key) == str(bucket):
            return None

        final_hour = bucket + BAR_MS - HOUR_MS
        newest = latest_ts(self._conn, self._market.exchange_id, symbol, BASE_TIMEFRAME)
        if newest is None or newest < final_hour:
            summary["skipped"].append(
                f"{symbol}: market data is behind; waiting for the hourly candle of {_utc(final_hour)} "
                f"(newest stored: {_utc(newest) if newest is not None else 'none'})."
            )
            return None

        hourly = load_candles(self._conn, self._market.exchange_id, symbol, BASE_TIMEFRAME)
        bars = [bar for bar in aggregate(hourly, SIGNAL_HOURS, now) if bar.ts <= bucket]
        snap = build_snapshots(bars, self._params)[-1]
        news = news_view(self._conn, symbol.split("/")[0], now, self._scorer is not None, self._params)
        if snap is None:
            reason = (
                f"Warming up: {len(bars)} four-hour bars stored, more than {self._params.ema_slow} are needed "
                "before the indicators are complete. No trading until then."
            )
            self._record_signal(symbol, bucket, now, Action.HOLD, [reason], {}, news, 1.0)
            set_meta(self._conn, meta_key, str(bucket))
            summary["signals"].append({"symbol": symbol, "action": "hold"})
            return None

        decision = decide(snap, position, news, self._params)
        indicators = {
            "close": snap.close,
            "ema_fast": snap.ema_fast,
            "ema_slow": snap.ema_slow,
            "prior_high": snap.prior_high,
            "atr": snap.atr,
            "stop": decision.stop_price,
        }
        signal_id = self._record_signal(
            symbol, bucket, now, decision.action, decision.reasons, indicators, news, decision.size_multiplier
        )
        set_meta(self._conn, meta_key, str(bucket))
        summary["signals"].append({"symbol": symbol, "action": decision.action.value})
        return _Evaluation(symbol, snap, decision, signal_id)

    # ------------------------------------------------------------------ news

    def _refresh_news(self, now: int) -> dict[str, Any]:
        if self._http is None:
            self._http = new_http_client()
        results = fetch_feeds(self._http, self._feeds)
        new = 0
        for result in results:
            record_source(self._conn, result.feed, result.error is None, result.error, len(result.headlines), now)
            new += save_headlines(self._conn, result.headlines, now)
        self._last_news_fetch = now
        out: dict[str, Any] = {
            "fetched": sum(len(r.headlines) for r in results),
            "new": new,
            "failed_sources": [r.feed.name for r in results if r.error is not None],
            "scoring": "off",
            "scored": 0,
        }
        if self._scorer is not None:
            out.update(self._score_pending(now))
        return out

    def _score_pending(self, now: int) -> dict[str, Any]:
        assert self._scorer is not None
        pending = pending_headlines(self._conn, now, SCORE_MAX_AGE_MS, SCORE_LIMIT_PER_REFRESH)
        scored, failed = 0, 0
        last_error: str | None = None
        for start in range(0, len(pending), SCORE_BATCH):
            batch = pending[start : start + SCORE_BATCH]
            ids = [news_id for news_id, _ in batch]
            try:
                scores = self._scorer.score(batch, self._settings.coins)
            except ScoringError as exc:
                last_error = str(exc)
                mark_error(self._conn, ids, last_error)
                failed += len(batch)
                continue
            save_scores(self._conn, scores, self._scorer.provider, self._scorer.model, now)
            scored += len(batch)
        if pending:
            set_meta(self._conn, META_SCORING_ERROR, last_error or "")
            self._conn.commit()
        return {"scoring": "on", "scored": scored, "scoring_failed": failed}

    # --------------------------------------------------------------- records

    def _save_quotes(self, quotes: dict[str, Quote]) -> None:
        self._conn.executemany(
            "insert or replace into quotes (symbol, bid, ask, last, ts) values (?, ?, ?, ?, ?)",
            [(q.symbol, q.bid, q.ask, q.last, q.ts) for q in quotes.values()],
        )

    def _record_signal(
        self,
        symbol: str,
        bar_ts: int,
        now: int,
        action: Action,
        reasons: list[str],
        indicators: dict[str, Any],
        news: NewsView,
        size_multiplier: float,
    ) -> int:
        cursor = self._conn.execute(
            "insert into signals (ts, created_at, symbol, action, reasons, indicators, news_state, news_score,"
            " news_ids, size_multiplier) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                bar_ts,
                now,
                symbol,
                action.value,
                json.dumps(reasons),
                json.dumps(indicators),
                news.state.value,
                news.score,
                json.dumps([h.id for h in news.headlines]),
                size_multiplier,
            ),
        )
        return int(cursor.lastrowid)

    def _record_order(self, request: OrderRequest, result: OrderResult, ts: int, summary: dict[str, Any]) -> None:
        fill = result.fill
        self._conn.execute(
            "insert into orders (created_at, symbol, side, requested_qty, qty, ref_price, status, reject_reason,"
            " notes, fill_price, fee, realized_pnl, signal_id, broker)"
            " values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                ts,
                request.symbol,
                request.side.value,
                result.requested_qty,
                result.qty,
                result.ref_price,
                result.status,
                result.reason,
                json.dumps(result.notes),
                fill.price if fill else None,
                fill.fee if fill else None,
                result.realized_pnl,
                request.signal_id,
                self._broker.name,
            ),
        )
        summary["orders"].append(
            {"symbol": request.symbol, "side": request.side.value, "status": result.status, "reason": result.reason}
        )
