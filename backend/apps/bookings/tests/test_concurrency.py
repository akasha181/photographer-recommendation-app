"""
The double-booking guard, tested for real.

TWO INDEPENDENT DEFENCES, TESTED SEPARATELY
-------------------------------------------
1. The application lock — `select_for_update()` on the photographer row in
   `create_booking`. Two buyers racing serialize behind it, so the loser gets
   a sentence they can act on rather than a database error.

2. The database constraint — `uniq_active_booking_slot`. MySQL has no partial
   indexes, so this is a generated column plus a plain unique index (see
   migration 0003). It exists because an application guard is only as good as
   the code paths that remember to call it.

These need real threads and real connections, so they run under
`transaction=True` and are marked slow.
"""

import threading
from datetime import time, timedelta
from decimal import Decimal

import pytest
from django.db import IntegrityError, connection, transaction
from django.utils import timezone

from apps.bookings.constants import BookingStatus
from apps.bookings.models import Booking
from apps.bookings.services import create_booking
from apps.core.exceptions import ConflictError

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.slow]


def test_two_buyers_racing_for_one_slot(
    buyer, other_buyer, service, photographer, event_date
):
    """
    Exactly one booking exists afterwards, and the loser gets a clean error.

    Both threads are held at a barrier so they enter `create_booking` at the
    same moment — without that they would simply run in sequence and prove
    nothing.

    Daily capacity is raised to two so the collision happens at the exact-slot
    guard. At the default capacity of one the day limit would refuse the
    second request first, and the test would pass without ever exercising the
    race it exists to cover.
    """
    from apps.availability.models import AvailabilityRule

    AvailabilityRule.objects.filter(
        photographer=photographer, weekday=event_date.weekday()
    ).update(max_bookings=2)

    barrier = threading.Barrier(2, timeout=15)
    results: dict[int, tuple[str, object]] = {}

    def attempt(index: int, user):
        try:
            barrier.wait()
            booking = create_booking(
                buyer=user,
                service=service,
                event_date=event_date,
                start_time=time(14, 0),
                location_address="F-7 Markaz",
                location_city="Islamabad",
            )
            results[index] = ("created", booking.pk)
        except Exception as exc:  # noqa: BLE001 — the point is to record it
            results[index] = ("refused", exc)
        finally:
            connection.close()

    threads = [
        threading.Thread(target=attempt, args=(0, buyer)),
        threading.Thread(target=attempt, args=(1, other_buyer)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    outcomes = [results[i][0] for i in sorted(results)]
    assert sorted(outcomes) == ["created", "refused"], results

    loser = next(value for status, value in results.values() if status == "refused")
    assert isinstance(loser, ConflictError), loser

    assert Booking.objects.filter(
        photographer=service.photographer,
        event_date=event_date,
        start_time=time(14, 0),
        status__in=[BookingStatus.PENDING, BookingStatus.ACCEPTED],
    ).count() == 1


def test_the_database_itself_refuses_a_duplicate_slot(
    buyer, other_buyer, service, photographer, event_date
):
    """
    Bypass the service entirely and insert straight into the table.

    This is the test that would have caught the original bug: before migration
    0003, MySQL accepted this row silently and the platform double-booked.
    """
    first = create_booking(
        buyer=buyer,
        service=service,
        event_date=event_date,
        start_time=time(14, 0),
        location_address="F-7 Markaz",
        location_city="Islamabad",
    )

    with pytest.raises(IntegrityError, match="uniq_active_booking_slot"):
        with transaction.atomic():
            Booking.objects.create(
                buyer=other_buyer,
                photographer=photographer,
                service=service,
                category=service.category,
                event_date=first.event_date,
                start_time=first.start_time,
                duration_hours=4,
                location_address="Somewhere else",
                location_city="Islamabad",
                unit_price=Decimal("1000.00"),
                total_price=Decimal("1000.00"),
                status=BookingStatus.PENDING,
                expires_at=timezone.now() + timedelta(hours=48),
            )


def test_the_constraint_ignores_dead_bookings(
    buyer, other_buyer, service, photographer, event_date
):
    """
    A cancelled booking must not keep its slot locked forever.

    This is what the generated column's CASE expression buys: the key is NULL
    for anything that is not PENDING or ACCEPTED, and MySQL unique indexes
    ignore NULL.
    """
    first = create_booking(
        buyer=buyer,
        service=service,
        event_date=event_date,
        start_time=time(14, 0),
        location_address="F-7 Markaz",
        location_city="Islamabad",
    )
    first.status = BookingStatus.CANCELLED
    first.save(update_fields=["status"])

    second = create_booking(
        buyer=other_buyer,
        service=service,
        event_date=event_date,
        start_time=time(14, 0),
        location_address="F-7 Markaz",
        location_city="Islamabad",
    )

    assert second.pk != first.pk
    assert second.status == BookingStatus.PENDING
