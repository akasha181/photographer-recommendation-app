"""
Reviews & ratings — Module 9.

THE PROPERTY UNDER TEST THROUGHOUT
---------------------------------
A review exists if and only if a completed booking paid for it, and the
photographer's headline rating always equals the reviews listed underneath it.
Every test below is one of those two sentences, or one of the ways they can be
broken: an ineligible booking, a double submit, a moderated review that should
leave the average, a rating edit that should move it.
"""

from decimal import Decimal

import pytest
from django.utils import timezone

from apps.bookings.constants import BookingStatus
from apps.core.exceptions import BusinessRuleViolation, ConflictError
from apps.reviews import selectors, services
from apps.reviews.models import ProductReview, Review, ReviewHelpful, ReviewReply

pytestmark = pytest.mark.django_db


def write(booking, buyer, **overrides):
    payload = {"rating": 5, "title": "Superb", "comment": "Beautiful work throughout the day."}
    payload.update(overrides)
    return services.create_review(booking, buyer, **payload)


# ═══════════════════════════════════════════════════════════════════════════
# ELIGIBILITY — the anti-fraud control
# ═══════════════════════════════════════════════════════════════════════════
def test_buyer_can_review_a_completed_booking(completed_booking, buyer):
    review = write(completed_booking, buyer)

    assert review.rating == 5
    assert review.photographer_id == completed_booking.photographer_id
    assert review.buyer_id == buyer.id


def test_cannot_review_a_booking_that_is_not_completed(booking, buyer):
    assert booking.status == BookingStatus.PENDING

    with pytest.raises(BusinessRuleViolation, match="marked completed"):
        write(booking, buyer)


def test_cannot_review_somebody_elses_booking(completed_booking, other_buyer):
    with pytest.raises(BusinessRuleViolation, match="your own bookings"):
        write(completed_booking, other_buyer)


def test_second_review_for_the_same_booking_is_refused(completed_booking, buyer):
    write(completed_booking, buyer)

    with pytest.raises(ConflictError, match="already reviewed"):
        write(completed_booking, buyer)

    assert Review.objects.filter(booking=completed_booking).count() == 1


def test_the_database_refuses_a_second_review_even_without_the_service(
    completed_booking, buyer
):
    """
    Level 3 of the three-level guard.

    The serializer and the service can both be bypassed by a code path that does
    not exist yet. `Review.booking` being OneToOne cannot be.
    """
    from django.db import IntegrityError, transaction

    write(completed_booking, buyer)

    with pytest.raises(IntegrityError), transaction.atomic():
        Review.objects.create(
            booking=completed_booking,
            buyer=buyer,
            photographer=completed_booking.photographer,
            rating=1,
        )


def test_reviewing_marks_the_booking_and_closes_the_prompt(completed_booking, buyer):
    assert completed_booking.is_reviewable is True

    write(completed_booking, buyer)
    completed_booking.refresh_from_db()

    assert completed_booking.has_review is True
    assert completed_booking.is_reviewable is False


# ═══════════════════════════════════════════════════════════════════════════
# THE HEADLINE NUMBER MATCHES THE LIST
# ═══════════════════════════════════════════════════════════════════════════
def test_rating_is_recomputed_on_the_profile(completed_booking, buyer, photographer):
    write(completed_booking, buyer, rating=5)
    photographer.refresh_from_db()

    assert photographer.reviews_count == 1
    assert photographer.avg_rating == Decimal("5.00")
    # The Bayesian score is what search sorts on, and it shrinks toward the
    # prior of 4.0: one 5★ review must NOT outrank a photographer with 200
    # reviews averaging 4.8.
    assert photographer.bayesian_rating < Decimal("5.00")


def test_buyer_review_counter_is_recomputed(completed_booking, buyer):
    write(completed_booking, buyer)
    buyer.buyer_profile.refresh_from_db()

    assert buyer.buyer_profile.reviews_written == 1


def test_a_hidden_review_leaves_the_public_average(completed_booking, buyer, photographer):
    review = write(completed_booking, buyer, rating=1, comment="Did not go well at all.")
    photographer.refresh_from_db()
    assert photographer.reviews_count == 1

    services.set_hidden(review, hidden=True, reason="Abusive language")
    photographer.refresh_from_db()

    assert photographer.reviews_count == 0
    assert photographer.avg_rating == Decimal("0.00")
    # The row survives — a hidden review must remain appealable.
    assert Review.all_objects.filter(pk=review.pk).exists()


def test_deleting_a_review_recomputes_but_keeps_the_entitlement_spent(
    completed_booking, buyer, photographer
):
    review = write(completed_booking, buyer)
    services.delete_review(review)

    photographer.refresh_from_db()
    completed_booking.refresh_from_db()

    assert photographer.reviews_count == 0
    # has_review stays True: the one review this booking was entitled to was
    # used. Otherwise deleting and reposting is an unlimited rating weapon.
    assert completed_booking.has_review is True


