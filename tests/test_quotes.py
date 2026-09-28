from datetime import date

from src.cluster import highlight, rank, theme_reviews
from src.filter import Review
from src.quotes import cut_quote, select_quotes


def _review(**overrides) -> Review:
    data = {
        "store": "play",
        "rating": 3,
        "date": date(2026, 9, 1),
        "text": "KYC took a day",
        "title": "",
    }
    data.update(overrides)
    return Review(**data)


def test_same_fixture_yields_same_quote_strings_twice():
    reviews = [
        _review(text="KYC failed on day one.", rating=1, date=date(2026, 9, 5)),
        _review(text="SIP payment failed twice.", rating=2, date=date(2026, 9, 4)),
        _review(text="OTP login locked me out.", rating=1, date=date(2026, 9, 3)),
        _review(text="Portfolio holdings look wrong.", rating=4, date=date(2026, 9, 2)),
    ]
    themed = theme_reviews(reviews)
    top, _other = highlight(rank(themed))
    first = [quote.text for quote in select_quotes(themed, top)]
    second = [quote.text for quote in select_quotes(themed, top)]
    assert first == second
    assert len(first) == 3


def test_email_review_counts_in_theme_but_is_not_quoted():
    reviews = [
        _review(text="KYC failed, email me at user@example.com", rating=1, date=date(2026, 9, 5)),
        _review(text="KYC worked after retry", rating=2, date=date(2026, 9, 4)),
        _review(text="SIP payment failed", rating=3, date=date(2026, 9, 3)),
        _review(text="OTP login issue", rating=4, date=date(2026, 9, 2)),
    ]
    themed = theme_reviews(reviews)
    stats = rank(themed)
    assert stats[0].name == "Onboarding and KYC"
    assert stats[0].count == 2
    top, _ = highlight(stats)
    quotes = select_quotes(themed, top)
    joined = " ".join(quote.text for quote in quotes)
    assert "user@example.com" not in joined
    assert any("KYC worked after retry" in quote.text for quote in quotes)


def test_fifty_word_first_sentence_becomes_forty_plus_ellipsis():
    words = " ".join(f"word{i}" for i in range(1, 51))
    text = words + " Second sentence stays out."
    cut = cut_quote(text)
    assert cut.endswith("...")
    kept = cut[:-3]
    assert len(kept.split()) == 40
    assert text.startswith(kept)


def test_skips_emoji_only_and_duplicate_collapsed_text():
    reviews = [
        _review(text="🔥🔥🔥", title="", rating=1, date=date(2026, 9, 5)),
        _review(text="KYC failed today", rating=1, date=date(2026, 9, 4)),
        _review(text="KYC   failed today", rating=2, date=date(2026, 9, 3)),
        _review(text="SIP payment failed", rating=3, date=date(2026, 9, 2)),
        _review(text="OTP login issue", rating=4, date=date(2026, 9, 1)),
    ]
    themed = theme_reviews(reviews)
    top, _ = highlight(rank(themed))
    quotes = select_quotes(themed, top)
    texts = [quote.text for quote in quotes]
    assert "🔥🔥🔥" not in texts
    assert sum("KYC failed today" in text for text in texts) == 1


def test_prefers_one_quote_per_highlighted_theme():
    reviews = [
        _review(text="KYC delayed", rating=1, date=date(2026, 9, 5)),
        _review(text="another KYC delay", rating=1, date=date(2026, 9, 4)),
        _review(text="SIP failed", rating=2, date=date(2026, 9, 3)),
        _review(text="OTP locked", rating=1, date=date(2026, 9, 2)),
    ]
    themed = theme_reviews(reviews)
    top, _ = highlight(rank(themed))
    quotes = select_quotes(themed, top)
    # Rank: Onboarding (2), then Login (avg 1) before SIP (avg 2).
    assert [item.name for item in top] == [
        "Onboarding and KYC",
        "Login and access",
        "SIP and payments",
    ]
    assert [quote.theme for quote in quotes] == [item.name for item in top]
