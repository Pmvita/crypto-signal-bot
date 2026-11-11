"""Local FastAPI for the dashboard. Paper mode only; no order-placement routes."""

from __future__ import annotations

import json
import logging
import threading
from collections.abc import Callable, Generator
from contextlib import asynccontextmanager
from dataclasses import asdict
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from csb.candles import BASE_TIMEFRAME, SIGNAL_HOURS, aggregate, load_candles
from csb.config import API_HOST, Settings
from csb.db import connect, init_schema, now_ms
from csb.jobs import candle_history_summary, run_backfill, run_stored_backtest
from csb.marketdata import MarketData, create_exchange
from csb.news_scoring import build_scorer
from csb.portfolio import load_portfolio
from csb.risk import RiskLimits, SqliteRiskStore
from csb.service import TradingService, scoring_status
from csb.strategy import StrategyParams, build_snapshots

log = logging.getLogger("csb.api")

ServiceFactory = Callable[[Settings, Any], TradingService]


class RiskUpdate(BaseModel):
    max_position_pct: float = Field(..., ge=1, le=100)
    max_open_positions: int = Field(..., ge=1, le=20)
    daily_loss_limit_pct: float = Field(..., ge=0.5, le=50)


class KillSwitchBody(BaseModel):
    engaged: bool


class BackfillBody(BaseModel):
    days: int | None = Field(None, ge=1, le=3000)


def default_service_factory(settings: Settings, conn: Any) -> TradingService:
    scorer, reason = build_scorer(settings)
    market = MarketData(create_exchange(settings.exchange), settings.exchange, conn)
    return TradingService(settings, conn, market, scorer, reason)


