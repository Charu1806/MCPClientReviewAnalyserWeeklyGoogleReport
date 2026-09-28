import json
from datetime import date
from pathlib import Path

from src.artifacts import write_stage_artifacts
from src.cluster import highlight, rank, theme_reviews
from src.filter import Review
from src.quotes import select_quotes


def _review(**overrides) -> Review:
    data = {
        "store": "play",
        "rating": 2,
        "date": date(2026, 9, 1),
        "text": "KYC failed",
        "title": "",
    }
    data.update(overrides)
    return Review(**data)


def test_writes_four_stage_files(tmp_path: Path):
    reviews = [
        _review(text="KYC failed", rating=1, date=date(2026, 9, 5)),
        _review(text="SIP payment failed", rating=2, date=date(2026, 9, 4)),
        _review(text="OTP login locked", rating=1, date=date(2026, 9, 3)),
    ]
    themed = theme_reviews(reviews)
    stats = rank(themed)
    top, other = highlight(stats)
    quotes = select_quotes(themed, top)

    paths = write_stage_artifacts(
        output_dir=tmp_path,
        window_start=date(2026, 7, 6),
        window_end=date(2026, 9, 28),
        themed_reviews=themed,
        theme_stats=stats,
        highlighted=top,
        other_themes=other,
        quotes=quotes,
    )

    assert set(paths) == {"catalog", "themes", "clusters", "quotes"}
    catalog = json.loads(paths["catalog"].read_text(encoding="utf-8"))
    themes = json.loads(paths["themes"].read_text(encoding="utf-8"))
    clusters = json.loads(paths["clusters"].read_text(encoding="utf-8"))
    quotes_json = json.loads(paths["quotes"].read_text(encoding="utf-8"))

    assert catalog["themes"][0]["name"] == "Onboarding and KYC"
    assert "keywords" in catalog["themes"][0]
    assert themes["kept"] == 3
    assert themes["highlighted"][0]["name"]
    assert clusters["clusters"]
    assert "reviews" in clusters["clusters"][0]
    assert quotes_json["quotes"]
    assert "text" in quotes_json["quotes"][0]
