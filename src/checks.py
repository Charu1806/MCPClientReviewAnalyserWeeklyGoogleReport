"""Validate Groq draft text against the brief. No network."""

from __future__ import annotations

import re
from datetime import date

from src.brief import Brief, Draft
from src.catalog import THEME_NAMES
from src.filter import Review
from src.quotes import is_unsafe

_FENCE = re.compile(r"^```(?:\w+)?\n([\s\S]*?)\n```$")
_TOP_THEMES = re.compile(r"(?im)^Top themes\s*$")
_QUOTES = re.compile(r"(?im)^Quotes\s*$")
_ACTIONS = re.compile(r"(?im)^Actions\s*$")
_ACTION_LINE = re.compile(r"(?im)^\d+\.\s*(.+?):\s+.+$")
_ADVICE_WORD = re.compile(r"(?i)\b(?:buy|sell|hold)\b")
_ADVICE_PHRASE = re.compile(r"(?i)\binvest in\b|\bbest scheme\b|\bbest fund\b|\byou should\b")
_QUOTED = re.compile(r'"([^"]+)"')


def check_draft(brief: Brief, draft: Draft) -> list[str]:
    """Return failure names. Empty list means the draft passes."""
    doc_body = _strip_fence(draft.doc_body)
    email_subject = _strip_fence(draft.email_subject)
    email_body = _strip_fence(draft.email_body)
    cleaned = Draft(doc_body=doc_body, email_subject=email_subject, email_body=email_body)

    failures: list[str] = []
    for name, ok in [
        ("shape", _shape_ok(brief, cleaned)),
        ("quotes", _quotes_ok(brief, cleaned)),
        ("facts", _facts_ok(brief, cleaned)),
        ("actions", _actions_ok(brief, cleaned)),
        ("length", len(cleaned.doc_body.split()) <= 250),
        ("privacy", _privacy_ok(cleaned)),
        ("advice", _advice_ok(cleaned)),
        ("subject", cleaned.email_subject.strip() == brief.title),
        ("link", _link_ok(cleaned)),
    ]:
        if not ok:
            failures.append(name)
    return failures


def _strip_fence(value: str) -> str:
    text = value.strip()
    match = _FENCE.match(text)
    if match:
        return match.group(1).strip()
    return text


def _shape_ok(brief: Brief, draft: Draft) -> bool:
    if not draft.doc_body.strip() or not draft.email_subject.strip() or not draft.email_body.strip():
        return False
    if brief.note_mode == "normal":
        return bool(_TOP_THEMES.search(draft.doc_body) and _ACTIONS.search(draft.doc_body))
    return True


def _quotes_ok(brief: Brief, draft: Draft) -> bool:
    body = draft.doc_body
    if brief.note_mode != "normal":
        return not _QUOTED.search(body)
    if not brief.quotes:
        if _QUOTES.search(body):
            return False
        return not _QUOTED.search(body)
    for quote in brief.quotes:
        if quote.text not in body:
            return False
    return True


def _facts_ok(brief: Brief, draft: Draft) -> bool:
    body = draft.doc_body
    if brief.note_mode != "normal":
        if _QUOTES.search(body) or _ACTIONS.search(body):
            return False
        if "average" in body.casefold():
            return False
        for name in THEME_NAMES:
            if name in body:
                return False
        # one sentence: no blank line separating multiple paragraphs required,
        # but reject multi-heading short notes
        return True

    allowed = {item.name for item in brief.highlighted} | {item.name for item in brief.other_themes}
    for name in THEME_NAMES:
        if name in body and name not in allowed:
            return False

    for item in brief.highlighted:
        pattern = re.compile(
            rf"(?im)^\d+\.\s*{re.escape(item.name)}\s*—\s*{item.count}\s+reviews,\s*average\s*{re.escape(item.avg_rating)}\s*$"
        )
        if not pattern.search(body):
            return False
    return True


def _actions_ok(brief: Brief, draft: Draft) -> bool:
    body = draft.doc_body
    if brief.note_mode != "normal":
        return not _ACTIONS.search(body)

    if not brief.highlighted:
        return not _ACTIONS.search(body)

    if not _ACTIONS.search(body):
        return False

    action_block = body.split("Actions", 1)[-1]
    lines = [line.strip() for line in action_block.splitlines() if line.strip()]
    actions = []
    for line in lines:
        match = _ACTION_LINE.match(line)
        if match:
            actions.append(match.group(1).strip())
    if len(actions) != len(brief.highlighted):
        return False
    allowed = {item.name for item in brief.highlighted}
    return all(name in allowed for name in actions)


def _privacy_ok(draft: Draft) -> bool:
    for text in (draft.doc_body, draft.email_subject, draft.email_body):
        probe = Review(store="play", rating=1, date=date(2026, 1, 1), text=text, title="")
        if is_unsafe(probe):
            return False
    return True


def _advice_ok(draft: Draft) -> bool:
    blob = "\n".join([draft.doc_body, draft.email_subject, draft.email_body])
    return not (_ADVICE_WORD.search(blob) or _ADVICE_PHRASE.search(blob))


def _link_ok(draft: Draft) -> bool:
    if "{doc_link}" in draft.email_body:
        return True
    return draft.doc_body in draft.email_body
