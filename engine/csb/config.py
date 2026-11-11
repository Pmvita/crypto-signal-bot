"""Settings. Values come from the project's own .env file and the process environment only."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values

# The API controls trading, so it listens on loopback only. Not configurable in phase 1.
API_HOST = "127.0.0.1"

LLM_PROVIDERS = ("openai", "anthropic")


def resolve_project_root(process_env: Mapping[str, str] | None = None) -> Path:
    """Repo root in CLI/dev; Electron packaged mode may set CSB_PROJECT_ROOT to AppData."""
    env = process_env if process_env is not None else os.environ
    override = (env.get("CSB_PROJECT_ROOT") or "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return Path(__file__).resolve().parents[2]


PROJECT_ROOT = resolve_project_root()


@dataclass(frozen=True)
class Settings:
    exchange: str
    symbols: tuple[str, ...]
    backfill_days: int
    starting_cash: float
    fee_bps: float
    slippage_bps: float
    cycle_seconds: int
    news_refresh_seconds: int
    api_port: int
    db_path: Path
    llm_provider: str
    openai_api_key: str
    openai_model: str
    openai_base_url: str
    anthropic_api_key: str
    anthropic_model: str

    @property
    def coins(self) -> tuple[str, ...]:
        """Base assets of the traded symbols, e.g. BTC for BTC/USD."""
        return tuple(dict.fromkeys(s.split("/")[0] for s in self.symbols))


def project_env(root: Path, process_env: Mapping[str, str]) -> dict[str, str]:
    """Values from `root/.env`, with CSB_* names overridable by the process environment.

    LLM keys and model names are read from the project's .env file only. A key that happens to be
    exported in the shell for some other tool is never picked up, so the bot cannot spend it by surprise.
    """
    values = {k: v for k, v in dotenv_values(root / ".env").items() if v is not None}
    values.update({k: v for k, v in process_env.items() if k.startswith("CSB_")})
    return values


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    """Build settings. With env=None, read PROJECT_ROOT/.env (see `project_env`)."""
    root = resolve_project_root(os.environ if env is None else env)
    source = project_env(root, os.environ) if env is None else env

    def get(name: str, default: str) -> str:
        value = source.get(name, "")
        return value.strip() if value and value.strip() else default

    db_path = Path(get("CSB_DB_PATH", "data/csb.sqlite3"))
    if not db_path.is_absolute():
        db_path = root / db_path

    symbols = tuple(s.strip().upper() for s in get("CSB_SYMBOLS", "BTC/USD,ETH/USD,SOL/USD").split(",") if s.strip())
    provider = get("CSB_LLM_PROVIDER", "openai").lower()
    if provider not in LLM_PROVIDERS:
        raise ValueError(f"CSB_LLM_PROVIDER must be one of {LLM_PROVIDERS}, got {provider!r}")

    return Settings(
        exchange=get("CSB_EXCHANGE", "coinbaseexchange").lower(),
        symbols=symbols,
        backfill_days=int(get("CSB_BACKFILL_DAYS", "730")),
        starting_cash=float(get("CSB_STARTING_CASH", "10000")),
        fee_bps=float(get("CSB_FEE_BPS", "40")),
        slippage_bps=float(get("CSB_SLIPPAGE_BPS", "5")),
        # Default 20s so 15m bar closes are noticed quickly (not once-a-minute stale). Override with CSB_CYCLE_SECONDS.
        cycle_seconds=int(get("CSB_CYCLE_SECONDS", "20")),
        news_refresh_seconds=int(get("CSB_NEWS_REFRESH_SECONDS", "600")),
        api_port=int(get("CSB_API_PORT", "8787")),
        db_path=db_path,
        llm_provider=provider,
        openai_api_key=get("OPENAI_API_KEY", ""),
        openai_model=get("OPENAI_MODEL", ""),
        openai_base_url=get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/"),
        anthropic_api_key=get("ANTHROPIC_API_KEY", ""),
        anthropic_model=get("ANTHROPIC_MODEL", ""),
    )
