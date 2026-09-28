from datetime import date
from decimal import Decimal

from src.brief import Draft, build_brief, prompt_payload, render_header
from src.cluster import ThemeStats
from src.filter import FilterResult, Review
from src.quotes import Quote


def _stats(name: str, count: int, avg: str, day: date, index: int) -> ThemeStats:
    return ThemeStats(
        name=name,
        count=count,
        avg_rating=Decimal(avg),
        median_date=day,
        catalog_index=index,
    )


def _filtered(**overrides) -> FilterResult:
    data = {
        "kept": [
            Review("play", 1, date(2026, 9, 1), "KYC failed", ""),
            Review("play", 2, date(2026, 9, 2), "SIP payment failed", ""),
            Review("app_store", 1, date(2026, 9, 3), "OTP login locked", ""),
        ],
        "dropped": {
            "empty": 0,
            "bad_date": 0,
            "bad_rating": 0,
            "bad_store": 0,
            "out_of_window": 2,
            "duplicate": 1,
            "wrong_app": 0,
        },
        "missing_stores": [],
        "stores_empty_in_window": [],
        "window_start": date(2026, 7, 6),
        "window_end": date(2026, 9, 28),
        "actual_start": date(2026, 9, 1),
        "actual_end": date(2026, 9, 3),
        "stop_reason": "",
    }
    data.update(overrides)
    return FilterResult(**data)


def test_normal_payload_has_no_recipient_and_only_selected_quotes():
    highlighted = [
        _stats("Onboarding and KYC", 1, "1.0", date(2026, 9, 1), 0),
        _stats("SIP and payments", 1, "2.0", date(2026, 9, 2), 1),
        _stats("Login and access", 1, "1.0", date(2026, 9, 3), 2),
    ]
    quotes = [
        Quote("KYC failed", "play", 1, date(2026, 9, 1), "Onboarding and KYC"),
        Quote("SIP payment failed", "play", 2, date(2026, 9, 2), "SIP and payments"),
        Quote("OTP login locked", "app_store", 1, date(2026, 9, 3), "Login and access"),
    ]
    brief = build_brief(
        filtered=_filtered(),
        run_date=date(2026, 9, 28),
        highlighted=highlighted,
        other_themes=[],
        quotes=quotes,
        unthemed=0,
        loaded_count=6,
    )
    payload = prompt_payload(brief)

    assert "recipient" not in payload
    assert "PULSE_RECIPIENT" not in str(payload)
    assert payload["note_mode"] == "normal"
    assert payload["quotes"] == [
        {
            "text": "KYC failed",
            "store": "play",
            "rating": 1,
            "date": "2026-09-01",
            "theme": "Onboarding and KYC",
        },
        {
            "text": "SIP payment failed",
            "store": "play",
            "rating": 2,
            "date": "2026-09-02",
            "theme": "SIP and payments",
        },
        {
            "text": "OTP login locked",
            "store": "app_store",
            "rating": 1,
            "date": "2026-09-03",
            "theme": "Login and access",
        },
    ]
    assert "raw" not in payload
    header = render_header(brief)
    assert "Groww — Weekly Review Pulse — week ending 2026-09-28" in header
    assert "Dropped out of window: 2" in header
    assert "Dropped duplicates: 1" in header


def test_empty_export_mode():
    brief = build_brief(
        filtered=_filtered(
            kept=[],
            actual_start=None,
            actual_end=None,
            missing_stores=["app_store", "play"],
            dropped={
                "empty": 0,
                "bad_date": 0,
                "bad_rating": 0,
                "bad_store": 0,
                "out_of_window": 0,
                "duplicate": 0,
                "wrong_app": 0,
            },
        ),
        run_date=date(2026, 9, 28),
        highlighted=[],
        other_themes=[],
        quotes=[],
        unthemed=0,
        loaded_count=0,
    )
    assert brief.note_mode == "empty_export"
    assert "No reviews in this export." in brief.shortfalls


def test_wrong_app_mode():
    brief = build_brief(
        filtered=_filtered(
            kept=[],
            actual_start=None,
            actual_end=None,
            dropped={
                "empty": 0,
                "bad_date": 0,
                "bad_rating": 0,
                "bad_store": 0,
                "out_of_window": 0,
                "duplicate": 0,
                "wrong_app": 4,
            },
        ),
        run_date=date(2026, 9, 28),
        highlighted=[],
        other_themes=[],
        quotes=[],
        unthemed=0,
        loaded_count=4,
    )
    assert brief.note_mode == "wrong_app"
