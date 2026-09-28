"""Read a local review export into plain rows. No network."""

from __future__ import annotations

import csv
import json
from pathlib import Path

_TEXT_ALIASES = ("text", "review", "content", "body")
_RATING_ALIASES = ("rating", "stars", "score")
_STORE_ALIASES = ("store", "platform")
_DATE_ALIASES = ("date",)
_TITLE_ALIASES = ("title",)
_APP_ALIASES = ("app_id", "appid", "package", "bundle_id", "product_id")

_FIELDS = {
    "text": _TEXT_ALIASES,
    "rating": _RATING_ALIASES,
    "store": _STORE_ALIASES,
    "date": _DATE_ALIASES,
    "title": _TITLE_ALIASES,
    "app_id": _APP_ALIASES,
}


class LoadError(Exception):
    """The export cannot be read. The message includes the path."""

    def __init__(self, path: Path | str, message: str) -> None:
        self.path = Path(path)
        super().__init__(f"{message}: {self.path}")


def load_export(path: Path | str) -> list[dict]:
    source = Path(path)
    if not source.exists():
        raise LoadError(source, "file not found")
    if not source.is_file():
        raise LoadError(source, "not a file")
    if source.suffix.lower() not in {".csv", ".json"}:
        raise LoadError(source, "expected a .csv or .json file")

    try:
        raw = source.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise LoadError(source, "unreadable file") from exc

    if raw.strip() == "":
        return []

    if source.suffix.lower() == ".csv":
        rows = _read_csv(raw)
    else:
        rows = _read_json(source, raw)

    if not rows:
        return []
    _require_columns(source, rows)
    return [_normalize(row) for row in rows]


def _read_csv(raw: str) -> list[dict]:
    reader = csv.DictReader(raw.splitlines())
    if reader.fieldnames is None:
        return []
    return [dict(row) for row in reader]


def _read_json(path: Path, raw: str) -> list[dict]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise LoadError(path, "invalid JSON") from exc

    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict) and len(payload) == 1 and isinstance(next(iter(payload.values())), list):
        rows = next(iter(payload.values()))
    else:
        raise LoadError(path, "JSON must be a list or an object with one list")

    normalized: list[dict] = []
    for row in rows:
        if not isinstance(row, dict):
            raise LoadError(path, "JSON rows must be objects")
        normalized.append(row)
    return normalized


def _require_columns(path: Path, rows: list[dict]) -> None:
    present = {key.lower() for row in rows for key in row}
    missing: list[str] = []
    for field in ("store", "rating", "date"):
        if not _has_alias(present, _FIELDS[field]):
            missing.append(field)
    if not _has_alias(present, _TEXT_ALIASES) and not _has_alias(present, _TITLE_ALIASES):
        missing.append("text")
    if missing:
        raise LoadError(path, "missing field: " + ", ".join(missing))


def _has_alias(present: set[str], aliases: tuple[str, ...]) -> bool:
    return any(alias in present for alias in aliases)


def _normalize(row: dict) -> dict:
    folded = {str(key).lower(): value for key, value in row.items()}
    text = _pick(folded, _TEXT_ALIASES)
    title = _pick(folded, _TITLE_ALIASES)
    if text.strip() == "" and title.strip() != "":
        text = title
    return {
        "store": _cell(folded, _STORE_ALIASES),
        "rating": _cell(folded, _RATING_ALIASES),
        "date": _cell(folded, _DATE_ALIASES),
        "text": text.strip(),
        "title": title.strip(),
        "app_id": _cell(folded, _APP_ALIASES),
    }


def _pick(folded: dict, aliases: tuple[str, ...]) -> str:
    for alias in aliases:
        if alias in folded and folded[alias] is not None:
            return str(folded[alias])
    return ""


def _cell(folded: dict, aliases: tuple[str, ...]) -> str:
    return _pick(folded, aliases).strip()
