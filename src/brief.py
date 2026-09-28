"""Build the Groq brief and the published header. No network."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from typing import Sequence

from src.cluster import ThemeStats
from src.filter import FilterResult
from src.quotes import Quote


@dataclass(frozen=True)
class HighlightedTheme:
    name: str
    count: int
    avg_rating: str


@dataclass(frozen=True)
class OtherTheme:
    name: str
    count: int


@dataclass(frozen=True)
class BriefQuote:
    text: str
    store: str
    rating: int
    date: str
    theme: str


@dataclass
class Brief:
    title: str
    window_start: date
    window_end: date
    run_date: date
    actual_start: date | None
    actual_end: date | None
    kept: int
    by_store: dict[str, int]
    missing_stores: list[str]
    stores_empty_in_window: list[str]
    unthemed: int
    dropped: dict[str, int]
    highlighted: list[HighlightedTheme]
    other_themes: list[OtherTheme]
    quotes: list[BriefQuote]
    shortfalls: list[str]
    note_mode: str


@dataclass(frozen=True)
class Draft:
    doc_body: str
    email_subject: str
    email_body: str


def build_brief(
    *,
    filtered: FilterResult,
    run_date: date,
    highlighted: Sequence[ThemeStats],
    other_themes: Sequence[ThemeStats],
    quotes: Sequence[Quote],
    unthemed: int,
    loaded_count: int,
) -> Brief:
    kept = len(filtered.kept)
    by_store = {
        "app_store": sum(1 for review in filtered.kept if review.store == "app_store"),
        "play": sum(1 for review in filtered.kept if review.store == "play"),
    }
    dropped = dict(filtered.dropped)
    note_mode = _note_mode(
        loaded_count=loaded_count,
        kept=kept,
        dropped=dropped,
        unthemed=unthemed,
    )
    shortfalls = _shortfalls(
        note_mode=note_mode,
        dropped=dropped,
        unthemed=unthemed,
        missing_stores=filtered.missing_stores,
        stores_empty_in_window=filtered.stores_empty_in_window,
        highlighted_count=len(highlighted),
        quote_count=len(quotes),
    )
    return Brief(
        title=f"Groww — Weekly Review Pulse — week ending {filtered.window_end.isoformat()}",
        window_start=filtered.window_start,
        window_end=filtered.window_end,
        run_date=run_date,
        actual_start=filtered.actual_start,
        actual_end=filtered.actual_end,
        kept=kept,
        by_store=by_store,
        missing_stores=list(filtered.missing_stores),
        stores_empty_in_window=list(filtered.stores_empty_in_window),
        unthemed=unthemed,
        dropped=dropped,
        highlighted=[
            HighlightedTheme(
                name=item.name,
                count=item.count,
                avg_rating=format(item.avg_rating, "f"),
            )
            for item in highlighted
        ],
        other_themes=[OtherTheme(name=item.name, count=item.count) for item in other_themes],
        quotes=[
            BriefQuote(
                text=quote.text,
                store=quote.store,
                rating=quote.rating,
                date=quote.date.isoformat(),
                theme=quote.theme,
            )
            for quote in quotes
        ],
        shortfalls=shortfalls,
        note_mode=note_mode,
    )


def prompt_payload(brief: Brief) -> dict:
    """JSON for Groq. No recipient and no raw review rows."""
    return {
        "title": brief.title,
        "window_start": brief.window_start.isoformat(),
        "window_end": brief.window_end.isoformat(),
        "run_date": brief.run_date.isoformat(),
        "actual_start": brief.actual_start.isoformat() if brief.actual_start else None,
        "actual_end": brief.actual_end.isoformat() if brief.actual_end else None,
        "kept": brief.kept,
        "by_store": brief.by_store,
        "missing_stores": brief.missing_stores,
        "stores_empty_in_window": brief.stores_empty_in_window,
        "unthemed": brief.unthemed,
        "dropped": brief.dropped,
        "highlighted": [asdict(item) for item in brief.highlighted],
        "other_themes": [asdict(item) for item in brief.other_themes],
        "quotes": [asdict(item) for item in brief.quotes],
        "shortfalls": brief.shortfalls,
        "note_mode": brief.note_mode,
    }


def render_header(brief: Brief) -> str:
    lines = [
        brief.title,
        f"Window: {brief.window_start.isoformat()} to {brief.window_end.isoformat()}",
        f"Run date: {brief.run_date.isoformat()}",
        (
            f"Reviews kept: {brief.kept} "
            f"(App Store {brief.by_store.get('app_store', 0)}, "
            f"Play {brief.by_store.get('play', 0)})"
        ),
    ]
    if (
        brief.actual_start
        and brief.actual_end
        and (brief.actual_start != brief.window_start or brief.actual_end != brief.window_end)
    ):
        lines.append(
            f"Actual review dates: {brief.actual_start.isoformat()} to {brief.actual_end.isoformat()}"
        )
    out = brief.dropped.get("out_of_window", 0)
    if out:
        lines.append(f"Dropped out of window: {out}")
    dupes = brief.dropped.get("duplicate", 0)
    if dupes:
        lines.append(f"Dropped duplicates: {dupes}")
    lines.extend(brief.shortfalls)
    return "\n".join(lines)


def _note_mode(*, loaded_count: int, kept: int, dropped: dict[str, int], unthemed: int) -> str:
    if loaded_count == 0:
        return "empty_export"
    right_app_touch = kept + sum(
        count for key, count in dropped.items() if key != "wrong_app"
    )
    if kept == 0 and right_app_touch > 0:
        return "empty_window"
    if kept == 0 and dropped.get("wrong_app", 0) > 0:
        return "wrong_app"
    if kept > 0 and unthemed == kept:
        return "unthemed"
    return "normal"


def _shortfalls(
    *,
    note_mode: str,
    dropped: dict[str, int],
    unthemed: int,
    missing_stores: Sequence[str],
    stores_empty_in_window: Sequence[str],
    highlighted_count: int,
    quote_count: int,
) -> list[str]:
    lines: list[str] = []
    if note_mode == "empty_export":
        lines.append("No reviews in this export.")
    if note_mode == "wrong_app":
        lines.append("No reviews for the Groww app in this export.")
    if note_mode == "empty_window":
        lines.append(
            f"No reviews in this window. {dropped.get('out_of_window', 0)} dropped as out of window."
        )
    if unthemed > 0:
        lines.append(f"No catalog theme matched {unthemed} reviews.")
    if "app_store" in missing_stores:
        lines.append("App Store export is absent.")
    if "play" in missing_stores:
        lines.append("Play export is absent.")
    if "app_store" in stores_empty_in_window:
        lines.append("App Store had no reviews in the window.")
    if "play" in stores_empty_in_window:
        lines.append("Play had no reviews in the window.")
    if highlighted_count in {1, 2}:
        lines.append(f"Only {highlighted_count} themes in this window.")
    if note_mode == "normal" and quote_count == 0:
        lines.append("No safe quote was available.")
    if quote_count in {1, 2}:
        lines.append(f"{quote_count} safe quotes; fewer than 3.")
    return lines
