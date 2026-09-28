import csv
import json
from pathlib import Path

import pytest

from src.download import download_export

FIXTURES = Path(__file__).parent / "fixtures"
RUN_DATE = __import__("datetime").date(2026, 9, 28)
RSS_URL = "https://itunes.apple.com/in/rss/customerreviews/page={page}/id=1404871703/sortBy=mostRecent/json"
APPLE_PAGE = (
    "https://apps.apple.com/in/app/groww-stocks-mutual-fund-ipo/id1404871703"
    "?see-all=reviews&platform=iphone"
)
PLAY_PAGE = "https://play.google.com/store/apps/details?id=com.nextbillion.groww&hl=en_IN&gl=IN"


@pytest.fixture(autouse=True)
def block_network(monkeypatch):
    def blocked(*_args, **_kwargs):
        raise AssertionError("network disabled")

    monkeypatch.setattr("urllib.request.urlopen", blocked)


def _product_html() -> str:
    payload = (FIXTURES / "apple_page.json").read_text(encoding="utf-8")
    return f'<html><script id="serialized-server-data" type="application/json">{payload}</script></html>'


def _fetcher(bodies: dict[str, tuple[int, str]]):
    seen: list[str] = []

    def fetch(url: str) -> tuple[int, str]:
        seen.append(url)
        if url not in bodies:
            raise AssertionError(url)
        return bodies[url]

    fetch.seen = seen
    return fetch


def _base_bodies(**overrides) -> dict[str, tuple[int, str]]:
    rss = (FIXTURES / "apple_rss.json").read_text(encoding="utf-8")
    play = (FIXTURES / "play_page.html").read_text(encoding="utf-8")
    bodies = {RSS_URL.format(page=page): (200, '{"feed": {}}') for page in range(1, 11)}
    bodies[RSS_URL.format(page=1)] = (200, rss)
    bodies[APPLE_PAGE] = (200, _product_html())
    bodies[PLAY_PAGE] = (200, play)
    bodies.update(overrides)
    return bodies


def _read_csv(path: Path) -> tuple[list[str], list[dict]]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def _run(tmp_path: Path, bodies: dict[str, tuple[int, str]], **kwargs):
    return download_export(
        window_weeks=12,
        run_date=RUN_DATE,
        fetcher=_fetcher(bodies),
        export_path=tmp_path / "reviews.csv",
        apple_row_fetcher=lambda **_: [],
        play_batch_fetcher=lambda **_: [],
        **kwargs,
    )


def test_rss_keeps_the_in_window_review_and_drops_the_author(tmp_path: Path):
    code = _run(tmp_path, _base_bodies(**{APPLE_PAGE: (200, "<html></html>")}))

    assert code == 0
    header, rows = _read_csv(tmp_path / "reviews.csv")
    assert header == ["store", "rating", "date", "title", "text", "app_id"]
    assert rows == [
        {
            "store": "app_store",
            "rating": "5",
            "date": "2026-09-01",
            "title": "Onboarding",
            "text": "KYC finished quickly",
            "app_id": "1404871703",
        }
    ]
    written = (tmp_path / "reviews.csv").read_text(encoding="utf-8")
    assert "author" not in header
    assert "Should Not Appear" not in written
    assert "This review is old" not in written
    notes = json.loads((tmp_path / "download_notes.json").read_text(encoding="utf-8"))
    assert notes["older_by_store"]["app_store"] == 1
    assert notes["window_start"] == "2026-07-06"
    assert notes["window_end"] == "2026-09-28"
    assert "Should Not Appear" not in json.dumps(notes)


def test_product_page_writes_the_text_and_not_the_reviewer_name(tmp_path: Path):
    empty_rss = {RSS_URL.format(page=1): (200, '{"feed": {}}')}
    code = _run(tmp_path, _base_bodies(**empty_rss))

    assert code == 0
    _header, rows = _read_csv(tmp_path / "reviews.csv")
    assert rows == [
        {
            "store": "app_store",
            "rating": "4",
            "date": "2026-08-16",
            "title": "Payments",
            "text": "UPI payment failed",
            "app_id": "1404871703",
        }
    ]
    written = (tmp_path / "reviews.csv").read_text(encoding="utf-8")
    assert "Hidden Person" not in written
    assert "dateAuthorText" not in written
    notes = json.loads((tmp_path / "download_notes.json").read_text(encoding="utf-8"))
    assert "app store rss returned no reviews" in notes["notes"]
    assert "Hidden Person" not in json.dumps(notes)


