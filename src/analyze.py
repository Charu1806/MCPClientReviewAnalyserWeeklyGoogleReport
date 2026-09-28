"""Run theme clustering and write catalog/themes/clusters/quotes JSON."""

from __future__ import annotations

import argparse
import os
from datetime import date
from pathlib import Path

from src.artifacts import DEFAULT_DIR, write_stage_artifacts
from src.cluster import highlight, rank, theme_reviews
from src.config import load_config
from src.filter import filter_reviews
from src.load import LoadError, load_export
from src.quotes import select_quotes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Cluster reviews and write stage JSON.")
    parser.add_argument("--export", help="Path to reviews.csv")
    parser.add_argument("--run-date", help="YYYY-MM-DD. Defaults to today.")
    parser.add_argument(
        "--out",
        default=str(DEFAULT_DIR),
        help="Directory for catalog/themes/clusters/quotes JSON.",
    )
    args = parser.parse_args(argv)
    _load_dotenv()
    config = load_config(os.environ)

    export_path = Path(args.export) if args.export else config.export_path
    if args.run_date:
        try:
            run_date = date.fromisoformat(args.run_date)
        except ValueError:
            print("invalid --run-date; use YYYY-MM-DD")
            return 1
    else:
        run_date = config.run_date

    try:
        rows = load_export(export_path)
    except LoadError as exc:
        print(exc)
        return 1

    filtered = filter_reviews(rows, window_weeks=config.window_weeks, run_date=run_date)
    if filtered.stop_reason:
        print(f"filter stopped: {filtered.stop_reason}")
        return 1

    themed = theme_reviews(filtered.kept)
    stats = rank(themed)
    top, other = highlight(stats)
    quotes = select_quotes(themed, top)
    paths = write_stage_artifacts(
        output_dir=Path(args.out),
        window_start=filtered.window_start,
        window_end=filtered.window_end,
        themed_reviews=themed,
        theme_stats=stats,
        highlighted=top,
        other_themes=other,
        quotes=quotes,
    )
    for name, path in paths.items():
        print(f"{name}: {path}")
    print(f"kept={len(filtered.kept)} themes={len(stats)} quotes={len(quotes)}")
    return 0


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv()


if __name__ == "__main__":
    raise SystemExit(main())
