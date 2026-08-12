"""
Availability computation.

The rule these tests pin down: a date is bookable unless something explicitly
says otherwise, and the *reason* it is not bookable is the most useful one
available — a buyer looking at a greyed-out date needs to know whether to try
a different time or a different photographer.
"""

from datetime import time, timedelta

import pytest
from django.utils import timezone

from apps.availability import selectors
from apps.availability.models import AvailabilityRule, BlackoutDate, TimeSlot
from apps.availability.selectors import UnavailableReason
from conftest import working_date

pytestmark = pytest.mark.django_db


# ═══════════════════════════════════════════════════════════════════════════
# THE WINDOW
# ═══════════════════════════════════════════════════════════════════════════
def test_calendar_defaults_to_the_standard_window(photographer):
    calendar = selectors.availability_calendar(photographer)
    assert len(calendar) == selectors.DEFAULT_WINDOW_DAYS
    assert calendar[0].date == timezone.localdate()


def test_calendar_window_is_capped(photographer):
    """An unbounded window is a cheap way to make the server do pointless work."""
    calendar = selectors.availability_calendar(photographer, days=10_000)
    assert len(calendar) == selectors.MAX_WINDOW_DAYS


def test_calendar_costs_the_same_for_any_window(photographer, django_assert_num_queries):
    """Three queries — rules, blackouts, bookings — regardless of length."""
    with django_assert_num_queries(3):
        selectors.availability_calendar(photographer, days=180)


# ═══════════════════════════════════════════════════════════════════════════
# REASONS, IN PRIORITY ORDER
# ═══════════════════════════════════════════════════════════════════════════
def test_past_dates_say_so(photographer):
    yesterday = timezone.localdate() - timedelta(days=1)
    day = selectors.day_availability(photographer, yesterday)

    assert day.is_available is False
    assert day.reason == UnavailableReason.PAST


def test_today_is_inside_the_minimum_lead_time(photographer):
    day = selectors.day_availability(photographer, timezone.localdate())

    assert day.is_available is False
    assert day.reason == UnavailableReason.TOO_SOON


def test_a_paused_photographer_beats_every_other_reason(photographer):
    photographer.is_accepting_bookings = False
    photographer.save(update_fields=["is_accepting_bookings"])

    day = selectors.day_availability(photographer, working_date(10))
    assert day.reason == UnavailableReason.NOT_ACCEPTING


def test_the_weekly_rule_marks_days_off(photographer):
    sunday = working_date(7)
    while sunday.weekday() != 6:
        sunday += timedelta(days=1)

    day = selectors.day_availability(photographer, sunday)
    assert day.reason == UnavailableReason.WEEKLY_OFF
    assert "Sunday" in day.message


def test_a_blackout_beats_the_weekly_rule(photographer):
    date = working_date(10)
    BlackoutDate.objects.create(
        photographer=photographer,
        start_date=date,
        end_date=date + timedelta(days=3),
        reason="Shooting abroad",
    )

    day = selectors.day_availability(photographer, date + timedelta(days=2))
    assert day.reason == UnavailableReason.BLACKOUT
    assert day.message == "Shooting abroad"


def test_a_partial_day_blackout_does_not_close_the_date(photographer):
    """Half-day blackouts narrow the day; they do not remove it."""
    date = working_date(10)
    BlackoutDate.objects.create(
        photographer=photographer,
        start_date=date,
        end_date=date,
        is_full_day=False,
        start_time=time(9, 0),
        end_time=time(12, 0),
    )

    assert selectors.day_availability(photographer, date).is_available is True


def test_a_booking_consumes_the_days_capacity(photographer, booking):
    day = selectors.day_availability(photographer, booking.event_date)

    assert day.is_available is False
    assert day.reason == UnavailableReason.FULLY_BOOKED
    assert day.booked_times == ["14:00"]


def test_capacity_above_one_keeps_the_day_open(photographer, booking):
    AvailabilityRule.objects.filter(
        photographer=photographer, weekday=booking.event_date.weekday()
    ).update(max_bookings=2)

    day = selectors.day_availability(photographer, booking.event_date)
    assert day.is_available is True
    assert day.remaining_slots == 1


def test_a_photographer_with_no_rules_is_available(photographer):
    """
    The default must be 'available'. The opposite would make every newly
    registered account invisible and unable to take a first booking.
    """
    AvailabilityRule.objects.filter(photographer=photographer).delete()
    day = selectors.day_availability(photographer, working_date(10))

    assert day.is_available is True
    assert day.start_time == time(9, 0)


# ═══════════════════════════════════════════════════════════════════════════
# START TIMES
# ═══════════════════════════════════════════════════════════════════════════
def test_start_times_stop_early_enough_to_finish(photographer):
    """A 4-hour shoot cannot start at 17:00 on a day that ends at 18:00."""
    times = selectors.suggested_start_times(photographer, working_date(10), 4)

    assert times[0] == "09:00"
    assert times[-1] == "14:00"


def test_a_longer_shoot_offers_fewer_starts(photographer):
    short = selectors.suggested_start_times(photographer, working_date(10), 2)
    long = selectors.suggested_start_times(photographer, working_date(10), 8)

    assert len(short) > len(long)


def test_taken_times_are_removed(photographer, booking):
    AvailabilityRule.objects.filter(
        photographer=photographer, weekday=booking.event_date.weekday()
    ).update(max_bookings=2)

    times = selectors.suggested_start_times(photographer, booking.event_date, 2)
    assert "14:00" not in times


def test_an_unavailable_date_offers_nothing(photographer):
    assert selectors.suggested_start_times(photographer, timezone.localdate()) == []


def test_explicit_slots_override_the_hourly_grid(photographer):
    """
    A studio selling "10:00-13:00" and "14:00-17:00" gets exactly those two,
    not a nine-entry hourly list.
    """
    date = working_date(10)
    TimeSlot.objects.create(
        photographer=photographer, date=date, start_time=time(10, 0), end_time=time(13, 0)
    )
    TimeSlot.objects.create(
        photographer=photographer, date=date, start_time=time(14, 0), end_time=time(17, 0)
    )

    assert selectors.suggested_start_times(photographer, date) == ["10:00", "14:00"]


def test_a_booked_explicit_slot_is_not_offered(photographer):
    date = working_date(10)
    TimeSlot.objects.create(
        photographer=photographer, date=date, start_time=time(10, 0), end_time=time(13, 0)
    )
    TimeSlot.objects.create(
        photographer=photographer, date=date, start_time=time(14, 0),
        end_time=time(17, 0), is_booked=True,
    )

    assert selectors.suggested_start_times(photographer, date) == ["10:00"]


def test_earliest_bookable_date_respects_the_lead_time(settings):
    settings.BOOKING_MIN_LEAD_HOURS = 48
    assert selectors.earliest_bookable_date() >= timezone.localdate() + timedelta(days=1)
