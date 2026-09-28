"""Persist state.json and per-run notes. No review text, no recipient."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

DEFAULT_STATE_PATH = Path("data/state.json")
DEFAULT_RUNS_DIR = Path("data/runs")


def load_state(path: Path | str = DEFAULT_STATE_PATH) -> dict[str, Any]:
    source = Path(path)
    if not source.exists():
        return {}
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_state_entry(
    week_key: str,
    *,
    doc_id: str,
    url: str,
    path: Path | str = DEFAULT_STATE_PATH,
) -> None:
    """Write or update one week. Called only after Docs returns an id."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    state = load_state(target)
    state[week_key] = {"doc_id": doc_id, "url": url or ""}
    target.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_run_notes(
    week_key: str,
    payload: Mapping[str, Any],
    *,
    runs_dir: Path | str = DEFAULT_RUNS_DIR,
) -> Path:
    """Write data/runs/{week_key}.json. Omits quotes and recipient."""
    directory = Path(runs_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{week_key}.json"
    safe = {
        "week_key": week_key,
        "window_start": payload.get("window_start"),
        "window_end": payload.get("window_end"),
        "kept": payload.get("kept"),
        "by_store": payload.get("by_store"),
        "unthemed": payload.get("unthemed"),
        "dropped": payload.get("dropped"),
        "highlighted": payload.get("highlighted"),
        "model": payload.get("model"),
        "doc_id": payload.get("doc_id"),
        "doc_url": payload.get("doc_url"),
        "draft_created": payload.get("draft_created"),
        "stop_reason": payload.get("stop_reason"),
    }
    path.write_text(json.dumps(safe, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path
