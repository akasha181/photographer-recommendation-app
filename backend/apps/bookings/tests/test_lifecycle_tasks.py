"""
The scheduled jobs that move bookings along without anyone opening the app,
plus the defensive paths that only fire when something has already gone wrong.
"""

from datetime import time, timedelta

import pytest
from django.core.cache import cache
from django.utils import timezone

from apps.bookings.constants import BookingStatus
from apps.bookings.models import Booking, BookingStatusHistory
from apps.bookings.services import accept_booking, create_booking
from apps.bookings.tasks import (
    auto_complete_bookings,
    expire_pending_bookings,
    send_booking_reminders,
)
from apps.core.exceptions import ConflictError

pytestmark = pytest.mark.django_db


def _accept(booking, photographer):
    return accept_booking(booking, photographer.user)


# ═══════════════════════════════════════════════════════════════════════════
# AUTO-COMPLETE
# ═══════════════════════════════════════════════════════════════════════════
def test_auto_completes_a_past_accepted_booking(booking, photographer):
    """
    Photographers routinely forget to tap "Completed". Left alone the booking
    would freeze forever and the buyer could never leave a review.
    """
    accepted = _accept(booking, photographer)
    accepted.event_date = timezone.localdate() - timedelta(days=10)
    accepted.save(update_fields=["event_date"])

    result = auto_complete_bookings()
    accepted.refresh_from_db()

    assert result["completed"] == 1
    assert accepted.status == BookingStatus.COMPLETED
    assert accepted.completed_at is not None
    assert BookingStatusHistory.objects.filter(
        booking=accepted, to_status=BookingStatus.COMPLETED, actor_role="SYSTEM"
    ).exists()


def test_auto_complete_leaves_future_bookings_alone(booking, photographer):
    accepted = _accept(booking, photographer)

    assert auto_complete_bookings()["completed"] == 0
    accepted.refresh_from_db()
    assert accepted.status == BookingStatus.ACCEPTED


def test_auto_complete_ignores_pending_bookings(booking):
    booking.event_date = timezone.localdate() - timedelta(days=10)
    booking.save(update_fields=["event_date"])

    assert auto_complete_bookings()["completed"] == 0
    booking.refresh_from_db()
    assert booking.status == BookingStatus.PENDING


# ═══════════════════════════════════════════════════════════════════════════
# EXPIRY
# ═══════════════════════════════════════════════════════════════════════════
def test_expiry_notifies_both_parties(booking, buyer, photographer):
    from apps.notifications.models import Notification

    booking.expires_at = timezone.now() - timedelta(hours=1)
    booking.save(update_fields=["expires_at"])

    expire_pending_bookings()

    for user in (buyer, photographer.user):
        assert Notification.objects.filter(
            recipient=user, notification_type="BOOKING_EXPIRED"
        ).exists()


def test_expiry_leaves_bookings_that_are_not_yet_due(booking):
    assert expire_pending_bookings()["expired"] == 0
    booking.refresh_from_db()
    assert booking.status == BookingStatus.PENDING


# ═══════════════════════════════════════════════════════════════════════════
# REMINDERS
# ═══════════════════════════════════════════════════════════════════════════
def test_reminds_both_parties_the_day_before(booking, photographer, buyer):
    from apps.notifications.models import Notification

    accepted = _accept(booking, photographer)
    accepted.event_date = timezone.localdate() + timedelta(days=1)
    accepted.save(update_fields=["event_date"])

    result = send_booking_reminders()

    assert result["reminders"] == 1
    for user in (buyer, photographer.user):
        assert Notification.objects.filter(
            recipient=user, notification_type="BOOKING_REMINDER"
        ).exists()


def test_no_reminder_for_an_unconfirmed_booking(booking):
    booking.event_date = timezone.localdate() + timedelta(days=1)
    booking.save(update_fields=["event_date"])

    assert send_booking_reminders()["reminders"] == 0


