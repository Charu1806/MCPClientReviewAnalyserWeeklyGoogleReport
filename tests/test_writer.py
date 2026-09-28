"""Writer tests use a fake transport. No sockets."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Mapping

import pytest

from src.brief import Draft, build_brief
from src.cluster import ThemeStats
from src.filter import FilterResult, Review
from src.quotes import Quote
from src.writer import HttpResponse, WriterError, write, write_once


def _stats(name: str, count: int, avg: str, day: date, index: int) -> ThemeStats:
    return ThemeStats(
        name=name,
        count=count,
        avg_rating=Decimal(avg),
        median_date=day,
        catalog_index=index,
    )


def _normal_brief():
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
    filtered = FilterResult(
        kept=[
            Review("play", 1, date(2026, 9, 1), "KYC failed", ""),
            Review("play", 2, date(2026, 9, 2), "SIP payment failed", ""),
            Review("app_store", 1, date(2026, 9, 3), "OTP login locked", ""),
        ],
        dropped={
            "empty": 0,
            "bad_date": 0,
            "bad_rating": 0,
            "bad_store": 0,
            "out_of_window": 0,
            "duplicate": 0,
            "wrong_app": 0,
        },
        missing_stores=[],
        stores_empty_in_window=[],
        window_start=date(2026, 7, 6),
        window_end=date(2026, 9, 28),
        actual_start=date(2026, 9, 1),
        actual_end=date(2026, 9, 3),
        stop_reason="",
    )
    return build_brief(
        filtered=filtered,
        run_date=date(2026, 9, 28),
        highlighted=highlighted,
        other_themes=[],
        quotes=quotes,
        unthemed=0,
        loaded_count=3,
    )


def _good_body(brief) -> str:
    q1, q2, q3 = brief.quotes
    return (
        "Top themes\n"
        "1. Onboarding and KYC — 1 reviews, average 1.0\n"
        "Users struggled with KYC.\n"
        "2. SIP and payments — 1 reviews, average 2.0\n"
        "Payments failed for some users.\n"
        "3. Login and access — 1 reviews, average 1.0\n"
        "Login OTP failed.\n"
        "\n"
        "Quotes\n"
        f'1. "{q1.text}" — Play, {q1.rating} stars, {q1.date}\n'
        f'2. "{q2.text}" — Play, {q2.rating} stars, {q2.date}\n'
        f'3. "{q3.text}" — App Store, {q3.rating} stars, {q3.date}\n'
        "\n"
        "Actions\n"
        "1. Onboarding and KYC: Clarify KYC retries in the app.\n"
        "2. SIP and payments: Improve payment failure messages.\n"
        "3. Login and access: Fix OTP delivery for login.\n"
    )


def _completion(doc_body: str, email_subject: str, email_body: str) -> bytes:
    inner = json.dumps(
        {
            "doc_body": doc_body,
            "email_subject": email_subject,
            "email_body": email_body,
        },
        ensure_ascii=False,
    )
    return json.dumps(
        {"choices": [{"message": {"content": inner}}]},
        ensure_ascii=False,
    ).encode("utf-8")


@dataclass
class FakeTransport:
    api_key: str = "test-key"
    model: str = "qwen/qwen3.8-27b"
    queue: list = field(default_factory=list)
    calls: list = field(default_factory=list)

    def post(
        self,
        url: str,
        headers: Mapping[str, str],
        body: bytes,
        timeout: float,
    ) -> HttpResponse:
        self.calls.append(
            {
                "url": url,
                "headers": dict(headers),
                "body": body,
                "timeout": timeout,
            }
        )
        if not self.queue:
            raise AssertionError("FakeTransport queue is empty")
        item = self.queue.pop(0)
        if isinstance(item, Exception):
            raise item
        status, payload = item
        return HttpResponse(status=status, body=payload)


def test_passing_draft_makes_one_content_call():
    brief = _normal_brief()
    body = _good_body(brief)
    draft_bytes = _completion(body, brief.title, body + "\nDoc: {doc_link}")
    transport = FakeTransport(queue=[(200, draft_bytes)])

    draft = write(brief, transport)

    assert draft.doc_body == body
    assert draft.email_subject == brief.title
    assert len(transport.calls) == 1
    assert transport.calls[0]["url"] == "https://api.groq.com/openai/v1/chat/completions"
    assert transport.calls[0]["headers"]["Authorization"] == "Bearer test-key"
    assert transport.calls[0]["timeout"] == 60.0
    request = json.loads(transport.calls[0]["body"].decode("utf-8"))
    assert request["model"] == "qwen/qwen3.8-27b"
    assert request["temperature"] == 0.2
    assert len(request["messages"]) == 2


def test_repair_after_quotes_failure():
    brief = _normal_brief()
    body = _good_body(brief)
    bad = body.replace("KYC failed", "KYC did not work")
    transport = FakeTransport(
        queue=[
            (200, _completion(bad, brief.title, bad + "\nDoc: {doc_link}")),
            (200, _completion(body, brief.title, body + "\nDoc: {doc_link}")),
        ]
    )

    draft = write(brief, transport)

    assert draft.doc_body == body
    assert len(transport.calls) == 2
    second_user = json.loads(transport.calls[1]["body"].decode("utf-8"))["messages"][1]["content"]
    payload = json.loads(second_user)
    assert "quotes" in payload["failed_checks"]
    assert payload["doc_body"] == bad


def test_two_failing_drafts_raise_with_failure_names():
    brief = _normal_brief()
    body = _good_body(brief)
    bad = body.replace("KYC failed", "KYC did not work")
    transport = FakeTransport(
        queue=[
            (200, _completion(bad, brief.title, bad + "\nDoc: {doc_link}")),
            (200, _completion(bad, brief.title, bad + "\nDoc: {doc_link}")),
        ]
    )

    with pytest.raises(WriterError) as caught:
        write(brief, transport)

    assert "quotes" in caught.value.failures
    assert len(transport.calls) == 2


def test_429_then_200_is_one_transport_retry():
    brief = _normal_brief()
    body = _good_body(brief)
    ok = _completion(body, brief.title, body + "\nDoc: {doc_link}")
    transport = FakeTransport(queue=[(429, b"rate"), (200, ok)])

    draft = write(brief, transport)

    assert draft.doc_body == body
    assert len(transport.calls) == 2


def test_400_raises_without_second_attempt():
    brief = _normal_brief()
    transport = FakeTransport(queue=[(400, b"bad request")])

    with pytest.raises(WriterError, match="HTTP 400"):
        write(brief, transport)

    assert len(transport.calls) == 1


def test_write_once_invalid_json_fails_shape_via_empty_draft():
    brief = _normal_brief()
    transport = FakeTransport(
        queue=[
            (
                200,
                json.dumps({"choices": [{"message": {"content": "not-json"}}]}).encode("utf-8"),
            )
        ]
    )

    draft = write_once(brief, transport)

    assert draft == Draft(doc_body="", email_subject="", email_body="")
