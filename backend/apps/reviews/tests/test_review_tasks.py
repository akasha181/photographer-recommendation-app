"""
Review background jobs — the reminder nudge and the sentiment backfill.

WHY THESE ARE WORTH TESTING
--------------------------
Both are idempotent by design and both would be silently wrong if they were
not. A reminder job that asks twice gets notifications muted wholesale — which
then costs the platform the booking alerts that actually matter. A backfill that
is not bounded holds a worker for an hour on a 50,000-row retrain.

The window is asserted as an INTERVAL from today, never as a fixed date: a test
pinned to "25 August" passes until the day the suite runs on the 26th.
"""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.bookings.constants import BookingStatus
from apps.bookings.models import Booking
from apps.notifications.models import Notification, NotificationType
from apps.reviews.models import Review
from apps.reviews.tasks import (
    REMIND_AFTER_DAYS,
    REMIND_UNTIL_DAYS,
    check_review_eligibility,
    recompute_review_sentiment,
)

pytestmark = pytest.mark.django_db


def _shoot_was(booking, *, days_ago: int):
    """Back-date the event without touching anything else on the row."""
    Booking.objects.filter(pk=booking.pk).update(
        event_date=timezone.localdate() - timedelta(days=days_ago)
    )
    booking.refresh_from_db()
    return booking


def reminders_for(user) -> int:
    return Notification.objects.filter(
        recipient=user, notification_type=NotificationType.REVIEW_REMINDER
    ).count()


# ═══════════════════════════════════════════════════════════════════════════
# THE REMINDER
# ═══════════════════════════════════════════════════════════════════════════
def test_a_completed_unreviewed_shoot_is_nudged(completed_booking, buyer):
    _shoot_was(completed_booking, days_ago=REMIND_AFTER_DAYS + 1)

    result = check_review_eligibility()

    assert result["sent"] == 1
    assert reminders_for(buyer) == 1


def test_the_nudge_deep_links_to_the_form(completed_booking, buyer):
    _shoot_was(completed_booking, days_ago=REMIND_AFTER_DAYS + 1)
    check_review_eligibility()

    notification = Notification.objects.get(
        recipient=buyer, notification_type=NotificationType.REVIEW_REMINDER
    )
    # Structured, not parsed out of the title — the app routes on these two.
    assert notification.action_screen == "WriteReview"
    assert notification.action_id == str(completed_booking.pk)


def test_it_asks_exactly_once(completed_booking, buyer):
    """
    The property the whole job depends on.

    The guard is a query against the notification table itself rather than a flag
    on the booking, so it stays true across a redeploy or a manual re-run.
    """
    _shoot_was(completed_booking, days_ago=REMIND_AFTER_DAYS + 1)

    first = check_review_eligibility()
    second = check_review_eligibility()
    third = check_review_eligibility()

    assert first["sent"] == 1
    assert second["sent"] == 0
    assert third["sent"] == 0
    assert reminders_for(buyer) == 1


def test_a_shoot_that_just_happened_is_left_alone(completed_booking, buyer):
    """Too soon — the gallery has plausibly not even been delivered yet."""
    _shoot_was(completed_booking, days_ago=0)

    assert check_review_eligibility()["sent"] == 0
    assert reminders_for(buyer) == 0


def test_an_old_shoot_is_left_alone(completed_booking, buyer):
    """Past the window the moment has gone, and the ask is just noise."""
    _shoot_was(completed_booking, days_ago=REMIND_UNTIL_DAYS + 5)

    assert check_review_eligibility()["sent"] == 0
    assert reminders_for(buyer) == 0


def test_an_already_reviewed_booking_is_not_nudged(completed_booking, buyer):
    from apps.reviews import services

    _shoot_was(completed_booking, days_ago=REMIND_AFTER_DAYS + 1)
    services.create_review(
        completed_booking, buyer, rating=5, comment="Already said my piece."
    )

    assert check_review_eligibility()["sent"] == 0
    assert reminders_for(buyer) == 0


def test_a_pending_booking_is_not_nudged(booking, buyer):
    _shoot_was(booking, days_ago=REMIND_AFTER_DAYS + 1)
    assert booking.status == BookingStatus.PENDING

    assert check_review_eligibility()["sent"] == 0


def test_muting_review_activity_silences_the_nudge(completed_booking, buyer):
    """
    `notify()` returns None for a muted category, and the job counts what was
    actually sent rather than what it attempted.
    """
    from apps.notifications.services import update_preferences

    _shoot_was(completed_booking, days_ago=REMIND_AFTER_DAYS + 1)
    update_preferences(buyer, review_activity=False)

    assert check_review_eligibility()["sent"] == 0
    assert reminders_for(buyer) == 0


