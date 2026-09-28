"""Select verbatim quotes from highlighted themes. No model calls."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Sequence

from src.cluster import ThemeStats
from src.filter import Review

_EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_HANDLE = re.compile(r"@[A-Za-z0-9_]{2,}")
_PAN = re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b", re.IGNORECASE)
_LONG_DIGITS = re.compile(r"\d{10,}")
_WHITESPACE = re.compile(r"\s+")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
_ALNUM = re.compile(r"[A-Za-z0-9]")


@dataclass(frozen=True)
class Quote:
    text: str
    store: str
    rating: int
    date: date
    theme: str


def is_unsafe(review: Review) -> bool:
    blob = f"{review.title}\n{review.text}"
    return bool(
        _EMAIL.search(blob)
        or _HANDLE.search(blob)
        or _PAN.search(blob)
        or _LONG_DIGITS.search(blob)
    )


def select_quotes(
    themed_reviews: Sequence[tuple[Review, str | None]],
    highlighted: Sequence[ThemeStats] | Sequence[str],
) -> list[Quote]:
    theme_names = [
        item.name if isinstance(item, ThemeStats) else str(item) for item in highlighted
    ]
    if not theme_names:
        return []

    by_theme: dict[str, list[Review]] = {name: [] for name in theme_names}
    for review, theme in themed_reviews:
        if theme is None or theme not in by_theme:
            continue
        if is_unsafe(review):
            continue
        if not _has_alnum(review.text) and not _has_alnum(review.title):
            continue
        by_theme[theme].append(review)

    for name in theme_names:
        by_theme[name].sort(key=_candidate_key)

    chosen: list[Quote] = []
    used_ids: set[int] = set()
    used_texts: set[str] = set()

    def try_add(review: Review, theme: str) -> bool:
        review_id = id(review)
        if review_id in used_ids:
            return False
        source = review.text.strip() or review.title.strip()
        cut = cut_quote(source)
        collapsed = _collapse(cut).casefold()
        if not collapsed or collapsed in used_texts:
            return False
        if not _has_alnum(cut):
            return False
        chosen.append(
            Quote(
                text=cut,
                store=review.store,
                rating=review.rating,
                date=review.date,
                theme=theme,
            )
        )
        used_ids.add(review_id)
        used_texts.add(collapsed)
        return True

    # One from each highlighted theme, in rank order.
    for theme in theme_names:
        for review in by_theme[theme]:
            if try_add(review, theme):
                break
        if len(chosen) == 3:
            return chosen

    # Fill from remaining safe candidates across highlighted themes.
    remaining: list[tuple[Review, str]] = []
    for theme in theme_names:
        for review in by_theme[theme]:
            if id(review) not in used_ids:
                remaining.append((review, theme))
    remaining.sort(key=lambda item: _candidate_key(item[0]))
    for review, theme in remaining:
        try_add(review, theme)
        if len(chosen) == 3:
            break
    return chosen


def cut_quote(text: str) -> str:
    cleaned = _WHITESPACE.sub(" ", text).strip()
    if not cleaned:
        return ""
    sentences = _SENTENCE_END.split(cleaned)
    if not sentences:
        return cleaned
    first = sentences[0].strip()
    words = first.split()
    if len(words) > 40:
        return " ".join(words[:40]) + "..."
    if len(sentences) == 1:
        return first
    second = sentences[1].strip()
    if not second:
        return first
    return f"{first} {second}".strip()


def _candidate_key(review: Review) -> tuple:
    return (-review.date.toordinal(), review.rating, review.text.casefold())


def _collapse(value: str) -> str:
    return _WHITESPACE.sub(" ", value).strip()


def _has_alnum(value: str) -> bool:
    return bool(_ALNUM.search(value))
