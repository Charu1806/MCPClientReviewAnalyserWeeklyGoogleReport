"""Assign themes and rank them. Deterministic. No model calls."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Sequence

from src.catalog import THEME_INDEX, THEME_NAMES, keyword_hits
from src.filter import Review


@dataclass(frozen=True)
class ThemeStats:
    name: str
    count: int
    avg_rating: Decimal
    median_date: date
    catalog_index: int


def assign(review: Review) -> str | None:
    """Pick one primary theme, or None when unthemed. Rating is ignored."""
    blob = f"{review.title} {review.text}".strip()
    if not blob:
        return None
    hits = keyword_hits(blob)
    best_name: str | None = None
    best_count = 0
    for name in THEME_NAMES:
        count = len(hits[name])
        if count > best_count:
            best_name = name
            best_count = count
        elif count == best_count and count > 0:
            # Earlier catalog theme wins on a tie.
            if best_name is None or THEME_INDEX[name] < THEME_INDEX[best_name]:
                best_name = name
    return best_name if best_count > 0 else None


def theme_reviews(reviews: Sequence[Review]) -> list[tuple[Review, str | None]]:
    return [(review, assign(review)) for review in reviews]


def rank(themed_reviews: Sequence[tuple[Review, str | None]]) -> list[ThemeStats]:
    """Return themes with at least one review, sorted for the pulse."""
    buckets: dict[str, list[Review]] = {name: [] for name in THEME_NAMES}
    for review, theme in themed_reviews:
        if theme is None:
            continue
        buckets[theme].append(review)

    stats: list[ThemeStats] = []
    for name in THEME_NAMES:
        group = buckets[name]
        if not group:
            continue
        ratings = [review.rating for review in group]
        dates = sorted(review.date for review in group)
        mean = (Decimal(sum(ratings)) / Decimal(len(ratings))).quantize(
            Decimal("0.1"), rounding=ROUND_HALF_UP
        )
        stats.append(
            ThemeStats(
                name=name,
                count=len(group),
                avg_rating=mean,
                median_date=_upper_median(dates),
                catalog_index=THEME_INDEX[name],
            )
        )

    stats.sort(
        key=lambda item: (
            -item.count,
            item.avg_rating,
            -item.median_date.toordinal(),
            item.catalog_index,
        )
    )
    return stats


def highlight(stats: Sequence[ThemeStats]) -> tuple[list[ThemeStats], list[ThemeStats]]:
    """Top three themes, then the rest."""
    ordered = list(stats)
    return ordered[:3], ordered[3:]


def _upper_median(dates: list[date]) -> date:
    if not dates:
        raise ValueError("median of empty dates")
    mid = len(dates) // 2
    if len(dates) % 2 == 1:
        return dates[mid]
    # Even count: later of the two central dates.
    return dates[mid]
