"""Call Groq to draft the note. Checks run here; MCP does not."""

from __future__ import annotations

import json
import re
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Mapping, Protocol, Sequence

from src.brief import Brief, Draft, prompt_payload
from src.checks import check_draft

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
_TIMEOUT_SECONDS = 60.0
_TEMPERATURE = 0.2
_RETRYABLE = {429, 500, 502, 503, 504}
_FENCE = re.compile(r"^```(?:\w+)?\n([\s\S]*?)\n```$")

_SYSTEM = """You write the weekly review pulse note from the brief JSON only.
Do not invent counts, themes, quotes, or causes.
Do not add investment advice (no buy, sell, hold, invest in, best scheme, best fund, or you should).

When note_mode is "normal":
- Shape doc_body exactly as:
Top themes
1. {Theme} — {count} reviews, average {avg}
{one sentence}

Quotes
1. "{quote text}" — {App Store or Play}, {rating} stars, {YYYY-MM-DD}

Actions
1. {Theme}: {one sentence}
- Number only the items that exist.
- Omit the Quotes section when the brief has no quotes.
- Copy each quote character for character, including "...".
- One sentence per highlighted theme.
- One action per highlighted theme, naming that theme.
- Actions are product, support, or growth steps only.

When note_mode is empty_export, wrong_app, empty_window, or unthemed:
- doc_body is exactly the first shortfall sentence, and nothing else.

email_subject must equal title.
email_body must contain doc_body and end with a final line: Doc: {doc_link}

Return one JSON object with keys doc_body, email_subject, and email_body.
No markdown fence around the JSON."""


class WriterError(Exception):
    """Groq transport failed or the draft failed checks twice."""

    def __init__(self, message: str, *, failures: Sequence[str] | None = None) -> None:
        super().__init__(message)
        self.failures = list(failures or [])


@dataclass(frozen=True)
class HttpResponse:
    status: int
    body: bytes


class Transport(Protocol):
    api_key: str
    model: str

    def post(
        self,
        url: str,
        headers: Mapping[str, str],
        body: bytes,
        timeout: float,
    ) -> HttpResponse:
        """Return status and body. Raise TimeoutError on timeout."""


@dataclass
class UrllibTransport:
    api_key: str
    model: str

    def post(
        self,
        url: str,
        headers: Mapping[str, str],
        body: bytes,
        timeout: float,
    ) -> HttpResponse:
        # Cloudflare on api.groq.com bans the default Python-urllib User-Agent (403/1010).
        merged = {"User-Agent": "groww-pulse/0.1", **dict(headers)}
        request = urllib.request.Request(
            url,
            data=body,
            headers=merged,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return HttpResponse(status=int(response.status), body=response.read())
        except urllib.error.HTTPError as exc:
            return HttpResponse(status=int(exc.code), body=exc.read() or b"")
        except TimeoutError as exc:
            raise TimeoutError(str(exc)) from exc
        except socket.timeout as exc:
            raise TimeoutError(str(exc)) from exc
        except urllib.error.URLError as exc:
            reason = exc.reason
            if isinstance(reason, (TimeoutError, socket.timeout)):
                raise TimeoutError(str(reason)) from exc
            raise WriterError(f"Groq transport error: {exc}") from exc


def write_once(
    brief: Brief,
    transport: Transport,
    *,
    failed_checks: Sequence[str] | None = None,
    previous: Draft | None = None,
) -> Draft:
    """One Groq call. Invalid JSON or missing keys become an empty-shaped draft."""
    user_obj = prompt_payload(brief)
    if failed_checks is not None and previous is not None:
        user_obj = {
            **user_obj,
            "failed_checks": list(failed_checks),
            "doc_body": previous.doc_body,
            "email_subject": previous.email_subject,
            "email_body": previous.email_body,
        }
    request_body = {
        "model": transport.model,
        "temperature": _TEMPERATURE,
        "messages": [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": json.dumps(user_obj, ensure_ascii=False)},
        ],
    }
    raw = _post_chat(transport, request_body)
    return _parse_draft(raw)


def write(brief: Brief, transport: Transport) -> Draft:
    """Write once, repair once on check failure, then raise."""
    first = write_once(brief, transport)
    failures = check_draft(brief, first)
    if not failures:
        return first

    second = write_once(
        brief,
        transport,
        failed_checks=failures,
        previous=first,
    )
    second_failures = check_draft(brief, second)
    if not second_failures:
        return second
    raise WriterError(
        f"draft failed checks: {', '.join(second_failures)}",
        failures=second_failures,
    )


def _post_chat(transport: Transport, request_body: dict) -> bytes:
    payload = json.dumps(request_body).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {transport.api_key}",
        "Content-Type": "application/json",
    }
    response = _post_with_transport_retry(transport, headers, payload)
    if response.status in _RETRYABLE:
        response = _post_with_transport_retry(transport, headers, payload)
        if response.status != 200:
            raise WriterError(f"Groq HTTP {response.status} after retry")
        return response.body
    if response.status != 200:
        raise WriterError(f"Groq HTTP {response.status}")
    return response.body


def _post_with_transport_retry(
    transport: Transport,
    headers: Mapping[str, str],
    payload: bytes,
) -> HttpResponse:
    """One logical HTTP attempt; on TimeoutError, retry the post once."""
    try:
        return transport.post(GROQ_URL, headers, payload, _TIMEOUT_SECONDS)
    except TimeoutError:
        try:
            return transport.post(GROQ_URL, headers, payload, _TIMEOUT_SECONDS)
        except TimeoutError as exc:
            raise WriterError("Groq timeout after retry") from exc


def _parse_draft(raw: bytes) -> Draft:
    empty = Draft(doc_body="", email_subject="", email_body="")
    try:
        outer = json.loads(raw.decode("utf-8"))
        content = outer["choices"][0]["message"]["content"]
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, IndexError, TypeError):
        return empty

    text = _strip_fence(str(content))
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return empty
    if not isinstance(data, dict):
        return empty

    doc_body = data.get("doc_body")
    email_subject = data.get("email_subject")
    email_body = data.get("email_body")
    if not isinstance(doc_body, str) or not isinstance(email_subject, str) or not isinstance(email_body, str):
        return Draft(
            doc_body=doc_body if isinstance(doc_body, str) else "",
            email_subject=email_subject if isinstance(email_subject, str) else "",
            email_body=email_body if isinstance(email_body, str) else "",
        )
    return Draft(doc_body=doc_body, email_subject=email_subject, email_body=email_body)


def _strip_fence(value: str) -> str:
    text = value.strip()
    match = _FENCE.match(text)
    if match:
        return match.group(1).strip()
    return text
