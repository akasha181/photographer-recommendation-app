"""
Availability writes — a photographer editing their own calendar.

WHAT THIS MODULE MUST NOT BREAK
-------------------------------
The read side (`selectors.py`) computes bookability from these rows, and
`bookings/services.create_booking` calls it under a row lock. So every write
here changes what buyers can book — which means two rules:

1. NARROWING THE CALENDAR NEVER CANCELS ANYTHING. Marking Sunday as a day off,
   or blacking out a week, does not touch bookings that already exist. A
   photographer who has committed to a shoot has committed to it; the calendar
   is about future requests. The endpoints report the clash instead so they
   can cancel deliberately, with a reason the buyer sees.

2. A BLACKOUT IS ALLOWED TO OVERLAP AN EXISTING BOOKING. Blocking the week you
   are getting married is exactly when you most need to, and refusing it
   because of one accepted shoot would leave the rest of the week open.
"""

import logging
from datetime import date as date_cls

from django.db import transaction

from apps.availability.models import AvailabilityRule, BlackoutDate, Weekday
from apps.core.exceptions import BusinessRuleViolation

logger = logging.getLogger("snapsphere")

MAX_BLACKOUT_DAYS = 180


@transaction.atomic
def set_weekly_rules(photographer, rules: list[dict]) -> list[AvailabilityRule]:
    """
    Replace the whole weekly pattern in one call.

    Sent as a set rather than seven separate PATCHes because the screen is one
    form with seven rows: saving them individually means a half-applied week
    if the connection drops in the middle, and the calendar would then be a
    mixture of the old pattern and the new one.
    """
    by_weekday = {rule["weekday"]: rule for rule in rules}
    unknown = set(by_weekday) - set(Weekday.values)
    if unknown:
        raise BusinessRuleViolation(f"Not a valid weekday: {sorted(unknown)}.")

    for weekday, data in by_weekday.items():
        start, end = data.get("start_time"), data.get("end_time")
        if start and end and start >= end:
            raise BusinessRuleViolation(
                f"{Weekday(weekday).label}: the finish time must be after the start."
            )

        AvailabilityRule.objects.update_or_create(
            photographer=photographer,
            weekday=weekday,
            defaults={
                "is_available": data.get("is_available", True),
                "start_time": start or "09:00",
                "end_time": end or "18:00",
                "max_bookings": max(1, int(data.get("max_bookings", 1))),
            },
        )

    logger.info(
        "Weekly availability updated", extra={"photographer_id": photographer.pk}
    )
    return list(
        AvailabilityRule.objects.filter(photographer=photographer).order_by("weekday")
    )


@transaction.atomic
def add_blackout(
    photographer,
    *,
    start_date: date_cls,
    end_date: date_cls,
    reason: str = "",
    is_full_day: bool = True,
    start_time=None,
    end_time=None,
) -> tuple[BlackoutDate, int]:
    """
    Block a date range.

    Returns the row plus **how many existing bookings fall inside it**, so the
    app can say "3 confirmed shoots are in this range" rather than silently
    creating a calendar that disagrees with the diary. Nothing is cancelled —
    see the module docstring.
    """
    if end_date < start_date:
        raise BusinessRuleViolation("The end date cannot be before the start date.")
    if (end_date - start_date).days > MAX_BLACKOUT_DAYS:
        raise BusinessRuleViolation(
            f"Block up to {MAX_BLACKOUT_DAYS} days at a time. "
            f"Turn off the weekdays you never work instead of blocking months."
        )
    if not is_full_day and (not start_time or not end_time):
        raise BusinessRuleViolation("A part-day block needs a start and finish time.")

    overlapping = BlackoutDate.objects.filter(
        photographer=photographer, start_date__lte=end_date, end_date__gte=start_date
    ).first()
    if overlapping is not None:
        raise BusinessRuleViolation(
            f"That overlaps a block you already have "
            f"({overlapping.start_date:%d %b} – {overlapping.end_date:%d %b})."
        )

    blackout = BlackoutDate.objects.create(
        photographer=photographer,
        start_date=start_date,
        end_date=end_date,
        reason=reason.strip()[:200],
        is_full_day=is_full_day,
        start_time=start_time,
        end_time=end_time,
    )
    return blackout, _bookings_in_range(photographer, start_date, end_date)


@transaction.atomic
def remove_blackout(photographer, blackout_id: int) -> None:
    deleted, _ = BlackoutDate.objects.filter(
        photographer=photographer, pk=blackout_id
    ).delete()
    if not deleted:
        raise BusinessRuleViolation("That blocked period is not on your calendar.")


def _bookings_in_range(photographer, start: date_cls, end: date_cls) -> int:
    from apps.bookings.constants import BLOCKING_STATUSES
    from apps.bookings.models import Booking

    return Booking.objects.filter(
        photographer=photographer,
        event_date__gte=start,
        event_date__lte=end,
        status__in=BLOCKING_STATUSES,
    ).count()
