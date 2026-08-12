"""
Read-side queries for bookings.

THE ONE RULE THIS MODULE ENFORCES
---------------------------------
Every queryset that leaves this module is already scoped to the caller.
`for_user()` on the manager decides buyer-side or photographer-side from the
role, so no view can accidentally serve a list that spans users. Object-level
access is then re-checked by `IsBookingParticipant`, because two independent
guards is the right number for a table holding money.

Every list path goes through `.with_details()`. A 20-row page without it fires
one query per booking for the photographer, the user behind the photographer,
the service and its category — 81 queries instead of 1.
"""

from __future__ import annotations

from django.db.models import Count, Prefetch, Q, QuerySet
from django.utils import timezone

from apps.bookings.constants import BookingStatus
from apps.bookings.models import Booking, BookingStatusHistory

#: Named tabs the mobile app shows, mapped to the statuses each contains.
#: Defined here rather than in the client so the two cannot drift apart.
STATUS_GROUPS: dict[str, list[str]] = {
    "pending": [BookingStatus.PENDING],
    "upcoming": [BookingStatus.ACCEPTED],
    "completed": [BookingStatus.COMPLETED],
    "cancelled": [
        BookingStatus.CANCELLED,
        BookingStatus.REJECTED,
        BookingStatus.EXPIRED,
    ],
}


def _base(user) -> QuerySet[Booking]:
    return Booking.objects.for_user(user).with_details()


def get_buyer_bookings(user, *, group: str | None = None, status: str | None = None):
    """Bookings a buyer has made, newest first."""
    return _apply_filters(Booking.objects.for_buyer(user).with_details(), group, status)


def get_photographer_bookings(
    user, *, group: str | None = None, status: str | None = None
):
    """Bookings a photographer has received — their Requests / Jobs screen."""
    return _apply_filters(
        Booking.objects.for_photographer(user).with_details(), group, status
    )


def get_user_bookings(user, *, group: str | None = None, status: str | None = None):
    """Role-agnostic entry point used by the shared list endpoint."""
    return _apply_filters(_base(user), group, status)


def _apply_filters(qs: QuerySet[Booking], group: str | None, status: str | None):
    """
    `group` is the app-facing tab; `status` is the precise filter.

    An unknown value for either returns the unfiltered queryset rather than an
    empty one — a typo in a query string should not render as "you have no
    bookings", which is indistinguishable from a real empty state.
    """
    if group and group in STATUS_GROUPS:
        qs = qs.filter(status__in=STATUS_GROUPS[group])
    elif status:
        qs = qs.filter(status=status.upper())
    return qs.order_by("-created_at")


def get_booking_for_user(user, pk: int) -> Booking | None:
    """
    Detail fetch, scoped to the caller and pre-joined with its timeline.

    Returns None rather than raising so the view chooses the response — and it
    must choose 404, since "this booking exists but is not yours" is itself
    information worth withholding.
    """
    return (
        _base(user)
        .prefetch_related(
            Prefetch(
                "status_history",
                queryset=BookingStatusHistory.objects.select_related(
                    "changed_by"
                ).order_by("created_at"),
            ),
            "payment",
        )
        .filter(pk=pk)
        .first()
    )


def get_booking_by_uuid(user, uuid) -> Booking | None:
    return _base(user).filter(uuid=uuid).first()


# ═══════════════════════════════════════════════════════════════════════════
# COUNTS & SUMMARIES
# ═══════════════════════════════════════════════════════════════════════════
def booking_counts(user) -> dict[str, int]:
    """
    Tab badge counts in a single aggregate query.

    Four separate `COUNT(*)` round trips to paint four tab badges is the kind
    of thing that makes a screen feel slow for no reason.
    """
    row = _base(user).aggregate(
        pending=Count("id", filter=Q(status=BookingStatus.PENDING)),
        upcoming=Count("id", filter=Q(status=BookingStatus.ACCEPTED)),
        completed=Count("id", filter=Q(status=BookingStatus.COMPLETED)),
        cancelled=Count(
            "id",
            filter=Q(
                status__in=[
                    BookingStatus.CANCELLED,
                    BookingStatus.REJECTED,
                    BookingStatus.EXPIRED,
                ]
            ),
        ),
    )
    row["total"] = sum(row.values())
    return row


def upcoming_bookings(user, limit: int = 5):
    """Next few confirmed shoots — the card at the top of the home screen."""
    return (
        _base(user)
        .filter(status=BookingStatus.ACCEPTED, event_date__gte=timezone.localdate())
        .order_by("event_date", "start_time")[:limit]
    )


def pending_requests_count(photographer_user) -> int:
    """Badge on the photographer's Requests tab."""
    return (
        Booking.objects.for_photographer(photographer_user)
        .filter(status=BookingStatus.PENDING)
        .count()
    )


def has_booking_between(buyer, photographer) -> bool:
    """
    Whether these two have ever transacted.

    Reviews use this (you may only review someone you booked) and chat will
    use it to decide who may open a conversation.
    """
    return Booking.objects.filter(buyer=buyer, photographer=photographer).exists()