def test_play_page_without_reviews_sets_the_note(tmp_path: Path):
    empty = {RSS_URL.format(page=1): (200, '{"feed": {}}'), APPLE_PAGE: (200, "<html></html>")}
    code = _run(tmp_path, _base_bodies(**empty))

    assert code == 0
    _header, rows = _read_csv(tmp_path / "reviews.csv")
    assert rows == []
    notes = json.loads((tmp_path / "download_notes.json").read_text(encoding="utf-8"))
    assert notes["kept_by_store"] == {"app_store": 0, "play": 0}
    assert "play batchexecute rows fetched=0" in notes["notes"]
    assert "product page shelf is missing" in notes["notes"]
    assert "app store rss returned no reviews" in notes["notes"]


def test_window_outside_8_to_12_does_not_write_or_fetch(tmp_path: Path):
    dest = tmp_path / "reviews.csv"
    called = False

    def fetcher(_url: str) -> tuple[int, str]:
        nonlocal called
        called = True
        return 200, ""

    code = download_export(
        window_weeks=6,
        run_date=RUN_DATE,
        fetcher=fetcher,
        export_path=dest,
        apple_row_fetcher=lambda **_: (_ for _ in ()).throw(AssertionError("no apple")),
        play_batch_fetcher=lambda **_: (_ for _ in ()).throw(AssertionError("no play")),
    )

    assert code == 1
    assert called is False
    assert not dest.exists()


def test_retries_a_server_error_once(tmp_path: Path):
    rss = (FIXTURES / "apple_rss.json").read_text(encoding="utf-8")
    page = RSS_URL.format(page=1)
    calls = {page: 0}

    def fetcher(url: str) -> tuple[int, str]:
        if url == page:
            calls[page] += 1
            if calls[page] == 1:
                return 503, ""
            return 200, rss
        if "page=" in url:
            return 200, '{"feed": {}}'
        if url == APPLE_PAGE or "see-all=reviews" in url:
            return 200, "<html></html>"
        if url == PLAY_PAGE:
            return 200, (FIXTURES / "play_page.html").read_text(encoding="utf-8")
        raise AssertionError(url)

    code = download_export(
        window_weeks=12,
        run_date=RUN_DATE,
        fetcher=fetcher,
        export_path=tmp_path / "reviews.csv",
        apple_row_fetcher=lambda **_: [],
        play_batch_fetcher=lambda **_: [],
    )

    assert code == 0
    assert calls[page] == 2
    _header, rows = _read_csv(tmp_path / "reviews.csv")
    assert len(rows) == 1


def test_every_failed_source_leaves_the_existing_csv(tmp_path: Path):
    dest = tmp_path / "reviews.csv"
    dest.write_text("keep me\n", encoding="utf-8")

    def fetcher(_url: str) -> tuple[int, str]:
        return 404, ""

    def boom(**_kwargs):
        raise RuntimeError("offline")

    code = download_export(
        window_weeks=12,
        run_date=RUN_DATE,
        fetcher=fetcher,
        export_path=dest,
        apple_row_fetcher=boom,
        play_batch_fetcher=boom,
    )

    assert code == 1
    assert dest.read_text(encoding="utf-8") == "keep me\n"


def test_play_is_requested_once(tmp_path: Path):
    fetcher = _fetcher(_base_bodies())
    download_export(
        window_weeks=12,
        run_date=RUN_DATE,
        fetcher=fetcher,
        export_path=tmp_path / "reviews.csv",
        apple_row_fetcher=lambda **_: [],
        play_batch_fetcher=lambda **_: [],
    )

    play_calls = [url for url in fetcher.seen if "play.google.com" in url]
    assert play_calls == [PLAY_PAGE]


def test_itunes_and_play_batch_rows_are_kept(tmp_path: Path):
    code = download_export(
        window_weeks=12,
        run_date=RUN_DATE,
        fetcher=_fetcher(_base_bodies(**{RSS_URL.format(page=1): (200, '{"feed": {}}'), APPLE_PAGE: (200, "<html></html>")})),
        export_path=tmp_path / "reviews.csv",
        apple_row_fetcher=lambda **_: [
            {
                "store": "app_store",
                "rating": "2",
                "date": "2026-09-10",
                "title": "Login",
                "text": "OTP failed on Groww",
                "app_id": "1404871703",
            }
        ],
        play_batch_fetcher=lambda **_: [
            {
                "store": "play",
                "rating": "5",
                "date": "2026-09-11",
                "title": "",
                "text": "SIP works well",
                "app_id": "com.nextbillion.groww",
            }
        ],
    )

    assert code == 0
    _header, rows = _read_csv(tmp_path / "reviews.csv")
    assert [(r["store"], r["text"]) for r in rows] == [
        ("app_store", "OTP failed on Groww"),
        ("play", "SIP works well"),
    ]