# ═══════════════════════════════════════════════════════════════════════════
# THE SENTIMENT BACKFILL
# ═══════════════════════════════════════════════════════════════════════════
def test_the_backfill_only_looks_at_unlabelled_reviews(completed_booking, buyer):
    from apps.reviews import services

    review = services.create_review(
        completed_booking, buyer, rating=5,
        comment="Absolutely stunning photographs and a joy to work with.",
    )
    # Whatever the artifact did or did not label it, force it unlabelled so the
    # scan has exactly one candidate. The assertion is about the SCAN, not about
    # the model's answer — an artifact-free checkout must still pass.
    Review.objects.filter(pk=review.pk).update(sentiment="", sentiment_score=None)

    result = recompute_review_sentiment(limit=10)

    assert result["scanned"] == 1
    assert result["labelled"] <= 1


def test_a_labelled_review_is_not_rescanned(completed_booking, buyer):
    from apps.reviews import services

    review = services.create_review(
        completed_booking, buyer, rating=5, comment="Beautiful work throughout."
    )
    Review.objects.filter(pk=review.pk).update(sentiment="POSITIVE")

    assert recompute_review_sentiment(limit=10)["scanned"] == 0


def test_a_commentless_review_is_never_scanned(completed_booking, buyer):
    """Nothing to classify — and a label on no evidence is worse than none."""
    from apps.reviews import services

    services.create_review(completed_booking, buyer, rating=5, comment="")

    assert recompute_review_sentiment(limit=10)["scanned"] == 0


def test_the_scan_is_bounded(buyer, photographer, category, make_booking):
    """
    A retrain over 50,000 rows must drain across beats, not hold one worker.

    The limit is asserted against more candidates than the limit allows, which is
    the only way to prove the slice is doing anything.
    """
    from conftest import working_date

    from apps.bookings.services import accept_booking, complete_booking
    from apps.reviews import services

    for index in range(3):
        # `working_date` skips Sundays: the seeded calendar has them off, so a
        # raw date arithmetic would fail for a reason unrelated to this test.
        booking = make_booking(event_date=working_date(10 + index * 3))
        accept_booking(booking, photographer.user)
        _shoot_was(booking, days_ago=1)
        # Use the RETURNED booking: `complete_booking` moves the row through a
        # separate instance fetched under a lock, so the local one is stale and
        # would still read ACCEPTED.
        booking = complete_booking(booking, photographer.user)
        review = services.create_review(
            booking, buyer, rating=4,
            comment=f"Review number {index} with enough words to classify.",
        )
        Review.objects.filter(pk=review.pk).update(sentiment="", sentiment_score=None)

    assert recompute_review_sentiment(limit=2)["scanned"] == 2


# ═══════════════════════════════════════════════════════════════════════════
# THE CLASSIFIER ITSELF
# ═══════════════════════════════════════════════════════════════════════════
def test_short_comments_are_left_unlabelled():
    """
    TF-IDF over "ok" still returns a label with a confident-looking probability,
    because softmax always sums to one. Showing "NEGATIVE 0.71" against two
    characters is worse than showing nothing.
    """
    from apps.core.sentiment import classify

    assert classify("ok") == (None, None)
    assert classify("") == (None, None)
    assert classify("   ") == (None, None)


def test_a_missing_artifact_degrades_quietly(settings, tmp_path):
    """
    The artifact is a build product. A fresh clone that has not run the trainer
    must still be able to post a review — the label is decoration on the review,
    not part of it.
    """
    from apps.core.sentiment import classify, reset_cache

    settings.ML_ARTIFACTS_DIR = tmp_path  # empty directory
    reset_cache()
    try:
        assert classify("A long enough comment to be classified normally.") == (
            None,
            None,
        )
    finally:
        reset_cache()


def test_a_review_still_saves_with_no_artifact(
    settings, tmp_path, completed_booking, buyer
):
    from apps.core.sentiment import reset_cache
    from apps.reviews import services

    settings.ML_ARTIFACTS_DIR = tmp_path
    reset_cache()
    try:
        review = services.create_review(
            completed_booking, buyer, rating=5,
            comment="Genuinely excellent from start to finish.",
        )
        assert review.pk is not None
        assert review.sentiment == ""
        assert review.sentiment_score is None
    finally:
        reset_cache()
