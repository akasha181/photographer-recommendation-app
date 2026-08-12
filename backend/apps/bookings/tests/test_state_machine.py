"""
The booking state machine.

NFR-19 requires full coverage of these transitions, so this file is organised
around the transition table in `constants.py` rather than around the service
functions: every legal edge is exercised, every illegal edge is asserted to be
refused, and every edge is checked for the right *actor*.

    PENDING  → ACCEPTED   photographer only
             → REJECTED   photographer only, reason required
             → CANCELLED  buyer only
             → EXPIRED    system only
    ACCEPTED → COMPLETED  either party, not before the event
             → CANCELLED  either party
    REJECTED · CANCELLED · COMPLETED · EXPIRED  → terminal
"""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.bookings.constants import (
    ALLOWED_TRANSITIONS,
    BookingStatus,
    CancellationReason,
    can_transition,
)
from apps.bookings.models import BookingStatusHistory
from apps.bookings.services import (
    accept_booking,
    actor_role_for,
    cancel_booking,
    complete_booking,
    reject_booking,
    transition_booking,
)
from apps.core.exceptions import BusinessRuleViolation

pytestmark = pytest.mark.django_db


def _accepted(booking, photographer):
    return accept_booking(booking, photographer.user)


def _past_event(booking):
    """Move the event into the past so completion is allowed."""
    booking.event_date = timezone.localdate() - timedelta(days=1)
    booking.save(update_fields=["event_date"])
    return booking


# ═══════════════════════════════════════════════════════════════════════════
# THE TRANSITION TABLE ITSELF
# ═══════════════════════════════════════════════════════════════════════════
def test_terminal_states_have_no_successors():
    for terminal in (
        BookingStatus.REJECTED,
        BookingStatus.CANCELLED,
        BookingStatus.COMPLETED,
        BookingStatus.EXPIRED,
    ):
        assert ALLOWED_TRANSITIONS[terminal] == set()


@pytest.mark.parametrize(
    "current,target,role,allowed",
    [
        (BookingStatus.PENDING, BookingStatus.ACCEPTED, "PHOTOGRAPHER", True),
        (BookingStatus.PENDING, BookingStatus.ACCEPTED, "BUYER", False),
        (BookingStatus.PENDING, BookingStatus.REJECTED, "PHOTOGRAPHER", True),
        (BookingStatus.PENDING, BookingStatus.REJECTED, "BUYER", False),
        (BookingStatus.PENDING, BookingStatus.CANCELLED, "BUYER", True),
        (BookingStatus.PENDING, BookingStatus.CANCELLED, "PHOTOGRAPHER", False),
        (BookingStatus.PENDING, BookingStatus.EXPIRED, "SYSTEM", True),
        (BookingStatus.PENDING, BookingStatus.EXPIRED, "BUYER", False),
        (BookingStatus.PENDING, BookingStatus.COMPLETED, "PHOTOGRAPHER", False),
        (BookingStatus.ACCEPTED, BookingStatus.COMPLETED, "PHOTOGRAPHER", True),
        (BookingStatus.ACCEPTED, BookingStatus.COMPLETED, "BUYER", True),
        (BookingStatus.ACCEPTED, BookingStatus.CANCELLED, "BUYER", True),
        (BookingStatus.ACCEPTED, BookingStatus.CANCELLED, "PHOTOGRAPHER", True),
        (BookingStatus.ACCEPTED, BookingStatus.ACCEPTED, "PHOTOGRAPHER", False),
        (BookingStatus.COMPLETED, BookingStatus.CANCELLED, "BUYER", False),
        (BookingStatus.CANCELLED, BookingStatus.ACCEPTED, "PHOTOGRAPHER", False),
        (BookingStatus.REJECTED, BookingStatus.ACCEPTED, "PHOTOGRAPHER", False),
        (BookingStatus.EXPIRED, BookingStatus.ACCEPTED, "PHOTOGRAPHER", False),
        # ADMIN may perform any transition the table permits at all.
        (BookingStatus.PENDING, BookingStatus.ACCEPTED, "ADMIN", True),
        (BookingStatus.COMPLETED, BookingStatus.CANCELLED, "ADMIN", False),
    ],
)
def test_can_transition(current, target, role, allowed):
    assert can_transition(current, target, role) is allowed


