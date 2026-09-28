from datetime import date
from pathlib import Path

from src.filter import filter_reviews
from src.load import load_export

FIXTURES = Path(__file__).parent / "fixtures"
RUN_DATE = date(2026, 9, 28)


def _row(**overrides) -> dict:
    row = {
        "store": "app_store",
        "rating": "5",
        "date": "2026-09-01",
        "text": "KYC took a day",
        "title": "Onboarding",
        "app_id": "1404871703",
    }
    row.update(overrides)
    return row


def test_twelve_week_bounds_end_on_the_run_date():
    result = filter_reviews([], window_weeks=12, run_date=RUN_DATE)

    assert result.window_start == date(2026, 7, 6)
    assert result.window_end == RUN_DATE
    assert result.stop_reason == ""
    assert result.actual_start is None
    assert result.actual_end is None


def test_ambiguous_date_stops_and_keeps_nothing():
    rows = load_export(FIXTURES / "ambiguous.csv")
    result = filter_reviews(rows, window_weeks=12, run_date=RUN_DATE)

    assert result.stop_reason == "ambiguous_date"
    assert result.kept == []
    assert result.dropped["duplicate"] == 0


def test_duplicate_is_counted_once_and_wrong_app_is_dropped():
    rows = load_export(FIXTURES / "kept_rows.csv")
    result = filter_reviews(rows, window_weeks=12, run_date=RUN_DATE)

    assert result.stop_reason == ""
    assert result.dropped["duplicate"] == 1
    assert result.dropped["wrong_app"] == 1
    assert [(review.store, review.text) for review in result.kept] == [
        ("app_store", "KYC took a day"),
        ("play", "Statement downloaded"),
    ]
    assert result.kept[0].rating == 5
    assert result.kept[0].date == date(2026, 9, 1)


def test_boundary_dates_are_kept_and_the_day_before_is_not():
    rows = [
        _row(date="2026-07-06", text="Window start"),
        _row(date="2026-09-28", text="Window end"),
        _row(date="2026-07-05", text="Too old"),
        _row(date="2026-09-29", text="Future"),
    ]
    result = filter_reviews(rows, window_weeks=12, run_date=RUN_DATE)

    assert [review.text for review in result.kept] == ["Window start", "Window end"]
    assert result.dropped["out_of_window"] == 2


def test_iso_datetime_and_english_month_names():
    rows = [
        _row(date="2026-08-01T05:01:36-07:00", text="ISO clock"),
        _row(date="28 September 2026", text="Long month"),
        _row(date="Sep 2, 2026", text="Short month"),
        _row(date="2 Aug 2026", text="Day month"),
    ]
    result = filter_reviews(rows, window_weeks=12, run_date=RUN_DATE)

    assert [review.date for review in result.kept] == [
        date(2026, 8, 1),
        date(2026, 9, 28),
        date(2026, 9, 2),
        date(2026, 8, 2),
    ]


def test_non_integer_ratings_are_dropped():
    rows = [
        _row(rating="5 stars", text="Words"),
        _row(rating="5.0", text="Decimal"),
        _row(rating="0", text="Zero"),
    ]
    result = filter_reviews(rows, window_weeks=12, run_date=RUN_DATE)

    assert result.kept == []
    assert result.dropped["bad_rating"] == 3


def test_same_words_on_both_stores_are_both_kept():
    rows = [
        _row(store="app_store", text="SIP failed"),
        _row(store="google play", text="SIP failed"),
    ]
    result = filter_reviews(rows, window_weeks=12, run_date=RUN_DATE)

    assert [review.store for review in result.kept] == ["app_store", "play"]
    assert result.dropped["duplicate"] == 0


def test_missing_store_and_store_empty_in_the_window():
    rows = [
        _row(store="ios", date="2026-09-01", text="Only apple"),
        _row(store="play", date="2026-01-01", text="Old play review"),
    ]
    result = filter_reviews(rows, window_weeks=12, run_date=RUN_DATE)

    assert result.missing_stores == []
    assert result.stores_empty_in_window == ["play"]
    assert result.dropped["out_of_window"] == 1
    assert len(result.kept) == 1


def test_file_with_only_one_store_names_the_other():
    result = filter_reviews([_row(store="app store")], window_weeks=12, run_date=RUN_DATE)

    assert result.missing_stores == ["play"]
    assert result.stores_empty_in_window == []


def test_window_outside_range_stops_when_the_span_is_eight_weeks_or_more():
    rows = [
        _row(date="2026-01-01", text="January"),
        _row(date="2026-09-01", text="September"),
    ]
    result = filter_reviews(rows, window_weeks=16, run_date=RUN_DATE)

    assert result.stop_reason == "window"
    assert result.kept == []


def test_short_export_continues_when_the_configured_window_is_outside_range():
    rows = [
        _row(date="2026-09-01", text="First"),
        _row(date="2026-09-03", text="Second"),
    ]
    result = filter_reviews(rows, window_weeks=4, run_date=RUN_DATE)

    assert result.stop_reason == ""
    assert result.actual_start == date(2026, 9, 1)
    assert result.actual_end == date(2026, 9, 3)
    assert len(result.kept) == 2


def test_every_date_unparseable_stops():
    rows = [_row(date="yesterday", text="No date"), _row(date="n/a", text="Also none")]
    result = filter_reviews(rows, window_weeks=12, run_date=RUN_DATE)

    assert result.stop_reason == "unparseable_dates"
    assert result.kept == []
    assert result.dropped["bad_date"] == 2
