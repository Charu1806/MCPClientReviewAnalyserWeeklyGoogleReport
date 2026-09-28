import json
from pathlib import Path

import pytest

from src.load import LoadError, load_export

FIXTURES = Path(__file__).parent / "fixtures"


def test_bom_aliases_and_identity_columns_are_dropped():
    rows = load_export(FIXTURES / "aliases_bom.csv")

    assert len(rows) == 2
    assert rows[0] == {
        "store": "App Store",
        "rating": "5",
        "date": "2026-09-01",
        "text": "KYC took a day",
        "title": "Onboarding",
        "app_id": "",
    }
    assert rows[1]["text"] == "UPI failed twice"
    assert rows[1]["title"] == "UPI failed twice"
    for row in rows:
        assert "author" not in row
        assert "userName" not in row
        assert "email" not in row
        assert "Ada" not in row.values()
        assert "ada@example.com" not in row.values()


def test_json_object_with_one_list_uses_aliases():
    rows = load_export(FIXTURES / "wrapped.json")

    assert rows == [
        {
            "store": "google play",
            "rating": "3",
            "date": "2026-07-06T05:01:36-07:00",
            "text": "Login   with OTP failed",
            "title": "OTP",
            "app_id": "com.nextbillion.groww",
        }
    ]
    assert "hidden@example.com" not in rows[0].values()


def test_header_only_csv_returns_no_rows():
    assert load_export(FIXTURES / "header_only.csv") == []


def test_empty_file_returns_no_rows(tmp_path: Path):
    path = tmp_path / "empty.csv"
    path.write_text("", encoding="utf-8")

    assert load_export(path) == []


def test_missing_path_names_the_path(tmp_path: Path):
    path = tmp_path / "missing.csv"

    with pytest.raises(LoadError, match="missing.csv"):
        load_export(path)


def test_directory_and_wrong_suffix_raise(tmp_path: Path):
    with pytest.raises(LoadError, match="not a file"):
        load_export(tmp_path)

    notes = tmp_path / "notes.txt"
    notes.write_text("hello", encoding="utf-8")
    with pytest.raises(LoadError, match="notes.txt"):
        load_export(notes)


def test_missing_date_column_names_the_field(tmp_path: Path):
    path = tmp_path / "reviews.csv"
    path.write_text("store,rating,text\nplay,5,Hello\n", encoding="utf-8")

    with pytest.raises(LoadError, match="missing field: date"):
        load_export(path)


def test_json_with_two_values_raises(tmp_path: Path):
    path = tmp_path / "reviews.json"
    path.write_text(json.dumps({"a": [], "b": []}), encoding="utf-8")

    with pytest.raises(LoadError, match="JSON must be a list"):
        load_export(path)
