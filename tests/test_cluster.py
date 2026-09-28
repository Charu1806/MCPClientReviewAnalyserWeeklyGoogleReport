from datetime import date
from decimal import Decimal

from src.cluster import assign, highlight, rank, theme_reviews
from src.filter import Review


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


def test_two_keyword_tie_assigns_earlier_catalog_theme():
    # "login" is Login and access; "kyc" is Onboarding. One each → earlier catalog wins.
    review = _review(text="login failed during kyc")
    assert assign(review) == "Onboarding and KYC"


def test_rating_only_review_is_unthemed():
    assert assign(_review(text="5 stars", title="")) is None
    assert assign(_review(text="", title="★★★★★")) is None


def test_word_boundaries_do_not_match_pay_inside_another_word():
    assert assign(_review(text="The repayment schedule is clear")) is None
    assert assign(_review(text="UPI payment failed")) == "SIP and payments"


def test_rank_is_stable_and_uses_half_up_average():
    reviews = [
        _review(text="KYC blocked me", rating=1, date=date(2026, 9, 1)),
        _review(text="eKYC failed again", rating=2, date=date(2026, 9, 2)),
        _review(text="SIP payment failed", rating=5, date=date(2026, 9, 3)),
        _review(text="UPI mandate issue", rating=4, date=date(2026, 9, 4)),
        _review(text="OTP login locked", rating=1, date=date(2026, 9, 5)),
        _review(text="Nice weather today", rating=5, date=date(2026, 9, 6)),
    ]
    themed = theme_reviews(reviews)
    first = rank(themed)
    second = rank(themed)

    assert [item.name for item in first] == [item.name for item in second]
    assert [item.name for item in first] == [
        "Onboarding and KYC",
        "SIP and payments",
        "Login and access",
    ]
    # (1+2)/2 = 1.5 exactly
    assert first[0].avg_rating == Decimal("1.5")
    # (5+4)/2 = 4.5
    assert first[1].avg_rating == Decimal("4.5")


def test_tie_on_count_prefers_lower_average_then_newer_median():
    reviews = [
        _review(text="KYC issue", rating=5, date=date(2026, 8, 1)),
        _review(text="SIP failed", rating=1, date=date(2026, 9, 1)),
    ]
    stats = rank(theme_reviews(reviews))
    assert [item.name for item in stats] == ["SIP and payments", "Onboarding and KYC"]


def test_upper_median_on_even_count():
    reviews = [
        _review(text="KYC one", rating=3, date=date(2026, 9, 1)),
        _review(text="KYC two", rating=3, date=date(2026, 9, 2)),
        _review(text="KYC three", rating=3, date=date(2026, 9, 3)),
        _review(text="KYC four", rating=3, date=date(2026, 9, 4)),
    ]
    stats = rank(theme_reviews(reviews))
    assert stats[0].median_date == date(2026, 9, 3)


def test_highlight_keeps_top_three():
    reviews = [
        _review(text="KYC", rating=1, date=date(2026, 9, 1)),
        _review(text="KYC again", rating=1, date=date(2026, 9, 2)),
        _review(text="SIP", rating=2, date=date(2026, 9, 3)),
        _review(text="login OTP", rating=3, date=date(2026, 9, 4)),
        _review(text="portfolio holdings", rating=4, date=date(2026, 9, 5)),
    ]
    top, other = highlight(rank(theme_reviews(reviews)))
    assert [item.name for item in top] == [
        "Onboarding and KYC",
        "SIP and payments",
        "Login and access",
    ]
    assert [item.name for item in other] == ["Portfolio and statements"]
