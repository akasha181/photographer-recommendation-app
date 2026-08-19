"""
Module 5 — a photographer editing their own calendar.

The rule these tests exist to protect: narrowing the calendar changes what
buyers can request, and never touches what they have already been promised.
"""

from datetime import time, timedelta

import pytest
from django.utils import timezone

from apps.availability.models import AvailabilityRule, BlackoutDate
from apps.availability.services import add_blackout, remove_blackout, set_weekly_rules
from apps.core.exceptions import BusinessRuleViolation
from conftest import working_date

pytestmark = pytest.mark.django_db

URL = "/api/v1/availability/me/"


# ═══════════════════════════════════════════════════════════════════════════
# WEEKLY SCHEDULE
# ═══════════════════════════════════════════════════════════════════════════
def test_the_whole_week_saves_as_one_unit(photographer_client, photographer):
    rules = [
        {"weekday": day, "is_available": day < 5, "start_time": "08:00",
         "end_time": "20:00", "max_bookings": 2}
        for day in range(7)
    ]
    response = photographer_client.put(
        f"{URL}schedule/", {"rules": rules}, format="json"
    )

    assert response.status_code == 200
    saved = AvailabilityRule.objects.filter(photographer=photographer).order_by("weekday")
    assert [r.is_available for r in saved] == [True] * 5 + [False, False]
    assert saved[0].max_bookings == 2


def test_the_schedule_changes_what_buyers_can_book(
    photographer_client, photographer, buyer, service
):
    """The read side computes from these rows, so an edit is immediately live."""
    from apps.availability.selectors import day_availability

    date = working_date(10)
    assert day_availability(photographer, date).is_available is True

    photographer_client.put(
        f"{URL}schedule/",
        {"rules": [{"weekday": date.weekday(), "is_available": False}]},
        format="json",
    )

    day = day_availability(photographer, date)
    assert day.is_available is False
    assert day.reason == "WEEKLY_OFF"


def test_marking_a_day_off_does_not_cancel_an_existing_booking(
    photographer_client, photographer, booking
):
    """
    A commitment already made stays made. The calendar governs future
    requests, not the diary.
    """
    photographer_client.put(
        f"{URL}schedule/",
        {"rules": [{"weekday": booking.event_date.weekday(), "is_available": False}]},
        format="json",
    )
    booking.refresh_from_db()

    assert booking.status == "PENDING"
    assert booking.event_date is not None


def test_a_finish_before_the_start_is_refused(photographer):
    with pytest.raises(BusinessRuleViolation, match="after the start"):
        set_weekly_rules(
            photographer,
            [{"weekday": 0, "start_time": time(18, 0), "end_time": time(9, 0)}],
        )


def test_a_repeated_weekday_is_refused(photographer_client):
    response = photographer_client.put(
        f"{URL}schedule/",
        {"rules": [{"weekday": 1, "is_available": True}, {"weekday": 1, "is_available": False}]},
        format="json",
    )
    assert response.status_code == 400
    assert "only once" in response.json()["message"]


# ═══════════════════════════════════════════════════════════════════════════
# BLACKOUTS
# ═══════════════════════════════════════════════════════════════════════════
def test_blocking_a_range(photographer_client, photographer):
    start = working_date(20)
    response = photographer_client.post(
        f"{URL}blackouts/add/",
        {
            "start_date": start.isoformat(),
            "end_date": (start + timedelta(days=4)).isoformat(),
            "reason": "Away for a family wedding",
        },
        format="json",
    )

    assert response.status_code == 201
    body = response.json()["data"]
    assert body["blackout"]["days"] == 5
    assert body["conflicting_bookings"] == 0


