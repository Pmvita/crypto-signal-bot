"""Command-line entry points: backfill, backtest, news, cycle, serve."""

from __future__ import annotations

import argparse
import json
import logging
from collections.abc import Sequence

import uvicorn

from csb.api import create_app
from csb.config import API_HOST, Settings, load_settings
from csb.db import connect, init_schema, now_ms
from csb.jobs import run_stored_backtest
from csb.marketdata import MarketData, create_exchange
from csb.news_feeds import FEEDS, fetch_feeds, new_http_client
from csb.news_scoring import build_scorer
from csb.news_store import record_source, save_headlines
from csb.service import TradingService

log = logging.getLogger("csb")


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def _open(settings: Settings):
    conn = connect(settings.db_path)
    init_schema(conn)
    return conn


def _market(settings: Settings, conn) -> MarketData:
    return MarketData(create_exchange(settings.exchange), settings.exchange, conn)


def _service(settings: Settings, conn) -> TradingService:
    scorer, reason = build_scorer(settings)
    return TradingService(settings, conn, _market(settings, conn), scorer, reason)


def cmd_backfill(settings: Settings, days: int | None) -> int:
    conn = _open(settings)
    market = _market(settings, conn)
    target_days = days if days is not None else settings.backfill_days
    print(f"Backfilling {target_days} days of 15m candles from {settings.exchange}…")
    for symbol in settings.symbols:
        print(f"  {symbol} …", end="", flush=True)

        def progress(n: int, sym: str = symbol) -> None:
            print(f"\r  {sym}: {n} candles", end="", flush=True)

        stored = market.backfill(symbol, target_days, progress=progress)
        print(f"\r  {symbol}: {stored} candles stored")
    print("Done.")
    return 0


def cmd_backtest(settings: Settings) -> int:
    conn = _open(settings)
    run = run_stored_backtest(settings, conn)
    print("Backtest (price rules only — news scoring is not included)")
    print(f"  symbols:           {', '.join(run['symbols'])}")
    print(f"  period start (ms): {run['period_start']}")
    print(f"  period end (ms):   {run['period_end']}")
    print(f"  bars:              {run['bars']}")
    print(f"  starting cash:     ${run['starting_cash']:,.2f}")
    print(f"  final equity:      ${run['final_equity']:,.2f}")
    print(f"  total return:      {run['total_return_pct']:+.2f}%")
    print(f"  max drawdown:      {run['max_drawdown_pct']:.2f}%")
    print(f"  trades:            {run['trades']}")
    print(f"  win rate:          {run['win_rate_pct']}")
    print(f"  profit factor:     {run['profit_factor']}")
    print(f"  total fees:        ${run['total_fees']:,.2f}")
    print(f"  buy & hold:        {run['buy_hold_return_pct']}")
    print(f"  news included:     {run['news_included']}")
    return 0


def cmd_news(settings: Settings) -> int:
    conn = _open(settings)
    client = new_http_client()
    try:
        results = fetch_feeds(client, FEEDS)
    finally:
        client.close()
    now = now_ms()
    total_new = 0
    for result in results:
        ok = result.error is None
        record_source(conn, result.feed, ok, result.error, len(result.headlines), now)
        if ok:
            added = save_headlines(conn, result.headlines, now)
            total_new += added
            print(f"  {result.feed.name}: {len(result.headlines)} headlines ({added} new)")
        else:
            print(f"  {result.feed.name}: FAILED — {result.error}")
    scorer, reason = build_scorer(settings)
    if scorer is None:
        print(f"Scoring: off — {reason}")
    else:
        print(f"Scoring: on ({scorer.provider}/{scorer.model})")
    print(f"Stored {total_new} new headlines.")
    return 0


def cmd_cycle(settings: Settings) -> int:
    conn = _open(settings)
    service = _service(settings, conn)
    summary = service.run_cycle()
    print(json.dumps(summary, indent=2, default=str))
    return 0 if summary["status"] == "ok" else 1


def cmd_serve(settings: Settings) -> int:
    app = create_app(settings, start_loop=True)
    print(f"Serving engine API on http://{API_HOST}:{settings.api_port}")
    print("Paper trading loop starts STOPPED — use Trading page or POST /api/trading/start.")
    print("Live exchange trading is not available in phase 1.")
    uvicorn.run(app, host=API_HOST, port=settings.api_port, log_level="info")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="csb", description="Crypto Signal Bot (phase 1: paper trading only)")
    sub = parser.add_subparsers(dest="command", required=True)

    backfill = sub.add_parser("backfill", help="Download historical 15m candles")
    backfill.add_argument("--days", type=int, default=None, help="Days of history (default: CSB_BACKFILL_DAYS)")

    sub.add_parser("backtest", help="Run the price-only backtest on stored candles")
    sub.add_parser("news", help="Fetch RSS headlines once")
    sub.add_parser("cycle", help="Run one paper trading cycle")
    sub.add_parser(
        "serve",
        help="Start the local API + market/news supervisor (paper trading paused until started)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    _setup_logging()
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    settings = load_settings()

    if args.command == "backfill":
        return cmd_backfill(settings, args.days)
    if args.command == "backtest":
        return cmd_backtest(settings)
    if args.command == "news":
        return cmd_news(settings)
    if args.command == "cycle":
        return cmd_cycle(settings)
    if args.command == "serve":
        return cmd_serve(settings)
    parser.error(f"unknown command {args.command!r}")
    return 2
