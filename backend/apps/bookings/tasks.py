"""
Scheduled jobs that move bookings through their lifecycle without anyone
having to open the app.
"""

import logging
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.bookings.constants import BookingStatus
from apps.bookings.models import Booking, BookingStatusHistory

logger = logging.getLogger("snapsphere")


@shared_task
def expire_pending_bookings():
    """
    Close out requests the photographer never answered.

    Runs every 15 minutes. Without it a buyer waits indefinitely on a
    photographer who has stopped using the app, and the calendar slot stays
    blocked against every other buyer.
    """
    now = timezone.now()
    stale = Booking.objects.filter(status=BookingStatus.PENDING, expires_at__lte=now)

    expired = 0
    for booking in stale.iterator():
        with transaction.atomic():
            # Re-read under a lock: the photographer may have accepted in the
            # milliseconds between the query and this update.
            locked = Booking.objects.select_for_update().get(pk=booking.pk)
            if locked.status != BookingStatus.PENDING:
                continue

            locked.status = BookingStatus.EXPIRED
            locked.save(update_fields=["status", "updated_at"])

            BookingStatusHistory.objects.create(
                booking=locked,
                from_status=BookingStatus.PENDING,
                to_status=BookingStatus.EXPIRED,
                changed_by=None,
                actor_role="SYSTEM",
                note=f"No response within {settings.BOOKING_EXPIRY_HOURS} hours.",
            )
            expired += 1

        _notify_expiry.delay(locked.pk)

    logger.info("Expired %s pending bookings", expired)
    return {"expired": expired}


@shared_task
def auto_complete_bookings():
    """
    Mark accepted bookings complete once the event is comfortably past.

    Photographers routinely forget to tap "Completed", which would freeze the
    booking forever and block the buyer from leaving a review. After the
    configured grace period the system closes it out.
    """
    cutoff = timezone.localdate() - timedelta(
        days=max(settings.BOOKING_AUTO_COMPLETE_HOURS // 24, 1)
    )
    due = Booking.objects.filter(status=BookingStatus.ACCEPTED, event_date__lte=cutoff)

    completed = 0
    for booking in due.iterator():
        with transaction.atomic():
            locked = Booking.objects.select_for_update().get(pk=booking.pk)
            if locked.status != BookingStatus.ACCEPTED:
                continue
            locked.status = BookingStatus.COMPLETED
            locked.completed_at = timezone.now()
            locked.save(update_fields=["status", "completed_at", "updated_at"])

            BookingStatusHistory.objects.create(
                booking=locked,
                from_status=BookingStatus.ACCEPTED,
                to_status=BookingStatus.COMPLETED,
                actor_role="SYSTEM",
                note="Auto-completed after the event date passed.",
            )
            completed += 1

    logger.info("Auto-completed %s bookings", completed)
    return {"completed": completed}


@shared_task
def send_booking_reminders():
    """Remind both parties the day before a shoot."""
    tomorrow = timezone.localdate() + timedelta(days=1)
    upcoming = Booking.objects.filter(
        status=BookingStatus.ACCEPTED, event_date=tomorrow
    ).select_related("buyer", "photographer__user", "service")

    sent = 0
    for booking in upcoming:
        _notify_reminder.delay(booking.pk)
        sent += 1

    logger.info("Queued %s booking reminders", sent)
    return {"reminders": sent}


# ═══════════════════════════════════════════════════════════════════════════
# Notification fan-out is a separate task so a failure to notify never rolls
# back the state change that has already been committed.
# ═══════════════════════════════════════════════════════════════════════════
@shared_task
def _notify_expiry(booking_id: int):
    from apps.notifications.services import notify

    booking = Booking.objects.select_related("buyer", "photographer__user").get(
        pk=booking_id
    )
    notify(
        booking.buyer,
        "BOOKING_EXPIRED",
        title="Booking request expired",
        body=(
            f"{booking.photographer.display_name} didn't respond in time. "
            f"We've found similar photographers for you."
        ),
        action_screen="BookingDetail",
        action_id=str(booking.pk),
    )
    notify(
        booking.photographer.user,
        "BOOKING_EXPIRED",
        title="You missed a booking request",
        body=f"A request for {booking.event_date} expired without a response.",
        action_screen="BookingDetail",
        action_id=str(booking.pk),
    )


@shared_task
def _notify_reminder(booking_id: int):
    from apps.notifications.services import notify

    booking = Booking.objects.select_related("buyer", "photographer__user").get(
        pk=booking_id
    )
    for user, other in (
        (booking.buyer, booking.photographer.display_name),
        (booking.photographer.user, booking.buyer.full_name),
    ):
        notify(
            user,
            "BOOKING_REMINDER",
            title="Shoot tomorrow",
            body=(
                f"Your shoot with {other} is tomorrow at "
                f"{booking.start_time:%H:%M} — {booking.location_address}"
            ),
            action_screen="BookingDetail",
            action_id=str(booking.pk),
        )
