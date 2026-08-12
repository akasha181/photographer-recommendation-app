"""
Read-side availability computation — Module 7 support.

WHY AVAILABILITY IS DERIVED, NOT STORED
---------------------------------------
See `availability/models.py`: storing "free" days would mean roughly 73,000
rows a year for 200 photographers, almost all of them saying "yes". The rules
and the exceptions are stored; the answer is computed.

The computation costs a fixed **three queries for any window length** — the
weekly rules (at most 7 rows), the blackouts overlapping the window, and the
blocking bookings inside it. Everything after that is arithmetic in Python, so
a 90-day calendar costs the same as a single-day check.

DEFAULT IS AVAILABLE
--------------------
A photographer with no `AvailabilityRule` rows is treated as working every
day. The opposite default would make every newly-registered account invisible
to the calendar and unable to receive a first booking — a silent dead end. The
same choice is made in `profiles/filters.filter_available_on`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date as date_cls
from datetime import datetime, time, timedelta

from django.conf import settings
from django.utils import timezone

from apps.availability.models import AvailabilityRule, BlackoutDate, TimeSlot

#: How many days a calendar request may span. A buyer planning a wedding looks
#: months ahead; nobody needs three years, and an unbounded window is a cheap
#: way for a caller to make the server do pointless work.
DEFAULT_WINDOW_DAYS = 60
MAX_WINDOW_DAYS = 180


class UnavailableReason:
    """
    Machine-readable codes. The mobile app branches on these to decide whether
    to grey a date out, hide it, or show "fully booked — try another date", so
    they are part of the API contract.
    """

    PAST = "PAST"
    TOO_SOON = "TOO_SOON"
    WEEKLY_OFF = "WEEKLY_OFF"
    BLACKOUT = "BLACKOUT"
    FULLY_BOOKED = "FULLY_BOOKED"
    NOT_ACCEPTING = "NOT_ACCEPTING"
    SLOT_TAKEN = "SLOT_TAKEN"


@dataclass(slots=True)
class DayAvailability:
    """One cell of the booking calendar."""

    date: date_cls
    is_available: bool
    reason: str = ""
    message: str = ""
    booked_times: list[str] = field(default_factory=list)
    remaining_slots: int = 0
    start_time: time | None = None
    end_time: time | None = None


# ═══════════════════════════════════════════════════════════════════════════
# WINDOW HELPERS
# ═══════════════════════════════════════════════════════════════════════════
def earliest_bookable_date() -> date_cls:
    """
    The first date a buyer may request.

    `BOOKING_MIN_LEAD_HOURS` exists because a request for "in two hours" is
    almost never real, and a photographer who misses it looks unresponsive
    through no fault of their own.
    """
    lead = timedelta(hours=settings.BOOKING_MIN_LEAD_HOURS)
    return timezone.localtime(timezone.now() + lead).date()


def clamp_window(start: date_cls | None, days: int | None) -> tuple[date_cls, date_cls]:
    """Normalise a caller-supplied window to something sane and bounded."""
    start = start or timezone.localdate()
    span = days or DEFAULT_WINDOW_DAYS
    span = max(1, min(int(span), MAX_WINDOW_DAYS))
    return start, start + timedelta(days=span - 1)


# ═══════════════════════════════════════════════════════════════════════════
# THE CALENDAR
# ═══════════════════════════════════════════════════════════════════════════
def availability_calendar(
    photographer, start: date_cls | None = None, days: int | None = None
) -> list[DayAvailability]:
    """
    Availability for every date in the window, in order.

    Three queries regardless of how long the window is.
    """
    start, end = clamp_window(start, days)

    rules = _rules_by_weekday(photographer)
    blackouts = _blackouts_in(photographer, start, end)
    bookings = _blocking_bookings_in(photographer, start, end)
    floor = earliest_bookable_date()
    accepting = bool(getattr(photographer, "is_accepting_bookings", True))

    calendar = []
    cursor = start
    while cursor <= end:
        calendar.append(
            _day_status(
                cursor,
                rule=rules.get(cursor.weekday()),
                blackouts=blackouts,
                booked=bookings.get(cursor, []),
                floor=floor,
                accepting=accepting,
            )
        )
        cursor += timedelta(days=1)
    return calendar


def day_availability(photographer, date: date_cls) -> DayAvailability:
    """Single-date check — the same logic, scoped to one day."""
    return availability_calendar(photographer, start=date, days=1)[0]


def suggested_start_times(
    photographer, date: date_cls, duration_hours: int = 4
) -> list[str]:
    """
    Hourly start times the booking form can offer for a date.

    Derived from the weekday rule's working hours, trimmed so the shoot
    finishes before the photographer's day ends, with already-taken starts
    removed. Returns [] when the date is not bookable at all.
    """
    day = day_availability(photographer, date)
    if not day.is_available or day.start_time is None or day.end_time is None:
        return []

    explicit = _explicit_slots(photographer, date)
    if explicit is not None:
        return explicit

    taken = set(day.booked_times)
    latest = _shift_hours(day.end_time, -max(duration_hours, 1))

    times, cursor = [], day.start_time
    while cursor <= latest:
        label = cursor.strftime("%H:%M")
        if label not in taken:
            times.append(label)
        nxt = _shift_hours(cursor, 1)
        if nxt <= cursor:  # wrapped past midnight
            break
        cursor = nxt
    return times


def booked_times_on(photographer, date: date_cls) -> list[str]:
    """Start times already occupied by a PENDING or ACCEPTED booking."""
    return _blocking_bookings_in(photographer, date, date).get(date, [])


# ═══════════════════════════════════════════════════════════════════════════
# INTERNALS
# ═══════════════════════════════════════════════════════════════════════════
def _rules_by_weekday(photographer) -> dict[int, AvailabilityRule]:
    return {
        rule.weekday: rule
        for rule in AvailabilityRule.objects.filter(photographer=photographer)
    }


def _blackouts_in(photographer, start: date_cls, end: date_cls) -> list[BlackoutDate]:
    """Ranges that *overlap* the window — not ranges contained by it."""
    return list(
        BlackoutDate.objects.filter(
            photographer=photographer, start_date__lte=end, end_date__gte=start
        )
    )


def _blocking_bookings_in(
    photographer, start: date_cls, end: date_cls
) -> dict[date_cls, list[str]]:
    """{event_date: ["10:00", "15:00"]} for bookings that occupy a slot."""
    from apps.bookings.constants import BLOCKING_STATUSES
    from apps.bookings.models import Booking

    rows = Booking.objects.filter(
        photographer=photographer,
        event_date__gte=start,
        event_date__lte=end,
        status__in=BLOCKING_STATUSES,
    ).values_list("event_date", "start_time")

    grouped: dict[date_cls, list[str]] = {}
    for event_date, start_time in rows:
        grouped.setdefault(event_date, []).append(start_time.strftime("%H:%M"))
    return grouped


def _explicit_slots(photographer, date: date_cls) -> list[str] | None:
    """
    Free start times from explicit TimeSlot rows, or None when the photographer
    has not defined any for this date.

    Most photographers sell whole days and never create these; when they do
    exist they are authoritative and the derived hourly grid is not used.
    """
    slots = list(
        TimeSlot.objects.filter(photographer=photographer, date=date).order_by(
            "start_time"
        )
    )
    if not slots:
        return None
    return [s.start_time.strftime("%H:%M") for s in slots if not s.is_booked]


def _day_status(
    date: date_cls,
    *,
    rule: AvailabilityRule | None,
    blackouts: list[BlackoutDate],
    booked: list[str],
    floor: date_cls,
    accepting: bool,
) -> DayAvailability:
    """
    Decide one day.

    Order matters: the most absolute reasons are checked first so the message a
    buyer sees is the most useful one. "That date has passed" beats "fully
    booked" for a date in 2024.
    """
    hours = (rule.start_time, rule.end_time) if rule else (time(9, 0), time(18, 0))
    capacity = rule.max_bookings if rule else 1
    remaining = max(capacity - len(booked), 0)

    def unavailable(reason: str, message: str) -> DayAvailability:
        return DayAvailability(
            date=date,
            is_available=False,
            reason=reason,
            message=message,
            booked_times=sorted(booked),
            remaining_slots=0,
            start_time=hours[0],
            end_time=hours[1],
        )

    if date < timezone.localdate():
        return unavailable(UnavailableReason.PAST, "That date has already passed.")
    if not accepting:
        return unavailable(
            UnavailableReason.NOT_ACCEPTING,
            "This photographer is not accepting bookings at the moment.",
        )
    if date < floor:
        return unavailable(
            UnavailableReason.TOO_SOON,
            f"Bookings need at least {settings.BOOKING_MIN_LEAD_HOURS} hours' notice.",
        )
    if rule and not rule.is_available:
        return unavailable(
            UnavailableReason.WEEKLY_OFF,
            f"This photographer does not work on {date:%A}s.",
        )
    for blackout in blackouts:
        if blackout.covers(date) and blackout.is_full_day:
            return unavailable(
                UnavailableReason.BLACKOUT,
                blackout.reason or "The photographer is unavailable on this date.",
            )
    if remaining <= 0:
        return unavailable(UnavailableReason.FULLY_BOOKED, "Fully booked on this date.")

    return DayAvailability(
        date=date,
        is_available=True,
        booked_times=sorted(booked),
        remaining_slots=remaining,
        start_time=hours[0],
        end_time=hours[1],
    )


def _shift_hours(value: time, hours: int) -> time:
    """Add (or subtract) whole hours to a naive time, clamped to one day."""
    base = datetime.combine(date_cls(2000, 1, 1), value) + timedelta(hours=hours)
    if base.date() != date_cls(2000, 1, 1):
        return time(23, 59) if hours > 0 else time(0, 0)
    return base.time()