def create_app(
    settings: Settings,
    start_loop: bool = True,
    service_factory: ServiceFactory | None = None,
) -> FastAPI:
    factory = service_factory or default_service_factory
    stop = threading.Event()
    loop_thread: threading.Thread | None = None
    # Shared connection used only by the background trading loop.
    loop_conn = connect(settings.db_path)
    init_schema(loop_conn)
    service = factory(settings, loop_conn)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> Generator[None, None, None]:
        nonlocal loop_thread
        if start_loop:
            loop_thread = threading.Thread(
                target=service.run_forever,
                args=(stop,),
                name="csb-trading-loop",
                daemon=True,
            )
            loop_thread.start()
            log.info("paper trading loop started")
        yield
        stop.set()
        if loop_thread is not None:
            loop_thread.join(timeout=settings.cycle_seconds + 5)
        loop_conn.close()

    app = FastAPI(title="Crypto Signal Bot", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["127.0.0.1", "localhost", "testserver"],
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def open_conn():
        conn = connect(settings.db_path)
        init_schema(conn)
        return conn

    def latest_cycle(conn) -> dict[str, Any] | None:
        row = conn.execute(
            "select id, started_at, finished_at, status, error from cycles order by id desc limit 1"
        ).fetchone()
        if row is None:
            return None
        return {
            "id": row["id"],
            "started_at": row["started_at"],
            "finished_at": row["finished_at"],
            "status": row["status"],
            "error": row["error"],
        }

    def risk_payload(conn) -> dict[str, Any]:
        store = SqliteRiskStore(conn)
        limits = store.load_limits()
        state = store.load_state()
        return {
            "limits": asdict(limits),
            "kill_switch": state.kill_switch,
            "day": state.day,
            "day_start_equity": state.day_start_equity,
            "halted": state.halted,
            "halted_at": state.halted_at,
        }

    @app.get("/api/status")
    def status() -> dict[str, Any]:
        conn = open_conn()
        try:
            scorer, reason = build_scorer(settings)
            return {
                "mode": "paper",
                "live_trading": {
                    "available": False,
                    "reason": "Live trading is not available in phase 1.",
                },
                "exchange": settings.exchange,
                "symbols": list(settings.symbols),
                "heartbeat": latest_cycle(conn),
                "news_scoring": scoring_status(conn, settings, scorer, reason),
                "risk": risk_payload(conn),
                "server_time": now_ms(),
            }
        finally:
            conn.close()

    @app.get("/api/portfolio")
    def portfolio() -> dict[str, Any]:
        conn = open_conn()
        try:
            pf = load_portfolio(conn, settings.starting_cash)
            quotes = {
                r["symbol"]: {"bid": r["bid"], "ask": r["ask"], "last": r["last"], "ts": r["ts"]}
                for r in conn.execute("select * from quotes").fetchall()
            }
            prices = {symbol: quotes[symbol]["last"] for symbol in pf.positions if symbol in quotes}
            # Positions without a quote are valued at entry so equity stays defined.
            for symbol, pos in pf.positions.items():
                prices.setdefault(symbol, pos.entry_price)
            equity = pf.equity(prices) if prices or not pf.positions else pf.cash
            day_pnl = None
            risk = risk_payload(conn)
            if risk["day_start_equity"] is not None:
                day_pnl = equity - risk["day_start_equity"]
            positions = []
            for symbol, pos in pf.positions.items():
                last = prices.get(symbol, pos.entry_price)
                positions.append(
                    {
                        "symbol": symbol,
                        "qty": pos.qty,
                        "entry_price": pos.entry_price,
                        "entry_ts": pos.entry_ts,
                        "stop_price": pos.stop_price,
                        "highest_close": pos.highest_close,
                        "last": last,
                        "unrealized_pnl": (last - pos.entry_price) * pos.qty - pos.entry_fee,
                    }
                )
            watchlist = []
            params = StrategyParams()
            for symbol in settings.symbols:
                quote = quotes.get(symbol)
                trend = None
                try:
                    hourly = load_candles(conn, settings.exchange, symbol, BASE_TIMEFRAME)
                    bars = aggregate(hourly, SIGNAL_HOURS, now_ms())
                    snaps = build_snapshots(bars, params)
                    snap = next((s for s in reversed(snaps) if s is not None), None)
                    if snap is not None:
                        trend = "up" if snap.ema_fast > snap.ema_slow else "down"
                except Exception:  # noqa: BLE001 - watchlist is best-effort
                    trend = None
                watchlist.append(
                    {
                        "symbol": symbol,
                        "last": quote["last"] if quote else None,
                        "bid": quote["bid"] if quote else None,
                        "ask": quote["ask"] if quote else None,
                        "ts": quote["ts"] if quote else None,
                        "trend": trend,
                    }
                )
            return {
                "cash": pf.cash,
                "equity": equity,
                "starting_cash": pf.starting_cash,
                "realized_pnl": pf.realized_pnl,
                "fees_paid": pf.fees_paid,
                "total_pnl": equity - pf.starting_cash,
                "day_pnl": day_pnl,
                "positions": positions,
                "watchlist": watchlist,
            }
        finally:
            conn.close()

    @app.get("/api/equity")
    def equity(limit: int = Query(500, ge=1, le=5000)) -> list[dict[str, Any]]:
        conn = open_conn()
        try:
            rows = conn.execute(
                "select ts, equity, cash from equity_snapshots order by ts desc limit ?", (limit,)
            ).fetchall()
            return [{"ts": r["ts"], "equity": r["equity"], "cash": r["cash"]} for r in reversed(rows)]
        finally:
            conn.close()

    @app.get("/api/signals")
    def signals(limit: int = Query(50, ge=1, le=500)) -> list[dict[str, Any]]:
        conn = open_conn()
        try:
            rows = conn.execute(
                "select * from signals order by created_at desc, id desc limit ?", (limit,)
            ).fetchall()
            out = []
            for r in rows:
                news_ids = json.loads(r["news_ids"])
                headlines = []
                if news_ids:
                    placeholders = ",".join("?" * len(news_ids))
                    for h in conn.execute(
                        f"select id, source, title, url, published_at, score_status from news_items"
                        f" where id in ({placeholders})",
                        news_ids,
                    ).fetchall():
                        scores = [
                            {
                                "coin": s["coin"],
                                "direction": s["direction"],
                                "strength": s["strength"],
                                "confidence": s["confidence"],
                                "rationale": s["rationale"],
                            }
                            for s in conn.execute(
                                "select coin, direction, strength, confidence, rationale from news_scores"
                                " where news_id = ?",
                                (h["id"],),
                            ).fetchall()
                        ]
                        headlines.append(
                            {
                                "id": h["id"],
                                "source": h["source"],
                                "title": h["title"],
                                "url": h["url"],
                                "published_at": h["published_at"],
                                "score_status": h["score_status"],
                                "scores": scores,
                            }
                        )
                order = conn.execute(
                    "select id, side, status, reject_reason, qty, fill_price from orders"
                    " where signal_id = ? order by id desc limit 1",
                    (r["id"],),
                ).fetchone()
                out.append(
                    {
                        "id": r["id"],
                        "ts": r["ts"],
                        "created_at": r["created_at"],
                        "symbol": r["symbol"],
                        "action": r["action"],
                        "reasons": json.loads(r["reasons"]),
                        "indicators": json.loads(r["indicators"]),
                        "news_state": r["news_state"],
                        "news_score": r["news_score"],
                        "size_multiplier": r["size_multiplier"],
                        "headlines": headlines,
                        "order": dict(order) if order else None,
                    }
                )
            return out
        finally:
            conn.close()

    @app.get("/api/trades")
    def trades(limit: int = Query(100, ge=1, le=1000)) -> list[dict[str, Any]]:
        conn = open_conn()
        try:
            rows = conn.execute(
                "select * from orders order by created_at desc, id desc limit ?", (limit,)
            ).fetchall()
            return [
                {
                    "id": r["id"],
                    "created_at": r["created_at"],
                    "symbol": r["symbol"],
                    "side": r["side"],
                    "requested_qty": r["requested_qty"],
                    "qty": r["qty"],
                    "ref_price": r["ref_price"],
                    "status": r["status"],
                    "reject_reason": r["reject_reason"],
                    "notes": json.loads(r["notes"] or "[]"),
                    "fill_price": r["fill_price"],
                    "fee": r["fee"],
                    "realized_pnl": r["realized_pnl"],
                    "signal_id": r["signal_id"],
                    "broker": r["broker"],
                }
                for r in rows
            ]
        finally:
            conn.close()

    @app.get("/api/news")
    def news(limit: int = Query(50, ge=1, le=500)) -> dict[str, Any]:
        conn = open_conn()
        try:
            scorer, reason = build_scorer(settings)
            items = []
            for r in conn.execute(
                "select * from news_items order by published_at desc, id desc limit ?", (limit,)
            ).fetchall():
                scores = [
                    {
                        "coin": s["coin"],
                        "direction": s["direction"],
                        "strength": s["strength"],
                        "confidence": s["confidence"],
                        "rationale": s["rationale"],
                        "provider": s["provider"],
                        "model": s["model"],
                    }
                    for s in conn.execute(
                        "select coin, direction, strength, confidence, rationale, provider, model"
                        " from news_scores where news_id = ?",
                        (r["id"],),
                    ).fetchall()
                ]
                items.append(
                    {
                        "id": r["id"],
                        "source": r["source"],
                        "kind": r["kind"],
                        "title": r["title"],
                        "url": r["url"],
                        "published_at": r["published_at"],
                        "fetched_at": r["fetched_at"],
                        "score_status": r["score_status"] if scorer is not None else "unscored",
                        "score_error": r["score_error"],
                        "scores": scores if scorer is not None else [],
                    }
                )
            sources = [
                {
                    "name": s["name"],
                    "kind": s["kind"],
                    "url": s["url"],
                    "last_attempt_at": s["last_attempt_at"],
                    "last_ok_at": s["last_ok_at"],
                    "last_error": s["last_error"],
                    "last_count": s["last_count"],
                }
                for s in conn.execute("select * from news_sources order by name").fetchall()
            ]
            return {
                "scoring": scoring_status(conn, settings, scorer, reason),
                "headlines": items,
                "sources": sources,
            }
        finally:
            conn.close()

    def _backtest_row(row) -> dict[str, Any] | None:
        if row is None:
            return None
        result = json.loads(row["result"])
        return {
            "id": row["id"],
            "created_at": row["created_at"],
            "params": json.loads(row["params"]),
            "result": result,
            "news_included": bool(result.get("news_included", False)),
        }

    backfill_lock = threading.Lock()

    @app.get("/api/candles/summary")
    def candles_summary() -> dict[str, Any]:
        conn = open_conn()
        try:
            return candle_history_summary(settings, conn)
        finally:
            conn.close()

    @app.post("/api/backfill")
    def backfill_run(body: BackfillBody | None = None) -> dict[str, Any]:
        payload = body or BackfillBody()
        if not backfill_lock.acquire(blocking=False):
            raise HTTPException(status_code=409, detail="Backfill already running. Wait for it to finish.")
        conn = open_conn()
        try:
            try:
                return run_backfill(settings, conn, payload.days)
            except RuntimeError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            except Exception as exc:
                raise HTTPException(
                    status_code=502,
                    detail=f"Backfill failed: {type(exc).__name__}: {exc}",
                ) from exc
        finally:
            conn.close()
            backfill_lock.release()

    @app.get("/api/backtests/latest")
    def backtests_latest() -> dict[str, Any] | None:
        conn = open_conn()
        try:
            row = conn.execute("select * from backtest_runs order by id desc limit 1").fetchone()
            return _backtest_row(row)
        finally:
            conn.close()

    @app.post("/api/backtests")
    def backtests_run() -> dict[str, Any]:
        conn = open_conn()
        try:
            try:
                run = run_stored_backtest(settings, conn)
            except RuntimeError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            row = conn.execute("select * from backtest_runs where id = ?", (run["id"],)).fetchone()
            return _backtest_row(row)  # type: ignore[return-value]
        finally:
            conn.close()

    @app.get("/api/risk")
    def get_risk() -> dict[str, Any]:
        conn = open_conn()
        try:
            return risk_payload(conn)
        finally:
            conn.close()

    @app.put("/api/risk")
    def put_risk(body: RiskUpdate) -> dict[str, Any]:
        conn = open_conn()
        try:
            limits = RiskLimits(body.max_position_pct, body.max_open_positions, body.daily_loss_limit_pct)
            try:
                limits.validate()
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            SqliteRiskStore(conn).save_limits(limits)
            return risk_payload(conn)
        finally:
            conn.close()

    @app.post("/api/kill-switch")
    def kill_switch(body: KillSwitchBody) -> dict[str, Any]:
        conn = open_conn()
        try:
            SqliteRiskStore(conn).save_kill_switch(body.engaged)
            return risk_payload(conn)
        finally:
            conn.close()

    @app.exception_handler(Exception)
    async def unhandled(_request: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled error")
        return JSONResponse(status_code=500, content={"detail": f"{type(exc).__name__}: {exc}"})

    # Expose for tests
    app.state.settings = settings  # type: ignore[attr-defined]
    app.state.service = service  # type: ignore[attr-defined]
    app.state.api_host = API_HOST  # type: ignore[attr-defined]
    return app
