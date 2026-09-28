"""Write catalog, themes, clusters, and quotes JSON for each stage."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Sequence

from src.catalog import THEMES
from src.cluster import ThemeStats
from src.filter import Review
from src.quotes import Quote

DEFAULT_DIR = Path("data/pulse")


def write_stage_artifacts(
    *,
    output_dir: Path = DEFAULT_DIR,
    window_start: date,
    window_end: date,
    themed_reviews: Sequence[tuple[Review, str | None]],
    theme_stats: Sequence[ThemeStats],
    highlighted: Sequence[ThemeStats],
    other_themes: Sequence[ThemeStats],
    quotes: Sequence[Quote],
) -> dict[str, Path]:
    """Persist each Phase 4 stage. Returns paths written."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    paths = {
        "catalog": output_dir / "catalog.json",
        "themes": output_dir / "themes.json",
        "clusters": output_dir / "clusters.json",
        "quotes": output_dir / "quotes.json",
    }
    paths["catalog"].write_text(
        json.dumps(catalog_payload(), indent=2) + "\n",
        encoding="utf-8",
    )
    paths["themes"].write_text(
        json.dumps(
            themes_payload(
                window_start=window_start,
                window_end=window_end,
                themed_reviews=themed_reviews,
                theme_stats=theme_stats,
                highlighted=highlighted,
                other_themes=other_themes,
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    paths["clusters"].write_text(
        json.dumps(
            clusters_payload(
                window_start=window_start,
                window_end=window_end,
                themed_reviews=themed_reviews,
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    paths["quotes"].write_text(
        json.dumps(
            quotes_payload(
                window_start=window_start,
                window_end=window_end,
                quotes=quotes,
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return paths


def catalog_payload() -> dict:
    return {
        "themes": [
            {"order": index, "name": name, "keywords": list(keywords)}
            for index, (name, keywords) in enumerate(THEMES)
        ]
    }


def themes_payload(
    *,
    window_start: date,
    window_end: date,
    themed_reviews: Sequence[tuple[Review, str | None]],
    theme_stats: Sequence[ThemeStats],
    highlighted: Sequence[ThemeStats],
    other_themes: Sequence[ThemeStats],
) -> dict:
    unthemed = sum(1 for _, theme in themed_reviews if theme is None)
    return {
        "window_start": window_start.isoformat(),
        "window_end": window_end.isoformat(),
        "kept": len(themed_reviews),
        "unthemed": unthemed,
        "ranked": [_theme_dict(item) for item in theme_stats],
        "highlighted": [_theme_dict(item) for item in highlighted],
        "other_themes": [_theme_dict(item) for item in other_themes],
    }


def clusters_payload(
    *,
    window_start: date,
    window_end: date,
    themed_reviews: Sequence[tuple[Review, str | None]],
) -> dict:
    buckets: dict[str, list[dict]] = {}
    unthemed: list[dict] = []
    for review, theme in themed_reviews:
        row = _review_dict(review)
        if theme is None:
            unthemed.append(row)
        else:
            buckets.setdefault(theme, []).append(row)
    return {
        "window_start": window_start.isoformat(),
        "window_end": window_end.isoformat(),
        "clusters": [
            {"theme": theme, "count": len(rows), "reviews": rows}
            for theme, rows in buckets.items()
        ],
        "unthemed": {"count": len(unthemed), "reviews": unthemed},
    }


def quotes_payload(
    *,
    window_start: date,
    window_end: date,
    quotes: Sequence[Quote],
) -> dict:
    return {
        "window_start": window_start.isoformat(),
        "window_end": window_end.isoformat(),
        "quotes": [
            {
                "text": quote.text,
                "store": quote.store,
                "rating": quote.rating,
                "date": quote.date.isoformat(),
                "theme": quote.theme,
            }
            for quote in quotes
        ],
    }


def _theme_dict(item: ThemeStats) -> dict:
    return {
        "name": item.name,
        "count": item.count,
        "avg_rating": format(item.avg_rating, "f"),
        "median_date": item.median_date.isoformat(),
        "catalog_index": item.catalog_index,
    }


def _review_dict(review: Review) -> dict:
    return {
        "store": review.store,
        "rating": review.rating,
        "date": review.date.isoformat(),
        "title": review.title,
        "text": review.text,
    }
