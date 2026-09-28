"""Runtime configuration for the weekly review pulse."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path

DEFAULT_MODEL = "qwen/qwen3.8-27b"
DEFAULT_EXPORT = Path("data/exports/reviews.csv")
DEFAULT_WINDOW_WEEKS = 12


@dataclass(frozen=True)
class Config:
    groq_api_key: str
    groq_model: str
    recipient: str
    export_path: Path
    window_weeks: int
    run_date: date
    docs_mcp_command: str
    gmail_mcp_command: str
    mcp_api_key: str


def _text(env: Mapping[str, str], key: str) -> str:
    return str(env.get(key, "")).strip()


def load_config(env: Mapping[str, str]) -> Config:
    """Read pulse settings from env. Blank optional values stay empty or use defaults."""
    model = _text(env, "GROQ_MODEL") or DEFAULT_MODEL
    export = _text(env, "PULSE_EXPORT")
    weeks_text = _text(env, "PULSE_WINDOW_WEEKS")
    weeks = int(weeks_text) if weeks_text else DEFAULT_WINDOW_WEEKS
    mcp_url = _text(env, "MCP_URL")
    docs = _text(env, "DOCS_MCP_COMMAND") or mcp_url
    gmail = _text(env, "GMAIL_MCP_COMMAND") or mcp_url
    return Config(
        groq_api_key=_text(env, "GROQ_API_KEY"),
        groq_model=model,
        recipient=_text(env, "PULSE_RECIPIENT"),
        export_path=Path(export) if export else DEFAULT_EXPORT,
        window_weeks=weeks,
        run_date=date.today(),
        docs_mcp_command=docs,
        gmail_mcp_command=gmail,
        mcp_api_key=_text(env, "MCP_API_KEY"),
    )


def missing_runtime(config: Config) -> list[str]:
    """Names of required settings that are still blank. Does not raise."""
    missing: list[str] = []
    if not config.groq_api_key.strip():
        missing.append("GROQ_API_KEY")
    if not config.recipient.strip():
        missing.append("PULSE_RECIPIENT")
    return missing
