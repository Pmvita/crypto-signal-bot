"""SQLite storage. One file, WAL mode, one connection per thread."""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

SCHEMA = """
create table if not exists candles (
    exchange text not null,
    symbol text not null,
    timeframe text not null,
    ts integer not null,
    open real not null,
    high real not null,
    low real not null,
    close real not null,
    volume real not null,
    primary key (exchange, symbol, timeframe, ts)
);

create table if not exists quotes (
    symbol text primary key,
    bid real,
    ask real,
    last real not null,
    ts integer not null
);

create table if not exists news_items (
    id integer primary key autoincrement,
    source text not null,
    kind text not null,
    title text not null,
    url text not null unique,
    published_at integer not null,
    fetched_at integer not null,
    score_status text not null default 'unscored',
    score_error text
);
create index if not exists idx_news_published on news_items (published_at);

create table if not exists news_scores (
    id integer primary key autoincrement,
    news_id integer not null references news_items (id) on delete cascade,
    coin text not null,
    direction integer not null,
    strength real not null,
    confidence real not null,
    rationale text not null,
    provider text not null,
    model text not null,
    scored_at integer not null
);
create index if not exists idx_news_scores_coin on news_scores (coin);

create table if not exists news_sources (
    name text primary key,
    kind text not null,
    url text not null,
    last_attempt_at integer,
    last_ok_at integer,
    last_error text,
    last_count integer
);

create table if not exists signals (
    id integer primary key autoincrement,
    ts integer not null,
    created_at integer not null,
    symbol text not null,
    action text not null,
    reasons text not null,
    indicators text not null,
    news_state text not null,
    news_score real,
    news_ids text not null,
    size_multiplier real not null
);
create index if not exists idx_signals_created on signals (created_at);

create table if not exists orders (
    id integer primary key autoincrement,
    created_at integer not null,
    symbol text not null,
    side text not null,
    requested_qty real not null,
    qty real not null,
    ref_price real not null,
    status text not null,
    reject_reason text,
    notes text not null default '[]',
    fill_price real,
    fee real,
    realized_pnl real,
    signal_id integer references signals (id),
    broker text not null
);
create index if not exists idx_orders_created on orders (created_at);

create table if not exists positions (
    symbol text primary key,
    qty real not null,
    entry_price real not null,
    entry_ts integer not null,
    entry_fee real not null,
    stop_price real not null,
    highest_close real not null
);

create table if not exists account (
    id integer primary key check (id = 1),
    cash real not null,
    starting_cash real not null,
    realized_pnl real not null,
    fees_paid real not null
);

create table if not exists equity_snapshots (
    ts integer primary key,
    equity real not null,
    cash real not null
);

create table if not exists risk_settings (
    id integer primary key check (id = 1),
    max_position_pct real not null,
    max_open_positions integer not null,
    daily_loss_limit_pct real not null,
    updated_at integer not null
);

create table if not exists risk_state (
    id integer primary key check (id = 1),
    kill_switch integer not null,
    day text,
    day_start_equity real,
    halted integer not null,
    halted_at integer
);

create table if not exists cycles (
    id integer primary key autoincrement,
    started_at integer not null,
    finished_at integer,
    status text not null,
    error text,
    summary text
);

create table if not exists backtest_runs (
    id integer primary key autoincrement,
    created_at integer not null,
    params text not null,
    result text not null
);

create table if not exists meta (
    key text primary key,
    value text not null
);
"""


def now_ms() -> int:
    return int(time.time() * 1000)


def connect(path: Path | str) -> sqlite3.Connection:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("pragma journal_mode = wal")
    conn.execute("pragma foreign_keys = on")
    conn.execute("pragma busy_timeout = 30000")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def get_meta(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("select value from meta where key = ?", (key,)).fetchone()
    return row["value"] if row else None


def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "insert into meta (key, value) values (?, ?) on conflict (key) do update set value = excluded.value",
        (key, value),
    )
