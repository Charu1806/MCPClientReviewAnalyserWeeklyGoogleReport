from datetime import date
from decimal import Decimal

from src.brief import Draft, build_brief
from src.checks import check_draft
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


def test_passing_draft():
    brief = _normal_brief()
    body = _good_body(brief)
    draft = Draft(doc_body=body, email_subject=brief.title, email_body=body + "\nDoc: {doc_link}")
    assert check_draft(brief, draft) == []


def test_paraphrased_quote_fails():
    brief = _normal_brief()
    body = _good_body(brief).replace("KYC failed", "KYC did not work")
    draft = Draft(doc_body=body, email_subject=brief.title, email_body=body + "\nDoc: {doc_link}")
    assert "quotes" in check_draft(brief, draft)


def test_over_250_words_fails():
    brief = _normal_brief()
    body = _good_body(brief) + "\n" + " ".join(["word"] * 251)
    draft = Draft(doc_body=body, email_subject=brief.title, email_body=body + "\nDoc: {doc_link}")
    assert "length" in check_draft(brief, draft)


def test_buy_advice_fails():
    brief = _normal_brief()
    body = _good_body(brief) + "\nUsers should buy more funds."
    draft = Draft(doc_body=body, email_subject=brief.title, email_body=body + "\nDoc: {doc_link}")
    assert "advice" in check_draft(brief, draft)


def test_empty_export_rejects_theme_name():
    filtered = FilterResult(
        kept=[],
        dropped={
            "empty": 0,
            "bad_date": 0,
            "bad_rating": 0,
            "bad_store": 0,
            "out_of_window": 0,
            "duplicate": 0,
            "wrong_app": 0,
        },
        missing_stores=["app_store", "play"],
        stores_empty_in_window=[],
        window_start=date(2026, 7, 6),
        window_end=date(2026, 9, 28),
        actual_start=None,
        actual_end=None,
        stop_reason="",
    )
    brief = build_brief(
        filtered=filtered,
        run_date=date(2026, 9, 28),
        highlighted=[],
        other_themes=[],
        quotes=[],
        unthemed=0,
        loaded_count=0,
    )
    bad = Draft(
        doc_body="SIP and payments dominated this week.",
        email_subject=brief.title,
        email_body="SIP and payments dominated this week.\nDoc: {doc_link}",
    )
    assert "facts" in check_draft(brief, bad)

    good = Draft(
        doc_body="No reviews in this export.",
        email_subject=brief.title,
        email_body="No reviews in this export.\nDoc: {doc_link}",
    )
    assert check_draft(brief, good) == []


def test_strips_wrapping_fence():
    brief = _normal_brief()
    body = _good_body(brief)
    draft = Draft(
        doc_body=f"```markdown\n{body}\n```",
        email_subject=f"```\n{brief.title}\n```",
        email_body=f"```\n{body}\nDoc: {{doc_link}}\n```",
    )
    assert check_draft(brief, draft) == []
