"""Download public App Store and Play reviews into data/exports/reviews.csv."""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from src.config import load_config

_RSS_URL = (
    "https://itunes.apple.com/in/rss/customerreviews/page={page}/id=1404871703/sortBy=mostRecent/json"
)
_APPLE_PAGE_URL = "https://apps.apple.com/in/app/groww-stocks-mutual-fund-ipo/id1404871703"
_APPLE_REVIEWS_URL = (
    "https://apps.apple.com/in/app/groww-stocks-mutual-fund-ipo/id1404871703"
    "?see-all=reviews&platform=iphone"
)
_APPLE_ROW_URL = "https://itunes.apple.com/WebObjects/MZStore.woa/wa/userReviewsRow"
_APPLE_STORE_FRONT = "143467-2,29"  # India
_PLAY_PAGE_URL = "https://play.google.com/store/apps/details?id=com.nextbillion.groww&hl=en_IN&gl=IN"
_PLAY_BATCH_URL = "https://play.google.com/_/PlayStoreUi/data/batchexecute?hl=en&gl=in"
_APP_STORE_ID = "1404871703"
_PLAY_ID = "com.nextbillion.groww"
_COLUMNS = ("store", "rating", "date", "title", "text", "app_id")
_USER_AGENT = "GrowwReviewPulse/1.0"
_ITUNES_UA = "iTunes/12.11.3 (Macintosh; OS X 10.15.7) AppleWebKit/605.1.15"
_BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
)
_TIMEOUT_SECONDS = 20
_PLAY_NOTE = "public page has no review list"
_SHELF_NOTE = "product page shelf is missing"
_EMPTY_RSS_NOTE = "app store rss returned no reviews"
_WHITESPACE = re.compile(r"\s+")
_SHELF_SCRIPT = re.compile(
    r'<script[^>]*id="serialized-server-data"[^>]*>(.*?)</script>',
    re.DOTALL,
)
_PLAY_TEXT_KEYS = ("text", "content", "reviewBody", "comment")
_NAME_KEYS = {"reviewername", "reviewer", "author", "username", "name", "dateauthortext"}
_APPLE_PAGE_SIZE = 25
_APPLE_MAX_PAGES = 40
_PLAY_PAGE_SIZE = 100
_PLAY_MAX_PAGES = 200
_PLAY_SORT_NEWEST = 2


class TemporaryError(Exception):
    """A timeout or HTTP 5xx. The caller retries once."""


def main(argv: list[str] | None = None, *, fetcher=None) -> int:
    parser = argparse.ArgumentParser(description="Download public store reviews.")
    parser.add_argument("--run-date", help="YYYY-MM-DD. Defaults to today.")
    args = parser.parse_args(argv)
    _load_dotenv()
    config = load_config(os.environ)
    if args.run_date:
        try:
            run_date = date.fromisoformat(args.run_date)
        except ValueError:
            print("invalid --run-date; use YYYY-MM-DD")
            return 1
    else:
        run_date = config.run_date
    return download_export(
        window_weeks=config.window_weeks,
        run_date=run_date,
        fetcher=fetcher or urlopen_fetch,
        export_path=config.export_path,
    )


def download_export(
    *,
    window_weeks: int,
    run_date: date,
    fetcher,
    export_path: Path,
    apple_row_fetcher=None,
    play_batch_fetcher=None,
) -> int:
    if window_weeks not in range(8, 13):
        print("PULSE_WINDOW_WEEKS must be from 8 to 12")
        return 1

    window_start = run_date - timedelta(days=window_weeks * 7)
    window_end = run_date
    notes: list[str] = []
    errors: list[str] = []
    parsed: list[dict] = []
    apple_ok = False
    play_ok = False

    # App Store: iTunes userReviewsRow (paginated), then RSS, then see-all page.
    row_fetch = apple_row_fetcher or fetch_apple_itunes_rows
    try:
        apple_rows = row_fetch(window_start=window_start, window_end=window_end)
        parsed.extend(apple_rows)
        apple_ok = True
        notes.append(f"app store itunes rows fetched={len(apple_rows)}")
    except Exception as exc:
        errors.append(f"app store itunes rows failed: {exc}")

    rss_rows, rss_failed, rss_notes = _fetch_rss(fetcher, window_start)
    parsed.extend(rss_rows)
    notes.extend(rss_notes)
    if rss_failed:
        errors.append(rss_failed)
    elif rss_rows:
        apple_ok = True

    page_body, page_error = _fetch_text(_APPLE_REVIEWS_URL, fetcher)
    if page_error:
        page_body, page_error = _fetch_text(_APPLE_PAGE_URL, fetcher)
    if page_error:
        errors.append(page_error)
        notes.append(_SHELF_NOTE)
    else:
        page_rows, shelf_note = parse_product_page(page_body or "")
        parsed.extend(page_rows)
        if page_rows:
            apple_ok = True
        if shelf_note:
            notes.append(shelf_note)

    # Play: batchexecute UsvDTd (paginated), then public details page fallback.
    batch_fetch = play_batch_fetcher or fetch_play_batchexecute_rows
    try:
        play_rows = batch_fetch(window_start=window_start, window_end=window_end)
        parsed.extend(play_rows)
        play_ok = True
        notes.append(f"play batchexecute rows fetched={len(play_rows)}")
    except Exception as exc:
        errors.append(f"play batchexecute failed: {exc}")

    play_body, play_error = _fetch_text(_PLAY_PAGE_URL, fetcher)
    if play_error:
        errors.append(play_error)
        if not play_ok:
            notes.append(_PLAY_NOTE)
    else:
        html_rows, play_note = parse_play_page(play_body or "")
        parsed.extend(html_rows)
        if html_rows:
            play_ok = True
        if play_note and not play_ok:
            notes.append(play_note)

    export_path = Path(export_path)
    notes_path = export_path.parent / "download_notes.json"
    if not apple_ok and not play_ok:
        _write_notes(notes_path, window_start, window_end, [], notes, errors)
        print("every review source failed")
        return 1

    kept, older = _select(parsed, window_start, window_end)
    _write_csv(export_path, kept)
    _write_notes(notes_path, window_start, window_end, kept, notes, errors, older)
    return 0


