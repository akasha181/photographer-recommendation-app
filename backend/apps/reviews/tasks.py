"""
Review-related background jobs.

WHY A REMINDER JOB EXISTS AT ALL
--------------------------------
Reviews are the platform's only trust signal, and the moment a buyer is most
likely to write one is a day or two after the shoot — not weeks later when they
next happen to open the app. Without a nudge, a marketplace accumulates
photographers with 40 completed bookings and 3 reviews.

WHY IT NUDGES EXACTLY ONCE
--------------------------
A second reminder for the same booking is nagging, and nagging gets
notifications muted wholesale — which then costs the platform the booking
alerts that actually matter. The guard is a query against the notification
table itself rather than a flag on the booking: the fact "we already asked"
lives where the asking is recorded, so it stays true even if the job is
re-deployed or re-run.
"""

import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger("snapsphere")

#: Long enough that the gallery has plausibly been delivered, short enough that
#: the shoot is still fresh.
REMIND_AFTER_DAYS = 2

#: Past this the moment has gone and the ask is just noise.
REMIND_UNTIL_DAYS = 21


@shared_task
def check_review_eligibility():
    """Nudge buyers who completed a booking but have not reviewed it yet."""
    from apps.bookings.constants import BookingStatus
    from apps.bookings.models import Booking
    from apps.notifications.models import Notification, NotificationType
    from apps.notifications.services import notify

    today = timezone.localdate()
    window_start = today - timedelta(days=REMIND_UNTIL_DAYS)
    window_end = today - timedelta(days=REMIND_AFTER_DAYS)

    candidates = (
        Booking.objects.filter(
            status=BookingStatus.COMPLETED,
            has_review=False,
            event_date__gte=window_start,
            event_date__lte=window_end,
        )
        .select_related("buyer", "photographer", "photographer__user")
        .order_by("event_date")
    )

    # One query for every booking we have already asked about, instead of one
    # per candidate. `action_id` is a CharField, so the ids are compared as
    # strings on both sides.
    already_asked = set(
        Notification.objects.filter(
            notification_type=NotificationType.REVIEW_REMINDER,
            action_screen="WriteReview",
        ).values_list("action_id", flat=True)
    )

    sent = 0
    for booking in candidates.iterator(chunk_size=200):
        if str(booking.pk) in already_asked:
            continue
        result = notify(
            booking.buyer,
            NotificationType.REVIEW_REMINDER,
            title=f"How was your shoot with {booking.photographer.display_name}?",
            body="Leave a review — it takes a minute and helps other buyers choose.",
            action_screen="WriteReview",
            action_id=str(booking.pk),
            payload={"booking_id": booking.pk},
        )
        if result is not None:
            sent += 1

    logger.info("Review reminders sent: %s", sent)
    return {"sent": sent}


@shared_task
def recompute_review_sentiment(limit: int = 500):
    """
    Backfill sentiment for reviews stored before the model existed, or
    re-label after a retrain.

    Idempotent and bounded: it takes the oldest `limit` unlabelled reviews each
    run, so a retrain over 50,000 rows drains across successive beats instead of
    holding a worker for an hour.
    """
    from apps.core.sentiment import classify, reset_cache
    from apps.reviews.models import Review

    reset_cache()  # pick up a freshly trained artifact

    rows = list(
        Review.objects.filter(sentiment="")
        .exclude(comment="")
        .order_by("created_at")[:limit]
    )
    labelled = 0
    for review in rows:
        sentiment, score = classify(review.comment)
        if sentiment is None:
            continue
        Review.objects.filter(pk=review.pk).update(
            sentiment=sentiment, sentiment_score=score
        )
        labelled += 1

    logger.info("Sentiment backfilled for %s reviews", labelled)
    return {"scanned": len(rows), "labelled": labelled}