# ═══════════════════════════════════════════════════════════════════════════
# THE DATABASE BACKSTOP
# ═══════════════════════════════════════════════════════════════════════════
def test_the_constraint_is_translated_into_a_friendly_error(
    buyer, other_buyer, service, event_date, monkeypatch
):
    """
    Disable the application guard and let the MySQL constraint fire.

    Proves the last line of defence produces the same sentence a buyer can act
    on, rather than leaking `Duplicate entry '280|2026-09-25|16:00:00'`.
    """
    from apps.bookings import services

    create_booking(
        buyer=buyer,
        service=service,
        event_date=event_date,
        start_time=time(14, 0),
        location_address="F-7",
        location_city="Islamabad",
    )
    monkeypatch.setattr(services, "_assert_slot_available", lambda *a, **k: None)

    with pytest.raises(ConflictError, match="just taken"):
        create_booking(
            buyer=other_buyer,
            service=service,
            event_date=event_date,
            start_time=time(14, 0),
            location_address="F-7",
            location_city="Islamabad",
        )


def test_a_booking_survives_a_failing_metric_refresh(
    buyer, service, event_date, monkeypatch
):
    """
    Denormalised counters are a convenience. Failing the booking itself
    because a cached number could not be updated would be the wrong trade —
    the nightly job recomputes them anyway.
    """
    from apps.profiles import services as profile_services

    def boom(*args, **kwargs):
        raise RuntimeError("metrics backend down")

    monkeypatch.setattr(profile_services, "refresh_photographer_booking_metrics", boom)

    booking = create_booking(
        buyer=buyer,
        service=service,
        event_date=event_date,
        start_time=time(14, 0),
        location_address="F-7",
        location_city="Islamabad",
    )
    assert booking.status == BookingStatus.PENDING


def test_a_booking_survives_a_failing_interaction_log(
    buyer, service, event_date, monkeypatch
):
    """Analytics must never break the thing a user is trying to do."""
    from apps.recommendations.models import BuyerInteraction

    def boom(*args, **kwargs):
        raise RuntimeError("recommender offline")

    monkeypatch.setattr(BuyerInteraction.objects, "create", boom)

    booking = create_booking(
        buyer=buyer,
        service=service,
        event_date=event_date,
        start_time=time(14, 0),
        location_address="F-7",
        location_city="Islamabad",
    )
    assert booking.pk is not None


# ═══════════════════════════════════════════════════════════════════════════
# IDEMPOTENCY EDGE CASES
# ═══════════════════════════════════════════════════════════════════════════
def test_a_retry_while_the_first_call_is_still_running_is_refused(
    buyer, service, event_date
):
    """
    `cache.add` is set-if-absent and atomic, so the second of two simultaneous
    retries sees the in-progress marker instead of creating a duplicate.
    """
    from apps.bookings.services import _idempotency_cache_key

    cache.set(_idempotency_cache_key(buyer, "in-flight"), "__in_progress__", 60)

    with pytest.raises(ConflictError, match="still being processed"):
        create_booking(
            buyer=buyer,
            service=service,
            event_date=event_date,
            start_time=time(14, 0),
            location_address="F-7",
            location_city="Islamabad",
            idempotency_key="in-flight",
        )


def test_a_key_pointing_at_a_vanished_booking_is_reused(
    buyer, service, event_date
):
    """A stale key must not lock a legitimate request out forever."""
    from apps.bookings.services import _idempotency_cache_key

    cache.set(_idempotency_cache_key(buyer, "stale"), 999_999, 60)

    booking = create_booking(
        buyer=buyer,
        service=service,
        event_date=event_date,
        start_time=time(14, 0),
        location_address="F-7",
        location_city="Islamabad",
        idempotency_key="stale",
    )
    assert Booking.objects.filter(pk=booking.pk).exists()


def test_one_buyers_key_does_not_collide_with_anothers(
    buyer, other_buyer, service, event_date
):
    from conftest import working_date

    first = create_booking(
        buyer=buyer,
        service=service,
        event_date=event_date,
        start_time=time(14, 0),
        location_address="F-7",
        location_city="Islamabad",
        idempotency_key="shared-key",
    )
    second = create_booking(
        buyer=other_buyer,
        service=service,
        event_date=working_date(20),
        start_time=time(14, 0),
        location_address="F-7",
        location_city="Islamabad",
        idempotency_key="shared-key",
    )

    assert first.pk != second.pk