def urlopen_fetch(url: str) -> tuple[int, str]:
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
            return response.status, response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return exc.code, body
    except (urllib.error.URLError, TimeoutError, socket.timeout) as exc:
        raise TemporaryError(url) from exc


def fetch_apple_itunes_rows(*, window_start: date, window_end: date) -> list[dict]:
    """Paginate Apple's public iTunes userReviewsRow feed for India."""
    rows: list[dict] = []
    for page in range(_APPLE_MAX_PAGES):
        start = page * _APPLE_PAGE_SIZE
        end = start + _APPLE_PAGE_SIZE - 1
        params = {
            "id": _APP_STORE_ID,
            "displayable-kind": "11",
            "startIndex": str(start),
            "endIndex": str(end),
            "sort": "4",
            "appVersion": "all",
        }
        url = _APPLE_ROW_URL + "?" + urllib.parse.urlencode(params)
        body = _http_get(
            url,
            headers={
                "User-Agent": _ITUNES_UA,
                "X-Apple-Store-Front": _APPLE_STORE_FRONT,
                "Accept": "application/json",
            },
        )
        try:
            payload = json.loads(body)
        except json.JSONDecodeError as exc:
            raise RuntimeError("invalid itunes reviews JSON") from exc
        items = payload.get("userReviewList") or []
        if not items:
            break
        page_dates: list[date] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            parsed = _review(
                store="app_store",
                rating=item.get("rating"),
                title=str(item.get("title") or ""),
                text=str(item.get("body") or ""),
                raw_date=str(item.get("date") or ""),
                app_id=_APP_STORE_ID,
            )
            if not parsed:
                continue
            rows.append(parsed)
            page_dates.append(date.fromisoformat(parsed["date"]))
        if page_dates and min(page_dates) < window_start:
            break
    return rows


def fetch_play_batchexecute_rows(*, window_start: date, window_end: date) -> list[dict]:
    """Paginate Play's public UsvDTd batchexecute reviews RPC for India."""
    rows: list[dict] = []
    token = None
    for _page in range(_PLAY_MAX_PAGES):
        payload = [
            None,
            None,
            [2, _PLAY_SORT_NEWEST, [_PLAY_PAGE_SIZE, None, token], None, []],
            [_PLAY_ID, 7],
        ]
        form = urllib.parse.urlencode(
            {"f.req": json.dumps([[["UsvDTd", json.dumps(payload), None, "generic"]]])}
        ).encode()
        body = _http_post(
            _PLAY_BATCH_URL,
            form,
            headers={
                "User-Agent": _BROWSER_UA,
                "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
                "Origin": "https://play.google.com",
                "Referer": (
                    f"https://play.google.com/store/apps/details?id={_PLAY_ID}&hl=en&gl=in"
                ),
            },
        )
        items, token = parse_play_batchexecute(body)
        if not items:
            break
        page_dates: list[date] = []
        for item in items:
            parsed = _review(
                store="play",
                rating=item["rating"],
                title="",
                text=item["text"],
                raw_date=item["date"],
                app_id=_PLAY_ID,
            )
            if not parsed:
                continue
            rows.append(parsed)
            page_dates.append(date.fromisoformat(parsed["date"]))
        if page_dates and min(page_dates) < window_start:
            break
        if not token:
            break
    return rows