def test_editing_the_rating_moves_the_average(completed_booking, buyer, photographer):
    review = write(completed_booking, buyer, rating=5)
    services.update_review(review, rating=2, comment="On reflection, several issues.")

    photographer.refresh_from_db()
    assert photographer.avg_rating == Decimal("2.00")


# ═══════════════════════════════════════════════════════════════════════════
# EDIT WINDOW
# ═══════════════════════════════════════════════════════════════════════════
def test_edit_is_refused_after_the_window(completed_booking, buyer):
    from datetime import timedelta

    review = write(completed_booking, buyer)
    # Pinned as an INTERVAL, not a date: a fixed timestamp would sit either side
    # of the window depending on what time the suite runs.
    Review.objects.filter(pk=review.pk).update(
        created_at=timezone.now() - timedelta(hours=services.EDIT_WINDOW_HOURS + 1)
    )
    review.refresh_from_db()

    with pytest.raises(BusinessRuleViolation, match="edited for"):
        services.update_review(review, rating=1)


def test_edit_is_refused_once_the_photographer_has_replied(
    completed_booking, buyer, photographer
):
    review = write(completed_booking, buyer, rating=2, comment="Late and unprepared.")
    services.reply_to_review(review, photographer, "We're sorry — here is what happened.")
    review.refresh_from_db()

    with pytest.raises(BusinessRuleViolation, match="public reply"):
        services.update_review(review, comment="Actually it was fine.")


# ═══════════════════════════════════════════════════════════════════════════
# REPLIES
# ═══════════════════════════════════════════════════════════════════════════
def test_photographer_can_reply_once(completed_booking, buyer, photographer):
    review = write(completed_booking, buyer)
    services.reply_to_review(review, photographer, "Thank you, it was a joy to shoot.")

    with pytest.raises(ConflictError, match="already replied"):
        services.reply_to_review(review, photographer, "Second thought.")

    assert ReviewReply.objects.filter(review=review).count() == 1


def test_another_photographer_cannot_reply(completed_booking, buyer, other_photographer):
    review = write(completed_booking, buyer)

    with pytest.raises(BusinessRuleViolation, match="your own reviews"):
        services.reply_to_review(review, other_photographer, "Nothing to do with me.")


def test_editing_a_reply_flags_it_as_edited(completed_booking, buyer, photographer):
    review = write(completed_booking, buyer)
    reply = services.reply_to_review(review, photographer, "Thanks!")

    services.update_reply(reply, "Thank you so much — it was a pleasure.")
    reply.refresh_from_db()

    assert reply.is_edited is True
    assert "pleasure" in reply.comment


# ═══════════════════════════════════════════════════════════════════════════
# HELPFUL VOTES
# ═══════════════════════════════════════════════════════════════════════════
def test_helpful_toggles_and_reports_the_state_it_left(
    completed_booking, buyer, other_buyer
):
    review = write(completed_booking, buyer)

    marked, count = services.toggle_helpful(review, other_buyer)
    assert (marked, count) == (True, 1)

    marked, count = services.toggle_helpful(review, other_buyer)
    assert (marked, count) == (False, 0)
    assert ReviewHelpful.objects.filter(review=review).count() == 0


def test_you_cannot_mark_your_own_review_helpful(completed_booking, buyer):
    review = write(completed_booking, buyer)

    with pytest.raises(BusinessRuleViolation, match="your own review"):
        services.toggle_helpful(review, buyer)


def test_the_counter_never_goes_negative(completed_booking, buyer, other_buyer):
    """
    `helpful_count` is maintained with F() expressions and the column is
    unsigned, so a decrement below zero would be a database error rather than a
    wrong number. The guard is the `helpful_count__gt=0` filter.
    """
    review = write(completed_booking, buyer)
    services.toggle_helpful(review, other_buyer)
    services.toggle_helpful(review, other_buyer)
    services.toggle_helpful(review, other_buyer)
    services.toggle_helpful(review, other_buyer)

    review.refresh_from_db()
    assert review.helpful_count == 0


# ═══════════════════════════════════════════════════════════════════════════
# LOW RATINGS MUST EXPLAIN THEMSELVES
# ═══════════════════════════════════════════════════════════════════════════
def test_a_one_star_review_needs_a_comment(buyer_client, completed_booking):
    response = buyer_client.post(
        "/api/v1/reviews/",
        {"booking": completed_booking.pk, "rating": 1},
        format="json",
    )
    assert response.status_code == 400
    assert "comment" in str(response.data)


