"""Keep reviews inside the window. No themes and no network."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta

_ALLOWED_WEEKS = {8, 9, 10, 11, 12}
_EIGHT_WEEKS = timedelta(days=56)
_ALLOWED_APPS = {"com.nextbillion.groww", "1404871703"}
_DROP_KEYS = ("empty", "bad_date", "bad_rating", "bad_store", "out_of_window", "duplicate", "wrong_app")
_STORE_ORDER = ("app_store", "play")
_STORE_ALIASES = {
    "ios": "app_store",
    "apple": "app_store",
    "app store": "app_store",
    "app_store": "app_store",
    "android": "play",
    "play": "play",
    "google play": "play",
    "play_store": "play",
}
_MONTHS = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}
_AMBIGUOUS_DATE = re.compile(r"^\d{1,2}[/-]\d{1,2}[/-]\d{2}(\d{2})?$")
_ISO_DATE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")
_DAY_MONTH = re.compile(r"^(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})$")
_MONTH_DAY = re.compile(r"^([A-Za-z]+)\s+(\d{1,2}),\s*(\d{4})$")
_WHITESPACE = re.compile(r"\s+")


@dataclass(frozen=True)
class Review:
    store: str
    rating: int
    date: date
    text: str
    title: str


@dataclass
class FilterResult:
    kept: list[Review]
    dropped: dict[str, int]
    missing_stores: list[str]
    stores_empty_in_window: list[str]
    window_start: date
    window_end: date
    actual_start: date | None
    actual_end: date | None
    stop_reason: str


def filter_reviews(rows: list[dict], *, window_weeks: int, run_date: date) -> FilterResult:
    window_start = run_date - timedelta(days=window_weeks * 7)
    window_end = run_date
    if window_weeks not in _ALLOWED_WEEKS:
        preflight = _preflight_window(rows, window_start, window_end)
        if preflight is not None:
            return preflight
    return _scan(rows, window_start, window_end)


def _empty_dropped() -> dict[str, int]:
    return {key: 0 for key in _DROP_KEYS}


def _result(
    *,
    window_start: date,
    window_end: date,
    kept: list[Review] | None = None,
    dropped: dict[str, int] | None = None,
    seen_stores: set[str] | None = None,
    stop_reason: str = "",
) -> FilterResult:
    kept_rows = [] if stop_reason and stop_reason in {"ambiguous_date", "window"} else list(kept or [])
    seen = set() if stop_reason in {"ambiguous_date", "window"} else set(seen_stores or [])
    counts = {store: sum(1 for review in kept_rows if review.store == store) for store in _STORE_ORDER}
    dates = [review.date for review in kept_rows]
    return FilterResult(
        kept=kept_rows,
        dropped=dropped if dropped is not None else _empty_dropped(),
        missing_stores=[store for store in _STORE_ORDER if store not in seen],
        stores_empty_in_window=[store for store in _STORE_ORDER if store in seen and counts[store] == 0],
        window_start=window_start,
        window_end=window_end,
        actual_start=min(dates) if dates else None,
        actual_end=max(dates) if dates else None,
        stop_reason=stop_reason,
    )


def _preflight_window(rows: list[dict], window_start: date, window_end: date) -> FilterResult | None:
    parsed: list[date] = []
    for row in rows:
        raw_date = str(row.get("date", "")).strip()
        if _AMBIGUOUS_DATE.fullmatch(raw_date):
            return _result(window_start=window_start, window_end=window_end, stop_reason="ambiguous_date")
        found = _parse_date(raw_date)
        if found is not None:
            parsed.append(found)
    if parsed and max(parsed) - min(parsed) >= _EIGHT_WEEKS:
        return _result(window_start=window_start, window_end=window_end, stop_reason="window")
    return None


def _scan(rows: list[dict], window_start: date, window_end: date) -> FilterResult:
    dropped = _empty_dropped()
    kept: list[Review] = []
    seen_stores: set[str] = set()
    seen_keys: set[tuple] = set()
    parsed_a_date = False
    asked_for_a_date = False

    for row in rows:
        raw_date = str(row.get("date", "")).strip()
        if _AMBIGUOUS_DATE.fullmatch(raw_date):
            return _result(window_start=window_start, window_end=window_end, stop_reason="ambiguous_date")

        text = _collapse(str(row.get("text", "")))
        title = _collapse(str(row.get("title", "")))
        if text == "" and title != "":
            text = title
        if text == "":
            dropped["empty"] += 1
            continue

        asked_for_a_date = True
        parsed = _parse_date(raw_date)
        if parsed is None:
            dropped["bad_date"] += 1
            continue
        parsed_a_date = True

        rating = _parse_rating(row.get("rating", ""))
        if rating is None:
            dropped["bad_rating"] += 1
            continue

        store = _STORE_ALIASES.get(str(row.get("store", "")).strip().lower())
        if store is None:
            dropped["bad_store"] += 1
            continue
        seen_stores.add(store)

        app_id = str(row.get("app_id", "")).strip()
        if app_id != "" and app_id not in _ALLOWED_APPS:
            dropped["wrong_app"] += 1
            continue

        if parsed < window_start or parsed > window_end:
            dropped["out_of_window"] += 1
            continue

        key = (store, parsed, rating, text)
        if key in seen_keys:
            dropped["duplicate"] += 1
            continue
        seen_keys.add(key)
        kept.append(Review(store=store, rating=rating, date=parsed, text=text, title=title))

    stop_reason = ""
    if asked_for_a_date and not parsed_a_date:
        stop_reason = "unparseable_dates"
        kept = []
        seen_stores = set()

    return _result(
        window_start=window_start,
        window_end=window_end,
        kept=kept,
        dropped=dropped,
        seen_stores=seen_stores,
        stop_reason=stop_reason,
    )


def _parse_rating(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if 1 <= value <= 5 else None
    text = str(value).strip()
    if re.fullmatch(r"[1-5]", text):
        return int(text)
    return None


def _parse_date(value: str) -> date | None:
    if value == "":
        return None
    iso = _ISO_DATE.match(value)
    if iso:
        return _make_date(int(iso.group(1)), int(iso.group(2)), int(iso.group(3)))
    day_month = _DAY_MONTH.match(value)
    if day_month:
        month = _MONTHS.get(day_month.group(2).lower())
        if month is None:
            return None
        return _make_date(int(day_month.group(3)), month, int(day_month.group(1)))
    month_day = _MONTH_DAY.match(value)
    if month_day:
        month = _MONTHS.get(month_day.group(1).lower())
        if month is None:
            return None
        return _make_date(int(month_day.group(3)), month, int(month_day.group(2)))
    return None


def _make_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _collapse(value: str) -> str:
    return _WHITESPACE.sub(" ", value).strip()