# ═══════════════════════════════════════════════════════════════════════════
# ACTOR RESOLUTION
# ═══════════════════════════════════════════════════════════════════════════
def test_actor_role_identifies_each_party(booking, buyer, photographer, other_buyer, admin_user):
    assert actor_role_for(booking, buyer) == "BUYER"
    assert actor_role_for(booking, photographer.user) == "PHOTOGRAPHER"
    assert actor_role_for(booking, admin_user) == "ADMIN"
    assert actor_role_for(booking, other_buyer) == "OTHER"
    assert actor_role_for(booking, None) == "SYSTEM"


# ═══════════════════════════════════════════════════════════════════════════
# ACCEPT
# ═══════════════════════════════════════════════════════════════════════════
def test_photographer_accepts(booking, photographer):
    accepted = accept_booking(booking, photographer.user)

    assert accepted.status == BookingStatus.ACCEPTED
    assert accepted.accepted_at is not None
    assert accepted.responded_at is not None


def test_buyer_cannot_accept(booking, buyer):
    with pytest.raises(BusinessRuleViolation):
        accept_booking(booking, buyer)

    booking.refresh_from_db()
    assert booking.status == BookingStatus.PENDING


def test_a_stranger_cannot_accept(booking, other_buyer):
    with pytest.raises(BusinessRuleViolation):
        accept_booking(booking, other_buyer)


def test_cannot_accept_after_the_event_date(booking, photographer):
    _past_event(booking)

    with pytest.raises(BusinessRuleViolation, match="already passed"):
        accept_booking(booking, photographer.user)


def test_accepting_twice_is_refused(booking, photographer):
    accept_booking(booking, photographer.user)
    booking.refresh_from_db()

    with pytest.raises(BusinessRuleViolation, match="already accepted"):
        accept_booking(booking, photographer.user)


def test_response_time_is_recorded_once(booking, photographer, buyer):
    accepted = accept_booking(booking, photographer.user)
    first_response = accepted.responded_at

    cancel_booking(accepted, buyer)
    accepted.refresh_from_db()

    assert accepted.responded_at == first_response


# ═══════════════════════════════════════════════════════════════════════════
# REJECT
# ═══════════════════════════════════════════════════════════════════════════
def test_photographer_rejects_with_a_reason(booking, photographer):
    rejected = reject_booking(
        booking, photographer.user, reason="Already booked that morning."
    )

    assert rejected.status == BookingStatus.REJECTED
    assert rejected.rejection_reason == "Already booked that morning."
    assert rejected.rejected_at is not None


def test_rejection_requires_a_real_reason(booking, photographer):
    with pytest.raises(BusinessRuleViolation, match="why you cannot"):
        reject_booking(booking, photographer.user, reason="no")

    booking.refresh_from_db()
    assert booking.status == BookingStatus.PENDING


def test_buyer_cannot_reject(booking, buyer):
    with pytest.raises(BusinessRuleViolation):
        reject_booking(booking, buyer, reason="Changed my mind about this.")


def test_rejected_is_terminal(booking, photographer):
    rejected = reject_booking(booking, photographer.user, reason="Not available.")

    with pytest.raises(BusinessRuleViolation, match="can no longer be changed"):
        accept_booking(rejected, photographer.user)


# ═══════════════════════════════════════════════════════════════════════════
# CANCEL
# ═══════════════════════════════════════════════════════════════════════════
def test_buyer_cancels_a_pending_request(booking, buyer):
    cancelled = cancel_booking(booking, buyer)

    assert cancelled.status == BookingStatus.CANCELLED
    assert cancelled.cancelled_by_id == buyer.id
    assert cancelled.cancellation_reason == CancellationReason.BUYER_CHANGED_PLANS


def test_photographer_cannot_cancel_a_pending_request(booking, photographer):
    """A pending request is declined, not cancelled — the distinction matters
    because a rejection carries a reason the buyer can act on."""
    with pytest.raises(BusinessRuleViolation):
        cancel_booking(booking, photographer.user, note="Not free.")