def test_a_blackout_closes_the_dates_for_buyers(photographer_client, photographer):
    from apps.availability.selectors import day_availability

    start = working_date(20)
    photographer_client.post(
        f"{URL}blackouts/add/",
        {
            "start_date": start.isoformat(),
            "end_date": (start + timedelta(days=2)).isoformat(),
            "reason": "Shooting abroad",
        },
        format="json",
    )

    day = day_availability(photographer, start + timedelta(days=1))
    assert day.is_available is False
    assert day.reason == "BLACKOUT"
    assert day.message == "Shooting abroad"


def test_a_blackout_reports_clashes_but_cancels_nothing(photographer, booking):
    """
    Blocking the week you are getting married is exactly when you most need
    to. Refusing it because of one accepted shoot would leave the rest open.
    """
    blackout, clashes = add_blackout(
        photographer,
        start_date=booking.event_date - timedelta(days=1),
        end_date=booking.event_date + timedelta(days=1),
        reason="Personal leave",
    )
    booking.refresh_from_db()

    assert clashes == 1
    assert booking.status == "PENDING"
    assert BlackoutDate.objects.filter(pk=blackout.pk).exists()


def test_overlapping_blackouts_are_refused(photographer):
    start = working_date(20)
    add_blackout(photographer, start_date=start, end_date=start + timedelta(days=5))

    with pytest.raises(BusinessRuleViolation, match="overlaps a block"):
        add_blackout(
            photographer,
            start_date=start + timedelta(days=3),
            end_date=start + timedelta(days=8),
        )


def test_a_backwards_range_is_refused(photographer):
    start = working_date(20)
    with pytest.raises(BusinessRuleViolation, match="cannot be before"):
        add_blackout(
            photographer, start_date=start, end_date=start - timedelta(days=2)
        )


def test_an_absurdly_long_block_is_refused(photographer):
    start = working_date(20)
    with pytest.raises(BusinessRuleViolation, match="at a time"):
        add_blackout(
            photographer, start_date=start, end_date=start + timedelta(days=365)
        )


def test_a_part_day_block_needs_times(photographer):
    start = working_date(20)
    with pytest.raises(BusinessRuleViolation, match="start and finish time"):
        add_blackout(
            photographer, start_date=start, end_date=start, is_full_day=False
        )


def test_removing_a_block_reopens_the_dates(photographer_client, photographer):
    from apps.availability.selectors import day_availability

    start = working_date(20)
    blackout, _ = add_blackout(photographer, start_date=start, end_date=start)
    assert day_availability(photographer, start).is_available is False

    response = photographer_client.delete(f"{URL}blackouts/{blackout.pk}/")

    assert response.status_code == 204
    assert day_availability(photographer, start).is_available is True


def test_removing_someone_elses_block_is_refused(photographer, other_photographer):
    blackout, _ = add_blackout(
        other_photographer, start_date=working_date(20), end_date=working_date(20)
    )
    with pytest.raises(BusinessRuleViolation, match="not on your calendar"):
        remove_blackout(photographer, blackout.pk)


# ═══════════════════════════════════════════════════════════════════════════
# THE CALENDAR SCREEN
# ═══════════════════════════════════════════════════════════════════════════
def test_the_calendar_endpoint_returns_everything_at_once(
    photographer_client, photographer
):
    add_blackout(photographer, start_date=working_date(20), end_date=working_date(22))
    body = photographer_client.get(URL).json()["data"]

    assert body["is_accepting_bookings"] is True
    assert len(body["rules"]) == 7
    assert len(body["blackouts"]) == 1


def test_past_blocks_are_not_listed(photographer_client, photographer):
    """Only what still affects the calendar."""
    BlackoutDate.objects.create(
        photographer=photographer,
        start_date=timezone.localdate() - timedelta(days=30),
        end_date=timezone.localdate() - timedelta(days=25),
    )
    body = photographer_client.get(URL).json()["data"]
    assert body["blackouts"] == []


def test_a_buyer_has_no_calendar(buyer_client):
    assert buyer_client.get(URL).status_code == 403


def test_anonymous_is_refused(api_client):
    assert api_client.get(URL).status_code == 401