def parse_play_batchexecute(body: str) -> tuple[list[dict], str | None]:
    text = body.lstrip()
    if text.startswith(")]}'"):
        text = text[4:].lstrip()
    try:
        outer = json.loads(text)
    except json.JSONDecodeError:
        return [], None
    data_str = None
    for row in outer:
        if isinstance(row, list) and len(row) >= 3 and row[0] == "wrb.fr" and row[1] == "UsvDTd":
            data_str = row[2]
            break
    if not data_str:
        return [], None
    try:
        data = json.loads(data_str)
    except json.JSONDecodeError:
        return [], None
    items = data[0] if isinstance(data, list) and data else []
    reviews: list[dict] = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, list) or len(item) < 5:
            continue
        rating = item[2] if isinstance(item[2], int) else None
        text_body = item[4] if isinstance(item[4], str) else ""
        stamp = None
        if isinstance(item[5], list) and item[5] and isinstance(item[5][0], (int, float)):
            stamp = int(item[5][0])
        elif isinstance(item[5], (int, float)):
            stamp = int(item[5])
        if rating is None or not text_body.strip() or stamp is None:
            continue
        reviews.append(
            {
                "rating": rating,
                "text": text_body,
                "date": datetime.fromtimestamp(stamp, tz=timezone.utc).date().isoformat(),
            }
        )
    token = None
    try:
        if isinstance(data[1], list) and len(data[1]) > 1 and isinstance(data[1][1], str):
            token = data[1][1]
    except (IndexError, TypeError):
        token = None
    return reviews, token


def parse_rss(body: str) -> list[dict]:
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return []
    entry = (payload.get("feed") or {}).get("entry")
    if entry is None:
        return []
    entries = entry if isinstance(entry, list) else [entry]
    reviews = []
    for item in entries:
        if not isinstance(item, dict):
            continue
        rating = _label(item.get("im:rating"))
        if rating is None:
            continue
        parsed = _review(
            store="app_store",
            rating=rating,
            title=_label(item.get("title")) or "",
            text=_label(item.get("content")) or "",
            raw_date=_label(item.get("updated")) or "",
            app_id=_APP_STORE_ID,
        )
        if parsed:
            reviews.append(parsed)
    return reviews


def parse_product_page(html: str) -> tuple[list[dict], str | None]:
    match = _SHELF_SCRIPT.search(html)
    if not match:
        return [], _SHELF_NOTE
    try:
        payload = json.loads(match.group(1))
    except json.JSONDecodeError:
        return [], _SHELF_NOTE
    reviews: list[dict] = []
    _collect_apple_shelf_reviews(payload, reviews)
    if not reviews:
        return [], _SHELF_NOTE
    return reviews, None


def _collect_apple_shelf_reviews(node, found: list[dict]) -> None:
    if isinstance(node, dict):
        if {"rating", "contents", "date"} <= set(node.keys()):
            parsed = _review(
                store="app_store",
                rating=node.get("rating"),
                title=str(node.get("title") or ""),
                text=str(node.get("contents") or ""),
                raw_date=str(node.get("date") or ""),
                app_id=_APP_STORE_ID,
            )
            if parsed:
                found.append(parsed)
        for key, value in node.items():
            if key.lower() in _NAME_KEYS:
                continue
            _collect_apple_shelf_reviews(value, found)
    elif isinstance(node, list):
        for value in node:
            _collect_apple_shelf_reviews(value, found)


def parse_play_page(html: str) -> tuple[list[dict], str | None]:
    reviews: list[dict] = []
    for script in re.findall(r"<script[^>]*>(.*?)</script>", html, re.DOTALL):
        script = script.strip()
        if not script.startswith("{") and not script.startswith("["):
            continue
        try:
            payload = json.loads(script)
        except json.JSONDecodeError:
            continue
        _collect_play_reviews(payload, reviews)
    if not reviews:
        return [], _PLAY_NOTE
    return reviews, None


def _collect_play_reviews(node, found: list[dict]) -> None:
    if isinstance(node, dict):
        text = next(
            (
                node[key]
                for key in _PLAY_TEXT_KEYS
                if isinstance(node.get(key), str) and node[key].strip()
            ),
            None,
        )
        raw_date = node.get("date") if isinstance(node.get("date"), str) else None
        if text and raw_date and _rating_text(node.get("rating")) is not None:
            parsed = _review(
                store="play",
                rating=node.get("rating"),
                title=str(node.get("title") or ""),
                text=text,
                raw_date=raw_date,
                app_id=_PLAY_ID,
            )
            if parsed:
                found.append(parsed)
        for key, value in node.items():
            if key.lower() in _NAME_KEYS:
                continue
            _collect_play_reviews(value, found)
    elif isinstance(node, list):
        for value in node:
            _collect_play_reviews(value, found)


