"""
The booking state machine — Module 7.

This module is the only place a booking is created or moved between states.
Views never write to `Booking.status` themselves, which is what makes the
guarantees below true of the whole system rather than of one endpoint.

FOUR THINGS THIS FILE GUARANTEES
--------------------------------
1. NO DOUBLE BOOKING.
   The availability check and the INSERT happen inside one transaction with
   the photographer's row locked (`select_for_update`). Two buyers racing for
   the last Saturday in December serialize behind that lock, so the loser is
   told "that slot was just taken" instead of both succeeding. The database
   constraint `uniq_active_booking_slot` still exists underneath as the last
   line of defence — but it is a backstop, not the mechanism. Relying on it
   alone would surface a raw integrity error to the user.

2. PRICE IS SNAPSHOTTED.
   `unit_price` is copied from the service (or the chosen package) at creation
   and never read again. A photographer raising their rate tomorrow must not
   silently rewrite a booking the buyer already agreed to.

3. EVERY TRANSITION IS LEGAL AND ATTRIBUTED.
   `can_transition(current, target, actor_role)` from constants.py is the only
   authority on legality, and every accepted change appends a row to
   `BookingStatusHistory` naming who did it. That table is append-only; during
   a dispute it is the evidence.

4. NOTIFICATIONS NEVER LIE.
   `notify()` defers delivery to `transaction.on_commit`, so a rolled-back
   transaction cannot tell a photographer they have a booking they do not.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from decimal import Decimal

from django.conf import settings
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.bookings.constants import (
    BookingStatus,
    CancellationReason,
    can_transition,
)
from apps.bookings.models import Booking, BookingPayment, BookingStatusHistory
from apps.core.constants import UserRole
from apps.core.exceptions import BusinessRuleViolation, ConflictError

logger = logging.getLogger("snapsphere")

#: How long an `Idempotency-Key` is honoured. A retry after a day is a new
#: intent, not a duplicate of the original request.
IDEMPOTENCY_TTL_SECONDS = 24 * 60 * 60
_IN_PROGRESS = "__in_progress__"


# ═══════════════════════════════════════════════════════════════════════════
# ACTOR RESOLUTION
# ═══════════════════════════════════════════════════════════════════════════
def actor_role_for(booking: Booking, user) -> str:
    """
    Which side of this booking is acting.

    The role recorded in history is the user's relationship *to this booking*,
    not their account type — that is the distinction that makes the audit
    trail readable. An admin acting on someone else's booking is ADMIN, and
    `can_transition` lets ADMIN perform any legal transition.
    """
    if user is None:
        return "SYSTEM"
    if getattr(user, "role", None) == UserRole.ADMIN:
        return "ADMIN"
    if booking.buyer_id == user.id:
        return "BUYER"
    if booking.photographer.user_id == user.id:
        return "PHOTOGRAPHER"
    return "OTHER"


# ═══════════════════════════════════════════════════════════════════════════
# CREATE
# ═══════════════════════════════════════════════════════════════════════════
def create_booking(
    *,
    buyer,
    service,
    event_date,
    start_time,
    location_address: str,
    location_city: str,
    package=None,
    duration_hours: int | None = None,
    location_latitude: Decimal | None = None,
    location_longitude: Decimal | None = None,
    guest_count: int | None = None,
    notes: str = "",
    special_requirements: str = "",
    idempotency_key: str | None = None,
) -> Booking:
    """
    Create a PENDING booking request.

    Returns the existing booking unchanged when `idempotency_key` has already
    been used by this buyer — a flaky mobile connection that retries a POST
    must not produce two requests to the same photographer.
    """
    if idempotency_key:
        existing = _claim_idempotency_key(buyer, idempotency_key)
        if existing is not None:
            return existing

    try:
        booking = _create_booking_locked(
            buyer=buyer,
            service=service,
            package=package,
            event_date=event_date,
            start_time=start_time,
            duration_hours=duration_hours,
            location_address=location_address,
            location_city=location_city,
            location_latitude=location_latitude,
            location_longitude=location_longitude,
            guest_count=guest_count,
            notes=notes,
            special_requirements=special_requirements,
        )
    except IntegrityError as exc:
        # The database backstop fired. Reaching here means the application
        # guard above was bypassed somehow; translate it into the same
        # friendly message rather than leaking a MySQL error string.
        _release_idempotency_key(buyer, idempotency_key)
        if "uniq_active_booking_slot" in str(exc):
            raise ConflictError(
                "That time slot was just taken. Please choose another."
            ) from exc
        raise
    except Exception:
        _release_idempotency_key(buyer, idempotency_key)
        raise

    _store_idempotency_result(buyer, idempotency_key, booking.pk)
    return booking


@transaction.atomic
def _create_booking_locked(
    *,
    buyer,
    service,
    package,
    event_date,
    start_time,
    duration_hours,
    location_address,
    location_city,
    location_latitude,
    location_longitude,
    guest_count,
    notes,
    special_requirements,
) -> Booking:
    from apps.profiles.models import PhotographerProfile

    _assert_buyer(buyer)
    _assert_service_bookable(service)

    # ─── The lock ────────────────────────────────────────────────────────────
    # Everything after this line is serialized per photographer. It must stay
    # short: an expensive call here would block every other buyer looking at
    # the same photographer.
    photographer = PhotographerProfile.objects.select_for_update().get(
        pk=service.photographer_id
    )

    _assert_photographer_bookable(photographer, buyer)
    _assert_buyer_within_limit(buyer)
    _assert_slot_available(photographer, event_date, start_time)

    # ─── Price snapshot ──────────────────────────────────────────────────────
    unit_price, quantity, hours = _price_snapshot(service, package, duration_hours)

    booking = Booking(
        buyer=buyer,
        photographer=photographer,
        service=service,
        package=package,
        category=service.category,
        event_date=event_date,
        start_time=start_time,
        end_time=_end_time(start_time, hours),
        duration_hours=hours,
        location_address=location_address,
        location_city=location_city,
        location_latitude=location_latitude,
        location_longitude=location_longitude,
        unit_price=unit_price,
        quantity=quantity,
        commission_percent=Decimal(str(settings.PLATFORM_COMMISSION_PERCENT)),
        status=BookingStatus.PENDING,
        guest_count=guest_count,
        notes=notes or "",
        special_requirements=special_requirements or "",
        expires_at=_expiry_for(event_date, start_time),
    )
    booking.calculate_totals()
    booking.save()

    BookingPayment.objects.create(booking=booking)

    _record_history(
        booking,
        from_status="",
        to_status=BookingStatus.PENDING,
        actor=buyer,
        actor_role="BUYER",
        note="Booking requested.",
    )
    _refresh_metrics(booking)
    _log_interaction(buyer, photographer, service)

    from apps.notifications.services import notify

    notify(
        photographer.user,
        "BOOKING_REQUEST",
        title="New booking request",
        body=(
            f"{buyer.full_name} wants to book {service.title} on "
            f"{event_date:%d %b %Y} at {start_time:%H:%M}."
        ),
        action_screen="BookingDetail",
        action_id=str(booking.pk),
        actor=buyer,
        payload={"booking_id": booking.pk, "reference": booking.reference},
    )

    logger.info(
        "Booking created",
        extra={
            "booking_id": booking.pk,
            "buyer_id": buyer.id,
            "photographer_id": photographer.pk,
        },
    )
    return booking


# ═══════════════════════════════════════════════════════════════════════════
# TRANSITIONS
# ═══════════════════════════════════════════════════════════════════════════
@transaction.atomic
def transition_booking(
    booking: Booking,
    *,
    to_status: str,
    actor,
    note: str = "",
    updates: dict | None = None,
) -> Booking:
    """
    The single gateway for every status change.

    Re-reads the booking under a row lock before deciding. Without that, two
    photographers' devices tapping Accept and Reject at the same moment would
    both read PENDING, both pass the legality check, and the second write
    would silently overwrite the first.
    """
    locked = Booking.objects.select_for_update().get(pk=booking.pk)
    role = actor_role_for(locked, actor)
    from_status = locked.status

    if from_status == to_status:
        raise BusinessRuleViolation(
            f"This booking is already {locked.get_status_display().lower()}."
        )
    if not can_transition(from_status, to_status, role):
        raise BusinessRuleViolation(_illegal_message(from_status, to_status, role))

    now = timezone.now()
    fields = ["status", "updated_at"]
    locked.status = to_status

    # First response from the photographer — feeds avg_response_time_hours,
    # which the ranking model uses. Set once, never overwritten.
    if (
        from_status == BookingStatus.PENDING
        and role == "PHOTOGRAPHER"
        and locked.responded_at is None
    ):
        locked.responded_at = now
        fields.append("responded_at")

    stamp = {
        BookingStatus.ACCEPTED: "accepted_at",
        BookingStatus.REJECTED: "rejected_at",
        BookingStatus.CANCELLED: "cancelled_at",
        BookingStatus.COMPLETED: "completed_at",
    }.get(to_status)
    if stamp:
        setattr(locked, stamp, now)
        fields.append(stamp)

    for field, value in (updates or {}).items():
        setattr(locked, field, value)
        fields.append(field)

    locked.save(update_fields=list(dict.fromkeys(fields)))

    _record_history(
        locked,
        from_status=from_status,
        to_status=to_status,
        actor=actor,
        actor_role=role,
        note=note,
    )
    _refresh_metrics(locked)
    _notify_transition(locked, from_status, to_status, actor, note)

    logger.info(
        "Booking transitioned",
        extra={
            "booking_id": locked.pk,
            "from": from_status,
            "to": to_status,
            "actor_role": role,
        },
    )
    return locked


def accept_booking(booking: Booking, actor, *, note: str = "") -> Booking:
    """
    Photographer confirms the job.

    Deliberately permitted even when `expires_at` has passed but the sweeper
    has not run yet: the booking is still PENDING, the slot is still held, and
    punishing a photographer for a 15-minute cron interval helps nobody.
    """
    if booking.event_date < timezone.localdate():
        raise BusinessRuleViolation(
            "This event date has already passed. Cancel the request instead."
        )
    return transition_booking(
        booking,
        to_status=BookingStatus.ACCEPTED,
        actor=actor,
        note=note or "Booking accepted by the photographer.",
    )


def reject_booking(booking: Booking, actor, *, reason: str) -> Booking:
    """
    Photographer declines. A reason is mandatory.

    A bare "declined" gives the buyer nothing to act on; "I'm already booked
    that morning, but the afternoon is free" turns a dead end into a
    rebooking.
    """
    reason = (reason or "").strip()
    if len(reason) < 5:
        raise BusinessRuleViolation(
            "Please tell the buyer why you cannot take this booking."
        )
    return transition_booking(
        booking,
        to_status=BookingStatus.REJECTED,
        actor=actor,
        note=reason,
        updates={"rejection_reason": reason[:500]},
    )


def cancel_booking(
    booking: Booking, actor, *, reason: str = "", note: str = ""
) -> Booking:
    """
    Either party backs out.

    A photographer cancelling a booking they already ACCEPTED is a broken
    commitment, so a reason is required from them; a buyer withdrawing a
    request nobody has answered yet is not, and demanding one would just make
    them abandon the screen.
    """
    role = actor_role_for(booking, actor)
    reason = (reason or "").strip().upper()

    if reason and reason not in CancellationReason.values:
        raise BusinessRuleViolation("That is not a valid cancellation reason.")
    if not reason:
        reason = (
            CancellationReason.PHOTOGRAPHER_UNAVAILABLE
            if role == "PHOTOGRAPHER"
            else CancellationReason.BUYER_CHANGED_PLANS
        )
    if role == "PHOTOGRAPHER" and booking.status == BookingStatus.ACCEPTED:
        if not (note or "").strip():
            raise BusinessRuleViolation(
                "Please explain why you are cancelling a confirmed booking."
            )

    history_note = note.strip() if note else CancellationReason(reason).label
    if _is_late_cancellation(booking):
        history_note = (
            f"{history_note} (within {settings.FREE_CANCELLATION_HOURS}h of the event)"
        )

    return transition_booking(
        booking,
        to_status=BookingStatus.CANCELLED,
        actor=actor,
        note=history_note[:500],
        updates={
            "cancellation_reason": reason,
            "cancellation_note": (note or "")[:500],
            "cancelled_by": actor,
        },
    )


def complete_booking(booking: Booking, actor, *, note: str = "") -> Booking:
    """
    The shoot happened.

    Refused before the event date: a booking cannot be completed before it has
    taken place, and allowing it would let a photographer close a job early to
    unlock the review prompt.
    """
    if booking.event_date > timezone.localdate():
        raise BusinessRuleViolation(
            "This shoot has not happened yet. It can be marked complete from "
            f"{booking.event_date:%d %b %Y}."
        )

    role = actor_role_for(booking, actor)
    updates = {}
    if role == "PHOTOGRAPHER":
        updates["photographer_marked_complete"] = True
    elif role == "BUYER":
        updates["buyer_confirmed_completion"] = True

    return transition_booking(
        booking,
        to_status=BookingStatus.COMPLETED,
        actor=actor,
        note=note or "Marked complete.",
        updates=updates,
    )


# ═══════════════════════════════════════════════════════════════════════════
# GUARDS
# Each raises a sentence a buyer can act on. "Validation failed" is not one.
# ═══════════════════════════════════════════════════════════════════════════
def _assert_buyer(buyer) -> None:
    if getattr(buyer, "role", None) != UserRole.BUYER:
        raise BusinessRuleViolation("Only buyer accounts can request bookings.")


def _assert_service_bookable(service) -> None:
    if service is None or service.is_deleted or not service.is_active:
        raise BusinessRuleViolation("This service is no longer available to book.")


def _assert_photographer_bookable(photographer, buyer) -> None:
    # Unreachable while `_assert_buyer` runs first — a photographer's own user
    # has role PHOTOGRAPHER and is turned away there. Kept as an invariant
    # guard so reordering these checks cannot quietly allow self-booking.
    if photographer.user_id == buyer.id:
        raise BusinessRuleViolation("You cannot book yourself.")
    if not photographer.is_publicly_visible:
        raise BusinessRuleViolation("This photographer is not available right now.")
    if not photographer.is_accepting_bookings:
        raise BusinessRuleViolation(
            f"{photographer.display_name} is not accepting new bookings at the moment."
        )


def _assert_buyer_within_limit(buyer) -> None:
    """
    Cap concurrent unanswered requests.

    Without it one buyer can blanket twenty photographers with requests, hold
    twenty calendar slots hostage, and accept whichever answers first — every
    other buyer loses those dates in the meantime.
    """
    limit = settings.MAX_PENDING_BOOKINGS_PER_BUYER
    pending = Booking.objects.filter(
        buyer=buyer, status=BookingStatus.PENDING
    ).count()
    if pending >= limit:
        raise BusinessRuleViolation(
            f"You already have {pending} requests awaiting a reply. Please wait "
            f"for a response or cancel one before sending another."
        )


def _assert_slot_available(photographer, event_date, start_time) -> None:
    """
    Weekday rule, blackout, capacity — then the exact start time.

    Runs while the photographer row is locked, so its answer is still true by
    the time the INSERT lands.
    """
    from apps.availability import selectors as availability

    day = availability.day_availability(photographer, event_date)
    if not day.is_available:
        raise BusinessRuleViolation(day.message)

    if start_time.strftime("%H:%M") in day.booked_times:
        raise ConflictError(
            f"{start_time:%H:%M} on {event_date:%d %b} is already booked. "
            f"Please choose another time."
        )


# ═══════════════════════════════════════════════════════════════════════════
# PRICING & TIMING
# ═══════════════════════════════════════════════════════════════════════════
def _price_snapshot(service, package, requested_hours) -> tuple[Decimal, int, int]:
    """
    Work out (unit_price, quantity, duration_hours) from the catalogue.

    A package is a fixed offer, so it always costs its own price for its own
    duration. An hourly service multiplies by the hours the buyer asked for,
    floored at the photographer's stated minimum.
    """
    from apps.catalog.models import PricingUnit

    if package is not None:
        return package.price, 1, package.duration_hours or service.duration_hours

    hours = int(requested_hours or service.duration_hours or 1)
    hours = max(hours, service.min_hours or 1)

    if service.pricing_unit == PricingUnit.PER_HOUR:
        return service.price, hours, hours
    return service.price, 1, hours


def _end_time(start_time, hours: int):
    base = datetime.combine(timezone.localdate(), start_time) + timedelta(hours=hours)
    return base.time()


def _expiry_for(event_date, start_time):
    """
    When an unanswered request gives up.

    Capped at the event itself: a 48-hour window on a shoot that is 30 hours
    away would leave the request "live" after the event had already happened.
    """
    now = timezone.now()
    window = now + timedelta(hours=settings.BOOKING_EXPIRY_HOURS)

    naive_event = datetime.combine(event_date, start_time)
    event_at = timezone.make_aware(naive_event, timezone.get_current_timezone())

    return max(min(window, event_at), now + timedelta(minutes=30))


def _is_late_cancellation(booking: Booking) -> bool:
    naive_event = datetime.combine(booking.event_date, booking.start_time)
    event_at = timezone.make_aware(naive_event, timezone.get_current_timezone())
    return event_at - timezone.now() < timedelta(
        hours=settings.FREE_CANCELLATION_HOURS
    )


# ═══════════════════════════════════════════════════════════════════════════
# SIDE EFFECTS
# ═══════════════════════════════════════════════════════════════════════════
def _record_history(
    booking: Booking, *, from_status: str, to_status: str, actor, actor_role: str,
    note: str = "",
) -> BookingStatusHistory:
    """Append-only. Never updated, never deleted."""
    return BookingStatusHistory.objects.create(
        booking=booking,
        from_status=from_status,
        to_status=to_status,
        changed_by=actor,
        actor_role=actor_role,
        note=note[:500],
    )


def _refresh_metrics(booking: Booking) -> None:
    """
    Keep the denormalised counters honest.

    Runs inside the same transaction as the change that caused it, so the
    numbers on the photographer's profile can never reflect a booking that
    rolled back. The nightly job recomputes the same values as a backstop.
    """
    from apps.profiles.services import (
        refresh_buyer_booking_metrics,
        refresh_photographer_booking_metrics,
    )

    try:
        refresh_photographer_booking_metrics(booking.photographer)
        refresh_buyer_booking_metrics(booking.buyer)
    except Exception:  # noqa: BLE001
        # Counters are a convenience; the nightly job heals them. Failing the
        # booking itself because a cached number could not be updated would be
        # the wrong trade.
        logger.warning("Metric refresh failed for booking %s", booking.pk, exc_info=True)


def _log_interaction(buyer, photographer, service) -> None:
    """Record the request as explicit feedback for the recommender."""
    try:
        from apps.recommendations.models import BuyerInteraction, BuyerInteractionType

        BuyerInteraction.objects.create(
            buyer=buyer,
            photographer=photographer,
            interaction_type=BuyerInteractionType.BOOKING,
            category=service.category,
        )
    except Exception:  # noqa: BLE001
        pass


def _notify_transition(booking, from_status, to_status, actor, note) -> None:
    """
    Tell the other party — never the person who pressed the button.

    `notify()` defers to `transaction.on_commit`, so nothing is sent for a
    transaction that later rolls back.
    """
    from apps.notifications.services import notify

    buyer, photographer_user = booking.buyer, booking.photographer.user
    photographer_name = booking.photographer.display_name
    when = f"{booking.event_date:%d %b %Y}"

    messages = {
        BookingStatus.ACCEPTED: (
            buyer,
            "BOOKING_ACCEPTED",
            "Booking confirmed",
            f"{photographer_name} accepted your booking for {when}.",
        ),
        BookingStatus.REJECTED: (
            buyer,
            "BOOKING_REJECTED",
            "Booking declined",
            f"{photographer_name} could not take your booking for {when}."
            + (f" Reason: {note}" if note else ""),
        ),
        BookingStatus.COMPLETED: (
            buyer,
            "BOOKING_COMPLETED",
            "Shoot complete",
            f"Your shoot with {photographer_name} is marked complete. "
            f"Leave a review to help other buyers.",
        ),
    }

    if to_status == BookingStatus.CANCELLED:
        # The recipient depends on who cancelled, so it cannot be table-driven.
        cancelled_by_buyer = actor is not None and actor.id == buyer.id
        recipient = photographer_user if cancelled_by_buyer else buyer
        who = buyer.full_name if cancelled_by_buyer else photographer_name
        notify(
            recipient,
            "BOOKING_CANCELLED",
            title="Booking cancelled",
            body=f"{who} cancelled the booking for {when}."
            + (f" Reason: {note}" if note else ""),
            action_screen="BookingDetail",
            action_id=str(booking.pk),
            actor=actor,
        )
        return

    entry = messages.get(to_status)
    if entry is None:
        return
    recipient, notification_type, title, body = entry
    notify(
        recipient,
        notification_type,
        title=title,
        body=body,
        action_screen="BookingDetail",
        action_id=str(booking.pk),
        actor=actor,
    )


def _illegal_message(from_status: str, to_status: str, role: str) -> str:
    """Explain the refusal in terms of the booking, not the state machine."""
    from apps.bookings.constants import ALLOWED_TRANSITIONS

    current = BookingStatus(from_status).label.lower()
    if to_status not in ALLOWED_TRANSITIONS.get(from_status, set()):
        if not ALLOWED_TRANSITIONS.get(from_status):
            return f"This booking is {current} and can no longer be changed."
        return f"A {current} booking cannot be {BookingStatus(to_status).label.lower()}."
    return "You are not allowed to make this change to this booking."


# ═══════════════════════════════════════════════════════════════════════════
# IDEMPOTENCY
# A dropped response on a flaky mobile connection makes the app retry the
# POST. Without this, the buyer gets two identical requests — and because the
# first one already holds the slot, the second fails with a confusing
# "already booked" error naming their own booking.
# ═══════════════════════════════════════════════════════════════════════════
def _idempotency_cache_key(buyer, key: str) -> str:
    return f"booking:idem:{buyer.id}:{key}"


def _claim_idempotency_key(buyer, key: str) -> Booking | None:
    """
    Claim the key, or return what the first call produced.

    `cache.add` is set-if-absent and atomic, so two simultaneous retries
    cannot both pass this point.
    """
    cache_key = _idempotency_cache_key(buyer, key)
    if cache.add(cache_key, _IN_PROGRESS, IDEMPOTENCY_TTL_SECONDS):
        return None

    stored = cache.get(cache_key)
    if stored == _IN_PROGRESS:
        raise ConflictError(
            "This booking request is still being processed. Please wait a moment."
        )
    booking = Booking.objects.filter(pk=stored, buyer=buyer).first()
    if booking is None:
        # The key is known but the booking is gone — treat it as a fresh call
        # rather than failing a legitimate request forever.
        cache.set(cache_key, _IN_PROGRESS, IDEMPOTENCY_TTL_SECONDS)
        return None
    logger.info("Idempotent replay of booking %s", booking.pk)
    return booking


def _store_idempotency_result(buyer, key: str | None, booking_id: int) -> None:
    if key:
        cache.set(
            _idempotency_cache_key(buyer, key), booking_id, IDEMPOTENCY_TTL_SECONDS
        )


def _release_idempotency_key(buyer, key: str | None) -> None:
    """A failed attempt must not lock the key out for 24 hours."""
    if key:
        cache.delete(_idempotency_cache_key(buyer, key))