def test_either_party_cancels_an_accepted_booking(booking, photographer, buyer):
    accepted = _accepted(booking, photographer)
    cancelled = cancel_booking(accepted, buyer, reason="EVENT_CANCELLED")

    assert cancelled.status == BookingStatus.CANCELLED
    assert cancelled.cancellation_reason == CancellationReason.EVENT_CANCELLED


def test_photographer_cancelling_a_confirmed_booking_must_explain(booking, photographer):
    accepted = _accepted(booking, photographer)

    with pytest.raises(BusinessRuleViolation, match="explain why"):
        cancel_booking(accepted, photographer.user)

    accepted.refresh_from_db()
    assert accepted.status == BookingStatus.ACCEPTED


def test_photographer_cancels_a_confirmed_booking_with_a_note(booking, photographer):
    accepted = _accepted(booking, photographer)
    cancelled = cancel_booking(
        accepted, photographer.user, note="Equipment failure, cannot cover the event."
    )

    assert cancelled.status == BookingStatus.CANCELLED
    assert "Equipment failure" in cancelled.cancellation_note


def test_rejects_an_unknown_cancellation_reason(booking, buyer):
    with pytest.raises(BusinessRuleViolation, match="not a valid cancellation reason"):
        cancel_booking(booking, buyer, reason="I_JUST_FELT_LIKE_IT")


def test_late_cancellation_is_flagged_in_the_history(booking):
    """
    Cancelling inside FREE_CANCELLATION_HOURS is recorded, because that is the
    fact a dispute turns on later.

    The event is pinned to exactly 24 hours away rather than to a fixed
    calendar date. A date two days out sits inside the 48-hour window when the
    suite runs in the evening and outside it when it runs in the morning —
    which made an earlier version of this test pass or fail depending on the
    clock.
    """
    now = timezone.localtime()
    booking.event_date = now.date() + timedelta(days=1)
    booking.start_time = now.time()
    booking.save(update_fields=["event_date", "start_time"])

    cancelled = cancel_booking(booking, booking.buyer)
    note = BookingStatusHistory.objects.filter(booking=cancelled).last().note

    assert "of the event" in note


def test_an_early_cancellation_is_not_flagged(booking):
    """The mirror case: well outside the window, no annotation."""
    now = timezone.localtime()
    booking.event_date = now.date() + timedelta(days=30)
    booking.start_time = now.time()
    booking.save(update_fields=["event_date", "start_time"])

    cancelled = cancel_booking(booking, booking.buyer)
    note = BookingStatusHistory.objects.filter(booking=cancelled).last().note

    assert "of the event" not in note


# ═══════════════════════════════════════════════════════════════════════════
# COMPLETE
# ═══════════════════════════════════════════════════════════════════════════
def test_photographer_completes_after_the_event(booking, photographer):
    accepted = _accepted(booking, photographer)
    _past_event(accepted)

    completed = complete_booking(accepted, photographer.user)

    assert completed.status == BookingStatus.COMPLETED
    assert completed.completed_at is not None
    assert completed.photographer_marked_complete is True


def test_buyer_completes_after_the_event(booking, photographer, buyer):
    accepted = _accepted(booking, photographer)
    _past_event(accepted)

    completed = complete_booking(accepted, buyer)

    assert completed.status == BookingStatus.COMPLETED
    assert completed.buyer_confirmed_completion is True


def test_cannot_complete_before_the_event(booking, photographer):
    accepted = _accepted(booking, photographer)

    with pytest.raises(BusinessRuleViolation, match="has not happened yet"):
        complete_booking(accepted, photographer.user)


def test_cannot_complete_a_pending_booking(booking, photographer):
    _past_event(booking)

    with pytest.raises(BusinessRuleViolation):
        complete_booking(booking, photographer.user)


def test_completed_booking_becomes_reviewable(booking, photographer):
    accepted = _accepted(booking, photographer)
    _past_event(accepted)
    completed = complete_booking(accepted, photographer.user)

    assert completed.is_reviewable is True
    assert completed.is_terminal is True


def test_completed_is_terminal(booking, photographer, buyer):
    accepted = _accepted(booking, photographer)
    _past_event(accepted)
    completed = complete_booking(accepted, photographer.user)

    with pytest.raises(BusinessRuleViolation, match="can no longer be changed"):
        cancel_booking(completed, buyer)