def _fetch_rss(fetcher, window_start: date) -> tuple[list[dict], str | None, list[str]]:
    collected: list[dict] = []
    for page in range(1, 11):
        body, error = _fetch_text(_RSS_URL.format(page=page), fetcher)
        if error:
            return collected, error, []
        page_rows = parse_rss(body or "")
        if not page_rows:
            notes = [_EMPTY_RSS_NOTE] if page == 1 else []
            return collected, None, notes
        newest = max(row["date"] for row in page_rows)
        if newest < window_start.isoformat():
            return collected + page_rows, None, []
        collected.extend(page_rows)
    return collected, None, []


def _fetch_text(url: str, fetcher) -> tuple[str | None, str | None]:
    last_error = f"temporary failure for {url}"
    for _attempt in range(2):
        try:
            status, body = fetcher(url)
        except TemporaryError:
            continue
        if status >= 500:
            last_error = f"HTTP {status} for {url}"
            continue
        if status >= 400:
            return None, f"HTTP {status} for {url}"
        return body, None
    return None, last_error


def _http_get(url: str, *, headers: dict[str, str]) -> str:
    last_error: Exception | None = None
    for _attempt in range(2):
        request = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
                return response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            if exc.code >= 500:
                last_error = TemporaryError(url)
                continue
            raise RuntimeError(f"HTTP {exc.code} for {url}") from exc
        except (urllib.error.URLError, TimeoutError, socket.timeout) as exc:
            last_error = TemporaryError(url)
            continue
    raise RuntimeError(f"temporary failure for {url}") from last_error


def _http_post(url: str, data: bytes, *, headers: dict[str, str]) -> str:
    last_error: Exception | None = None
    for _attempt in range(2):
        request = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
                return response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            if exc.code >= 500:
                last_error = TemporaryError(url)
                continue
            raise RuntimeError(f"HTTP {exc.code} for {url}") from exc
        except (urllib.error.URLError, TimeoutError, socket.timeout) as exc:
            last_error = TemporaryError(url)
            continue
    raise RuntimeError(f"temporary failure for {url}") from last_error


def _select(rows: list[dict], window_start: date, window_end: date) -> tuple[list[dict], dict[str, int]]:
    start = window_start.isoformat()
    end = window_end.isoformat()
    older = {"app_store": 0, "play": 0}
    in_window: list[dict] = []
    for row in rows:
        if row["date"] < start:
            older[row["store"]] += 1
        elif row["date"] <= end:
            in_window.append(row)
    kept: list[dict] = []
    seen: set[tuple] = set()
    for row in in_window:
        text = _collapse(row["text"])
        key = (row["store"], row["date"], row["rating"], text)
        if key in seen:
            continue
        seen.add(key)
        kept.append({**row, "text": text, "title": _collapse(row["title"])})
    kept.sort(key=lambda row: (row["store"], row["date"], int(row["rating"]), row["text"]))
    return kept, older


def _write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def _write_notes(
    path: Path,
    window_start: date,
    window_end: date,
    kept: list[dict],
    notes: list[str],
    errors: list[str],
    older: dict[str, int] | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "window_start": window_start.isoformat(),
        "window_end": window_end.isoformat(),
        "kept_by_store": {
            "app_store": sum(1 for row in kept if row["store"] == "app_store"),
            "play": sum(1 for row in kept if row["store"] == "play"),
        },
        "older_by_store": older or {"app_store": 0, "play": 0},
        "notes": notes,
        "errors": errors,
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _review(*, store: str, rating, title: str, text: str, raw_date: str, app_id: str) -> dict | None:
    rating_text = _rating_text(rating)
    parsed_date = _calendar_date(raw_date)
    if rating_text is None or parsed_date is None or text.strip() == "":
        return None
    return {
        "store": store,
        "rating": rating_text,
        "date": parsed_date,
        "title": title,
        "text": text,
        "app_id": app_id,
    }


def _rating_text(value) -> str | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and 1 <= value <= 5:
        return str(value)
    text = str(value).strip()
    if re.fullmatch(r"[1-5]", text):
        return text
    return None


def _calendar_date(value: str) -> str | None:
    head = value.split("T", 1)[0].strip()
    try:
        return date.fromisoformat(head).isoformat()
    except ValueError:
        return None


def _label(value) -> str | None:
    if isinstance(value, dict):
        label = value.get("label")
        if label is None:
            return None
        return str(label)
    return None


def _collapse(value: str) -> str:
    return _WHITESPACE.sub(" ", value).strip()


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv()


if __name__ == "__main__":
    raise SystemExit(main())
