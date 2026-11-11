from pathlib import Path

from csb.config import API_HOST, PROJECT_ROOT, load_settings, project_env


def test_defaults_use_keyless_public_exchange_and_paper_values():
    s = load_settings({})
    assert s.exchange == "coinbaseexchange"
    assert s.symbols == ("BTC/USD", "ETH/USD", "SOL/USD")
    assert s.coins == ("BTC", "ETH", "SOL")
    assert s.fee_bps == 40 and s.slippage_bps == 5
    assert s.starting_cash == 10_000
    assert s.openai_api_key == "" and s.anthropic_api_key == ""
    assert s.openai_base_url == "https://api.openai.com/v1"


def test_api_host_is_loopback_and_not_configurable():
    s = load_settings({"CSB_API_HOST": "0.0.0.0"})
    assert API_HOST == "127.0.0.1"
    assert not hasattr(s, "api_host")


def test_env_values_override_defaults():
    s = load_settings(
        {
            "CSB_EXCHANGE": "kraken",
            "CSB_SYMBOLS": "BTC/USD, ETH/USD",
            "CSB_FEE_BPS": "26",
            "CSB_LLM_PROVIDER": "Anthropic",
            "ANTHROPIC_API_KEY": "  test-key  ",
            "OPENAI_BASE_URL": "https://openrouter.ai/api/v1/",
        }
    )
    assert s.exchange == "kraken"
    assert s.symbols == ("BTC/USD", "ETH/USD")
    assert s.fee_bps == 26
    assert s.llm_provider == "anthropic"
    assert s.anthropic_api_key == "test-key"
    assert s.openai_base_url == "https://openrouter.ai/api/v1"


def test_llm_keys_come_from_the_project_env_file_only(tmp_path):
    (tmp_path / ".env").write_text("OPENAI_API_KEY=from-file\nCSB_EXCHANGE=bitstamp\n", encoding="utf-8")
    process_env = {"ANTHROPIC_API_KEY": "from-process", "OPENAI_API_KEY": "process-openai", "CSB_EXCHANGE": "kraken"}
    merged = project_env(tmp_path, process_env)
    assert merged["OPENAI_API_KEY"] == "from-file"
    assert "ANTHROPIC_API_KEY" not in merged
    assert merged["CSB_EXCHANGE"] == "kraken"  # CSB_* settings may be overridden by the process environment


def test_missing_env_file_means_no_keys(tmp_path):
    merged = project_env(tmp_path, {"OPENAI_API_KEY": "process-openai"})
    assert load_settings(merged).openai_api_key == ""


def test_relative_db_path_is_resolved_inside_the_project():
    s = load_settings({"CSB_DB_PATH": "data/x.sqlite3"})
    assert s.db_path == PROJECT_ROOT / "data" / "x.sqlite3"
    assert isinstance(s.db_path, Path)