# ═══════════════════════════════════════════════════════════════════════════
# EXPIRY (system actor)
# ═══════════════════════════════════════════════════════════════════════════
def test_system_expires_a_pending_booking(booking):
    expired = transition_booking(
        booking, to_status=BookingStatus.EXPIRED, actor=None, note="No response."
    )

    assert expired.status == BookingStatus.EXPIRED
    assert BookingStatusHistory.objects.filter(
        booking=expired, actor_role="SYSTEM"
    ).exists()


def test_a_buyer_cannot_expire_a_booking(booking, buyer):
    with pytest.raises(BusinessRuleViolation):
        transition_booking(booking, to_status=BookingStatus.EXPIRED, actor=buyer)


def test_the_expiry_task_sweeps_overdue_requests(booking):
    from apps.bookings.tasks import expire_pending_bookings

    booking.expires_at = timezone.now() - timedelta(hours=1)
    booking.save(update_fields=["expires_at"])

    result = expire_pending_bookings()
    booking.refresh_from_db()

    assert result["expired"] == 1
    assert booking.status == BookingStatus.EXPIRED


def test_the_expiry_task_leaves_accepted_bookings_alone(booking, photographer):
    from apps.bookings.tasks import expire_pending_bookings

    accepted = _accepted(booking, photographer)
    accepted.expires_at = timezone.now() - timedelta(hours=1)
    accepted.save(update_fields=["expires_at"])

    expire_pending_bookings()
    accepted.refresh_from_db()

    assert accepted.status == BookingStatus.ACCEPTED


# ═══════════════════════════════════════════════════════════════════════════
# ADMIN OVERRIDE
# ═══════════════════════════════════════════════════════════════════════════
def test_admin_can_accept_on_a_photographers_behalf(booking, admin_user):
    accepted = transition_booking(
        booking,
        to_status=BookingStatus.ACCEPTED,
        actor=admin_user,
        note="Confirmed by support over the phone.",
    )

    assert accepted.status == BookingStatus.ACCEPTED
    assert BookingStatusHistory.objects.filter(
        booking=accepted, actor_role="ADMIN"
    ).exists()


def test_admin_cannot_perform_an_impossible_transition(booking, admin_user, photographer):
    rejected = reject_booking(booking, photographer.user, reason="Not available.")

    with pytest.raises(BusinessRuleViolation):
        transition_booking(
            rejected, to_status=BookingStatus.ACCEPTED, actor=admin_user
        )


# ═══════════════════════════════════════════════════════════════════════════
# AUDIT TRAIL
# ═══════════════════════════════════════════════════════════════════════════
def test_every_transition_appends_exactly_one_history_row(booking, photographer, buyer):
    accepted = _accepted(booking, photographer)
    _past_event(accepted)
    complete_booking(accepted, buyer)

    rows = list(
        BookingStatusHistory.objects.filter(booking=booking).order_by("created_at")
    )
    assert [row.to_status for row in rows] == [
        BookingStatus.PENDING,
        BookingStatus.ACCEPTED,
        BookingStatus.COMPLETED,
    ]
    assert [row.actor_role for row in rows] == ["BUYER", "PHOTOGRAPHER", "BUYER"]


def test_a_refused_transition_writes_no_history(booking, buyer):
    before = BookingStatusHistory.objects.filter(booking=booking).count()

    with pytest.raises(BusinessRuleViolation):
        accept_booking(booking, buyer)

    assert BookingStatusHistory.objects.filter(booking=booking).count() == before


def test_photographer_metrics_follow_the_booking(booking, photographer):
    accepted = _accepted(booking, photographer)
    _past_event(accepted)
    complete_booking(accepted, photographer.user)

    photographer.refresh_from_db()
    assert photographer.total_bookings == 1
    assert photographer.completed_bookings == 1


def test_buyer_metrics_follow_the_booking(booking, photographer, buyer):
    accepted = _accepted(booking, photographer)
    _past_event(accepted)
    completed = complete_booking(accepted, photographer.user)

    buyer.buyer_profile.refresh_from_db()
    assert buyer.buyer_profile.completed_bookings == 1
    assert buyer.buyer_profile.total_spent == completed.total_price
