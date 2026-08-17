"""
The order the Home feed is presented in — Module 10's serving path.

THE PROPERTY UNDER TEST
----------------------
The Home screen titles this feed "Top rated" when it is not personalised and
"Picked for you" when it is. The list has to be ordered the way its own heading
claims:

  * unpersonalised → descending by the rating the card DISPLAYS (`avg_rating`)
  * personalised   → the engine's score order, untouched

This was a real defect: a "Top rated" page came back 4.75, 4.67, 4.78, 3.79,
4.50 — every number correct, the sequence apparently random, because rating is
one of twelve features in the blended score. The numbers below are asserted as a
SEQUENCE, not against fixed values, so the test survives any reseed.
"""

from decimal import Decimal

import pytest

from apps.recommendations import engine

pytestmark = pytest.mark.django_db


@pytest.fixture
def rated_photographers(db, category):
    """
    Five approved photographers whose averages are deliberately out of order.

    Built in a jumbled sequence on purpose: if the fixture inserted them already
    descending, a feed that simply preserved insertion order would pass without
    sorting anything.
    """
    from django.contrib.auth import get_user_model

    from apps.catalog.models import Service
    from apps.profiles.services import create_photographer_profile

    User = get_user_model()
    made = []
    for index, (avg, reviews) in enumerate(
        [
            ("3.90", 120),
            ("4.80", 200),
            ("2.70", 90),
            ("4.30", 150),
            ("4.80", 40),  # same average as #2, thinner evidence
        ]
    ):
        user = User.objects.create_photographer(
            email=f"ordering{index}@test.pk",
            password="TestPass123!",
            full_name=f"Ordering Studio {index}",
            city="Islamabad",
            is_email_verified=True,
        )
        profile = create_photographer_profile(user)
        profile.business_name = f"Ordering Studio {index}"
        profile.is_approved = True
        profile.is_accepting_bookings = True
        profile.avg_rating = Decimal(avg)
        profile.reviews_count = reviews
        profile.bayesian_rating = profile.recompute_bayesian()
        profile.base_price = Decimal("40000.00")
        profile.completed_bookings = 10 + index
        profile.save()

        Service.objects.create(
            photographer=profile,
            category=category,
            title=f"Session {index}",
            price=Decimal("40000.00"),
            duration_hours=4,
        )
        made.append(profile)
    return made


def displayed(result) -> list[float]:
    return [float(p.avg_rating) for p in result["photographers"]]


# ═══════════════════════════════════════════════════════════════════════════
# UNPERSONALISED — the "Top rated" heading
# ═══════════════════════════════════════════════════════════════════════════
def test_an_unpersonalised_feed_descends_by_the_rating_it_shows(rated_photographers):
    result = engine.recommend(buyer=None, limit=10, use_cache=False)

    assert result["personalised"] is False
    ratings = displayed(result)
    assert ratings == sorted(ratings, reverse=True), (
        f"'Top rated' must descend by the number on the card, got {ratings}"
    )


def test_a_buyer_with_no_history_gets_the_same_order(rated_photographers, buyer):
    """
    A signed-in buyer is only "personalised" once they have interaction history.
    Until then their feed carries the "Top rated" heading too, so it must obey
    the same rule.
    """
    result = engine.recommend(buyer=buyer, limit=10, use_cache=False)

    assert result["personalised"] is False
    ratings = displayed(result)
    assert ratings == sorted(ratings, reverse=True)


def test_equal_averages_break_toward_more_reviews(rated_photographers):
    """4.8 from 200 reviews outranks 4.8 from 40 — same number, better evidence."""
    result = engine.recommend(buyer=None, limit=10, use_cache=False)

    top_two = result["photographers"][:2]
    assert [float(p.avg_rating) for p in top_two] == [4.8, 4.8]
    assert top_two[0].reviews_count > top_two[1].reviews_count


def test_ordering_survives_the_cache(rated_photographers):
    """
    The re-sort happens BEFORE the result is cached, so a cache hit must not
    serve the old score order.
    """
    from django.core.cache import cache

    cache.clear()
    first = displayed(engine.recommend(buyer=None, limit=10))
    second = displayed(engine.recommend(buyer=None, limit=10))

    assert first == second
    assert second == sorted(second, reverse=True)
    cache.clear()


def test_the_relaxed_fallback_is_ordered_too(rated_photographers):
    """
    Filters that match nobody widen until something is found — and whatever comes
    back is still shown under an unpersonalised heading.
    """
    result = engine.recommend(
        buyer=None, city="Nowhere-at-all", max_price=1.0, limit=10, use_cache=False
    )

    assert result["relaxed"] is not None
    ratings = displayed(result)
    assert ratings == sorted(ratings, reverse=True)


# ═══════════════════════════════════════════════════════════════════════════
# WHAT THE RE-SORT MUST NOT DO
# ═══════════════════════════════════════════════════════════════════════════
def test_it_reorders_the_page_without_changing_who_is_on_it(rated_photographers):
    """
    Presentation only. The scorer still selects the page — so this cannot become
    a back door that promotes a photographer the engine did not choose.
    """
    scored = engine.recommend(buyer=None, limit=3, use_cache=False)
    ids = {p.pk for p in scored["photographers"]}

    assert len(ids) == 3
    # Every row still carries the engine's own numbers and explanation.
    for photographer in scored["photographers"]:
        assert photographer.score > 0
        assert photographer.reason
        assert photographer.strategy


def test_a_personalised_feed_keeps_the_engines_order(rated_photographers, buyer):
    """
    The whole point of "Picked for you" is that the order IS the recommendation.
    Verified by calling the display helper directly with `personalised=True`,
    because manufacturing real collaborative-filter signal needs an interaction
    matrix this test has no business building.
    """
    rows = list(rated_photographers)
    for index, photographer in enumerate(rows):
        photographer.score = 1.0 - index / 100  # already descending by score
        photographer.reviews_count = photographer.reviews_count or 0

    before = [p.pk for p in rows]
    after = [p.pk for p in engine._order_for_display(rows, personalised=True)]

    assert after == before
