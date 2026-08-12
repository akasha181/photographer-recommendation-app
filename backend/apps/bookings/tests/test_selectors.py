"""
Read-side scoping.

The property worth testing here is negative: no selector may ever return a
booking belonging to someone else, whichever entry point is used.
"""

from datetime import time, timedelta

import pytest
from django.utils import timezone

from apps.bookings import selectors
from apps.bookings.constants import BookingStatus
from apps.bookings.services import accept_booking, cancel_booking, create_booking
from conftest import working_date

pytestmark = pytest.mark.django_db


@pytest.fixture
def second_booking(other_buyer, service):
    """A booking belonging to a different buyer, same photographer."""
    return create_booking(
        buyer=other_buyer,
        service=service,
        event_date=working_date(20),
        start_time=time(10, 0),
        location_address="Gulberg, Lahore",
        location_city="Lahore",
    )


def test_buyer_sees_only_their_own(booking, second_booking, buyer):
    rows = selectors.get_buyer_bookings(buyer)
    assert [row.pk for row in rows] == [booking.pk]


def test_photographer_sees_both_sides_of_their_calendar(
    booking, second_booking, photographer
):
    rows = selectors.get_photographer_bookings(photographer.user)
    assert {row.pk for row in rows} == {booking.pk, second_booking.pk}


def test_role_decides_which_side_the_shared_entry_point_returns(
    booking, second_booking, buyer, photographer
):
    assert {r.pk for r in selectors.get_user_bookings(buyer)} == {booking.pk}
    assert {r.pk for r in selectors.get_user_bookings(photographer.user)} == {
        booking.pk,
        second_booking.pk,
    }


def test_group_filter(booking, buyer, photographer):
    assert selectors.get_user_bookings(buyer, group="pending").count() == 1
    assert selectors.get_user_bookings(buyer, group="upcoming").count() == 0

    accept_booking(booking, photographer.user)
    assert selectors.get_user_bookings(buyer, group="upcoming").count() == 1


def test_exact_status_filter(booking, buyer):
    assert selectors.get_user_bookings(buyer, status="pending").count() == 1
    assert selectors.get_user_bookings(buyer, status="COMPLETED").count() == 0


def test_an_unknown_group_does_not_look_like_an_empty_account(booking, buyer):
    """
    A typo in a query string must not render as "you have no bookings" — that
    is indistinguishable from a real empty state and hides the bug.
    """
    assert selectors.get_user_bookings(buyer, group="nonsense").count() == 1


def test_detail_is_scoped_to_the_caller(booking, buyer, other_buyer, photographer):
    assert selectors.get_booking_for_user(buyer, booking.pk) is not None
    assert selectors.get_booking_for_user(photographer.user, booking.pk) is not None
    assert selectors.get_booking_for_user(other_buyer, booking.pk) is None


def test_lookup_by_uuid(booking, buyer, other_buyer):
    assert selectors.get_booking_by_uuid(buyer, booking.uuid).pk == booking.pk
    assert selectors.get_booking_by_uuid(other_buyer, booking.uuid) is None


def test_counts_track_status(booking, buyer, photographer):
    assert selectors.booking_counts(buyer) == {
        "pending": 1, "upcoming": 0, "completed": 0, "cancelled": 0, "total": 1,
    }

    accept_booking(booking, photographer.user)
    assert selectors.booking_counts(buyer)["upcoming"] == 1

    cancel_booking(booking, buyer)
    counts = selectors.booking_counts(buyer)
    assert counts["cancelled"] == 1
    assert counts["upcoming"] == 0


def test_upcoming_excludes_unconfirmed_and_past_shoots(booking, buyer, photographer):
    assert list(selectors.upcoming_bookings(buyer)) == []

    accepted = accept_booking(booking, photographer.user)
    assert [b.pk for b in selectors.upcoming_bookings(buyer)] == [booking.pk]

    accepted.event_date = timezone.localdate() - timedelta(days=1)
    accepted.save(update_fields=["event_date"])
    assert list(selectors.upcoming_bookings(buyer)) == []


def test_pending_requests_count(booking, second_booking, photographer):
    assert selectors.pending_requests_count(photographer.user) == 2

    accept_booking(booking, photographer.user)
    assert selectors.pending_requests_count(photographer.user) == 1


def test_has_booking_between(booking, buyer, other_buyer, photographer):
    assert selectors.has_booking_between(buyer, photographer) is True
    assert selectors.has_booking_between(other_buyer, photographer) is False


def test_list_queries_stay_flat(booking, second_booking, photographer, django_assert_max_num_queries):
    """
    `.with_details()` is what keeps a 20-row page at a constant query count.
    Without it each row costs four extra joins.
    """
    with django_assert_max_num_queries(2):
        list(selectors.get_photographer_bookings(photographer.user))


def test_status_group_map_covers_every_status():
    """A status missing from every tab would be invisible in the app."""
    grouped = {s for statuses in selectors.STATUS_GROUPS.values() for s in statuses}
    assert grouped == set(BookingStatus.values)