def test_a_five_star_review_needs_nothing(buyer_client, completed_booking):
    response = buyer_client.post(
        "/api/v1/reviews/",
        {"booking": completed_booking.pk, "rating": 5},
        format="json",
    )
    assert response.status_code == 201


# ═══════════════════════════════════════════════════════════════════════════
# SUMMARY / SELECTORS
# ═══════════════════════════════════════════════════════════════════════════
def test_breakdown_is_gap_filled_to_five_stars(completed_booking, buyer, photographer):
    write(completed_booking, buyer, rating=4)
    breakdown = selectors.rating_breakdown(photographer.pk)

    assert set(breakdown) == {"1", "2", "3", "4", "5"}
    assert breakdown["4"] == 1
    assert breakdown["1"] == 0


def test_summary_reports_sub_ratings_as_none_when_unrated(
    completed_booking, buyer, photographer
):
    write(completed_booking, buyer, rating=5)
    summary = selectors.review_summary(photographer.pk)

    assert summary["total_reviews"] == 1
    assert summary["average_rating"] == 5.0
    assert summary["recommend_percent"] == 100.0
    # None means "nobody filled this in" — not a damning zero.
    assert summary["sub_ratings"]["punctuality"] is None


def test_summary_averages_the_sub_ratings_that_were_given(
    completed_booking, buyer, photographer
):
    write(
        completed_booking, buyer, rating=4,
        rating_quality=5, rating_punctuality=2,
    )
    summary = selectors.review_summary(photographer.pk)

    assert summary["sub_ratings"]["quality"] == 5.0
    assert summary["sub_ratings"]["punctuality"] == 2.0


def test_summary_on_an_empty_profile_does_not_divide_by_zero(photographer):
    summary = selectors.review_summary(photographer.pk)

    assert summary["total_reviews"] == 0
    assert summary["average_rating"] == 0
    assert summary["recommend_percent"] == 0.0


def test_pending_lists_what_can_be_reviewed(completed_booking, buyer, paid_order_item):
    pending = selectors.pending_for_user(buyer)

    assert completed_booking in list(pending["bookings"])
    assert paid_order_item in list(pending["order_items"])


def test_pending_drops_a_booking_once_reviewed(completed_booking, buyer):
    write(completed_booking, buyer)
    pending = selectors.pending_for_user(buyer)

    assert list(pending["bookings"]) == []


# ═══════════════════════════════════════════════════════════════════════════
# PRODUCT REVIEWS
# ═══════════════════════════════════════════════════════════════════════════
def test_product_review_requires_a_paid_purchase(paid_order_item, funded_buyer, product):
    review = services.create_product_review(
        paid_order_item, funded_buyer, rating=5, comment="Exactly what I needed."
    )

    product.refresh_from_db()
    paid_order_item.refresh_from_db()

    assert product.reviews_count == 1
    assert product.avg_rating == Decimal("5.00")
    assert paid_order_item.has_review is True
    assert review.product_id == product.pk


def test_cannot_review_a_product_you_did_not_buy(paid_order_item, other_buyer):
    with pytest.raises(BusinessRuleViolation, match="products you bought"):
        services.create_product_review(paid_order_item, other_buyer, rating=5)


def test_second_product_review_is_refused(paid_order_item, funded_buyer):
    services.create_product_review(paid_order_item, funded_buyer, rating=5)

    with pytest.raises(ConflictError, match="already reviewed"):
        services.create_product_review(paid_order_item, funded_buyer, rating=1)

    assert ProductReview.objects.filter(order_item=paid_order_item).count() == 1


def test_deleting_a_product_review_recomputes_the_product(
    paid_order_item, funded_buyer, product
):
    review = services.create_product_review(paid_order_item, funded_buyer, rating=5)
    services.delete_product_review(review)

    product.refresh_from_db()
    assert product.reviews_count == 0
    assert product.avg_rating == Decimal("0.00")


# ═══════════════════════════════════════════════════════════════════════════
# NOTIFICATIONS
# ═══════════════════════════════════════════════════════════════════════════
def test_the_photographer_is_notified(completed_booking, buyer, photographer):
    from apps.notifications.models import Notification, NotificationType

    write(completed_booking, buyer, rating=5)

    notification = Notification.objects.filter(
        recipient=photographer.user,
        notification_type=NotificationType.REVIEW_RECEIVED,
    ).first()
    assert notification is not None
    assert notification.action_screen == "ReviewDetail"


def test_the_buyer_is_notified_of_a_reply(completed_booking, buyer, photographer):
    from apps.notifications.models import Notification, NotificationType

    review = write(completed_booking, buyer)
    services.reply_to_review(review, photographer, "Thank you!")

    assert Notification.objects.filter(
        recipient=buyer, notification_type=NotificationType.REVIEW_REPLIED
    ).exists()
