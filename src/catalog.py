"""Fixed theme catalog and keyword matching for Groww reviews."""

from __future__ import annotations

import re

# Order is the ranking tie-break. Do not reorder without updating tests and the PRD.
THEMES: list[tuple[str, tuple[str, ...]]] = [
    (
        "Onboarding and KYC",
        (
            "kyc",
            "e-kyc",
            "ekyc",
            "onboarding",
            "registration",
            "sign up",
            "signup",
            "paperwork",
            "demat",
            "account opening",
        ),
    ),
    (
        "SIP and payments",
        (
            "sip",
            "lump sum",
            "lumpsum",
            "upi",
            "net banking",
            "netbanking",
            "mandate",
            "payment",
            "autopay",
            "nach",
            "purchase",
        ),
    ),
    (
        "Login and access",
        (
            "mpin",
            "biometric",
            "otp",
            "password",
            "login",
            "log in",
            "sign in",
            "lockout",
            "locked",
            "fingerprint",
        ),
    ),
    (
        "Portfolio and statements",
        (
            "statement",
            "capital gain",
            "dashboard",
            "holding",
            "holdings",
            "nav",
            "portfolio",
            "order",
            "orders",
        ),
    ),
    (
        "Redemption and service",
        (
            "withdraw",
            "withdrawal",
            "redemption",
            "redeem",
            "bank detail",
            "contact update",
            "service request",
            "sell",
            "fast exit",
        ),
    ),
]

THEME_NAMES = [name for name, _ in THEMES]
THEME_INDEX = {name: index for index, (name, _) in enumerate(THEMES)}


def keyword_hits(text: str) -> dict[str, set[str]]:
    """Return distinct keywords hit per theme in title+text."""
    haystack = text.casefold()
    hits: dict[str, set[str]] = {name: set() for name, _ in THEMES}
    for name, keywords in THEMES:
        for keyword in keywords:
            needle = keyword.casefold()
            if " " in needle or "-" in needle:
                if needle in haystack:
                    hits[name].add(keyword)
            else:
                if re.search(rf"(?<!\w){re.escape(needle)}(?!\w)", haystack):
                    hits[name].add(keyword)
    return hits
