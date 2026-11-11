from csb.db import connect, init_schema

TABLES = {
    "candles",
    "news_items",
    "news_scores",
    "news_sources",
    "signals",
    "orders",
    "positions",
    "account",
    "equity_snapshots",
    "risk_settings",
    "risk_state",
    "cycles",
    "backtest_runs",
    "quotes",
    "meta",
}


def test_init_schema_creates_all_tables_and_is_idempotent(tmp_path):
    conn = connect(tmp_path / "t.sqlite3")
    init_schema(conn)
    init_schema(conn)
    names = {r["name"] for r in conn.execute("select name from sqlite_master where type='table'")}
    assert TABLES <= names


def test_connect_creates_missing_parent_directory(tmp_path):
    conn = connect(tmp_path / "nested" / "dir" / "t.sqlite3")
    init_schema(conn)
    assert (tmp_path / "nested" / "dir" / "t.sqlite3").exists()
