"""
Module 15 — analytics rollups and the photographer dashboard.

The property that matters: a rollup must be IDEMPOTENT. It runs nightly, it
gets retried after failures, and it gets re-run by a backfill. If running it
twice doubled the numbers, every one of those would silently corrupt the
history it exists to preserve.
"""

from datetime import time, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.analytics.models import DailyPhotographerStat, PlatformStat, RevenueSnapshot
from apps.analytics.services import (
    backfill,
    rebuild_revenue_snapshots,
    rollup_day,
    rollup_platform_day,
)
from apps.bookings.services import accept_booking, complete_booking
from conftest import working_date

pytestmark = pytest.mark.django_db

URL = "/api/v1/analytics/me/"


def complete(booking, photographer, *, on=None):
    """Drive a booking to COMPLETED, optionally stamping when it finished."""
    accepted = accept_booking(booking, photographer.user)
    accepted.event_date = timezone.localdate() - timedelta(days=1)
    accepted.save(update_fields=["event_date"])
    done = complete_booking(accepted, photographer.user)
    if on is not None:
        done.completed_at = on
        done.save(update_fields=["completed_at"])
    return done


# ═══════════════════════════════════════════════════════════════════════════
# THE IDEMPOTENCE GUARANTEE
# ═══════════════════════════════════════════════════════════════════════════
def test_rerunning_a_rollup_corrects_rather_than_doubles(booking, photographer):
    """
    Nightly job, retry-after-failure and backfill all re-run the same day.
    Every one of them would corrupt history if this were additive.
    """
    today = timezone.localdate()
    rollup_day(today)
    first = DailyPhotographerStat.objects.get(photographer=photographer, date=today)

    rollup_day(today)
    rollup_day(today)
    again = DailyPhotographerStat.objects.get(photographer=photographer, date=today)

    assert DailyPhotographerStat.objects.filter(date=today).count() == 1
    assert again.bookings_created == first.bookings_created == 1


def test_a_day_with_no_activity_writes_no_row(photographer):
    """
    200 zero rows a day would be 73,000 rows a year saying nothing, and the
    dashboard treats a missing day as zero anyway.
    """
    quiet = timezone.localdate() - timedelta(days=200)
    rollup_day(quiet)
    assert DailyPhotographerStat.objects.filter(date=quiet).count() == 0


# ═══════════════════════════════════════════════════════════════════════════
# WHAT THE ROLLUP COUNTS
# ═══════════════════════════════════════════════════════════════════════════
def test_counts_a_booking_on_the_day_it_was_created(booking, photographer):
    today = timezone.localdate()
    rollup_day(today)
    row = DailyPhotographerStat.objects.get(photographer=photographer, date=today)

    assert row.bookings_created == 1
    assert row.bookings_completed == 0
    assert row.revenue == Decimal("0.00")


def test_revenue_lands_on_the_day_the_shoot_completed(booking, photographer):
    """
    A booking created in June and completed in August is AUGUST's revenue —
    that is the month the photographer was actually paid for it.
    """
    today = timezone.localdate()
    complete(booking, photographer)
    rollup_day(today)

    row = DailyPhotographerStat.objects.get(photographer=photographer, date=today)
    assert row.bookings_completed == 1
    assert row.revenue == Decimal("85000.00")
    assert row.commission_paid == Decimal("8500.00")


def test_rates_are_stored_not_left_to_the_client(booking, photographer, buyer):
    """A client that divides will show NaN the first time a denominator is 0."""
    from apps.recommendations.models import BuyerInteraction, BuyerInteractionType

    for _ in range(4):
        BuyerInteraction.objects.create(
            buyer=buyer,
            photographer=photographer,
            interaction_type=BuyerInteractionType.VIEW,
        )

    today = timezone.localdate()
    rollup_day(today)
    row = DailyPhotographerStat.objects.get(photographer=photographer, date=today)

    assert row.profile_views == 4
    assert row.conversion_rate == 0.25   # 1 booking / 4 views
    assert row.response_rate == 0.0      # nothing answered yet


def test_response_rate_after_answering(booking, photographer):
    today = timezone.localdate()
    accept_booking(booking, photographer.user)
    rollup_day(today)

    row = DailyPhotographerStat.objects.get(photographer=photographer, date=today)
    assert row.bookings_accepted == 1
    assert row.response_rate == 1.0


def test_zero_views_does_not_divide_by_zero(booking, photographer):
    today = timezone.localdate()
    rollup_day(today)
    row = DailyPhotographerStat.objects.get(photographer=photographer, date=today)
    assert row.conversion_rate == 0.0


def test_marketplace_earnings_are_counted(funded_buyer, photographer, product):
    from apps.marketplace.services import add_to_cart, checkout

    add_to_cart(funded_buyer, product)
    order = checkout(funded_buyer)

    rollup_day(timezone.localdate())
    row = DailyPhotographerStat.objects.get(
        photographer=photographer, date=timezone.localdate()
    )
    assert row.product_revenue == order.items.first().seller_earning


# ═══════════════════════════════════════════════════════════════════════════
# MONTHLY REVENUE
# ═══════════════════════════════════════════════════════════════════════════
def test_revenue_snapshot_is_built_from_completed_bookings(booking, photographer):
    complete(booking, photographer)
    rebuild_revenue_snapshots()

    now = timezone.now()
    snapshot = RevenueSnapshot.objects.get(
        photographer=photographer, year=now.year, month=now.month
    )
    assert snapshot.bookings_completed == 1
    assert snapshot.gross_revenue == Decimal("85000.00")
    assert snapshot.net_earnings == Decimal("76500.00")


def test_growth_is_computed_against_the_previous_month(
    buyer, other_buyer, service, photographer
):
    """The "+18%" badge needs no extra query at render time."""
    from apps.bookings.services import create_booking

    now = timezone.now()
    last_month = (now.replace(day=1) - timedelta(days=1)).replace(day=15)

    first = create_booking(
        buyer=buyer, service=service, event_date=working_date(7),
        start_time=time(9, 0), location_address="F-7", location_city="Islamabad",
    )
    complete(first, photographer, on=last_month)

    second = create_booking(
        buyer=other_buyer, service=service, event_date=working_date(14),
        start_time=time(11, 0), location_address="F-7", location_city="Islamabad",
    )
    complete(second, photographer, on=now)

    rebuild_revenue_snapshots()
    current = RevenueSnapshot.objects.get(
        photographer=photographer, year=now.year, month=now.month
    )
    # Same price both months, so the change is exactly zero — the point is
    # that it was computed at all rather than left at the default.
    assert current.growth_percent == 0.0
    assert RevenueSnapshot.objects.filter(photographer=photographer).count() == 2


def test_rebuilding_snapshots_is_idempotent(booking, photographer):
    complete(booking, photographer)
    rebuild_revenue_snapshots()
    rebuild_revenue_snapshots()

    assert RevenueSnapshot.objects.filter(photographer=photographer).count() == 1


# ═══════════════════════════════════════════════════════════════════════════
# PLATFORM
# ═══════════════════════════════════════════════════════════════════════════
def test_platform_rollup(booking, photographer):
    complete(booking, photographer)
    stat = rollup_platform_day(timezone.localdate())

    assert stat.bookings_created == 1
    assert stat.bookings_completed == 1
    assert stat.gross_booking_value == Decimal("85000.00")
    assert stat.cancellation_rate == 0.0
    assert PlatformStat.objects.count() == 1


def test_backfill_covers_a_window(booking, photographer):
    result = backfill(days=3)

    assert result["days"] == 3
    assert result["stat_rows"] >= 1


# ═══════════════════════════════════════════════════════════════════════════
# THE DASHBOARD
# ═══════════════════════════════════════════════════════════════════════════
def test_dashboard_serves_everything_in_one_response(photographer_client, booking):
    body = photographer_client.get(URL).json()["data"]

    assert set(body) == {
        "overview", "revenue_series", "daily_series", "funnel",
        "top_services", "category_split", "upcoming",
    }
    assert len(body["daily_series"]) == 30
    assert len(body["revenue_series"]) == 6


def test_headline_numbers_are_live_not_rolled_up(photographer_client, booking):
    """
    A booking made this second must show immediately. The rollup runs
    overnight; a dashboard stale in its headline is untrustworthy.
    """
    body = photographer_client.get(URL).json()["data"]["overview"]

    assert body["pending_requests"] == 1
    assert body["bookings_this_month"] == 1
    assert DailyPhotographerStat.objects.count() == 0  # no rollup has run


def test_series_gaps_are_filled_with_zeroes(photographer_client, photographer):
    """
    A missing month means "earned nothing", not "no data" — leaving it out
    would draw December next to March with no visible break.
    """
    body = photographer_client.get(URL).json()["data"]

    assert all(point["net_earnings"] == "0.00" for point in body["revenue_series"])
    assert all(point["bookings_created"] == 0 for point in body["daily_series"])


def test_window_parameters_are_clamped(photographer_client):
    body = photographer_client.get(f"{URL}?days=9999&months=9999").json()["data"]

    assert len(body["daily_series"]) == 90
    assert len(body["revenue_series"]) == 24


def test_a_nonsense_window_falls_back_to_the_default(photographer_client):
    body = photographer_client.get(f"{URL}?days=abc").json()["data"]
    assert len(body["daily_series"]) == 30


def test_top_services_rank_by_earnings(photographer_client, booking, photographer):
    complete(booking, photographer)
    rows = photographer_client.get(URL).json()["data"]["top_services"]

    assert rows[0]["title"] == "Full-Day Wedding Coverage"
    assert rows[0]["completed"] == 1
    assert rows[0]["revenue"] == "76500.00"


def test_category_split(photographer_client, booking, photographer):
    complete(booking, photographer)
    rows = photographer_client.get(URL).json()["data"]["category_split"]

    assert rows == [
        {"category": "Wedding", "bookings": 1, "revenue": "76500.00"}
    ]


def test_upcoming_shoots_appear(photographer_client, booking, photographer):
    accept_booking(booking, photographer.user)
    body = photographer_client.get(URL).json()["data"]

    assert len(body["upcoming"]) == 1
    assert body["overview"]["upcoming_shoots"] == 1


# ═══════════════════════════════════════════════════════════════════════════
# ACCESS
# ═══════════════════════════════════════════════════════════════════════════
def test_analytics_are_private_to_their_owner(
    photographer_client, other_photographer, booking
):
    """
    There is no "analytics for photographer X" route by design — engagement
    and revenue are competitively sensitive.
    """
    from rest_framework.test import APIClient

    other = APIClient()
    other.force_authenticate(user=other_photographer.user)
    body = other.get(URL).json()["data"]

    assert body["overview"]["pending_requests"] == 0
    assert body["overview"]["completed_shoots"] == 0


def test_a_buyer_has_no_analytics(buyer_client):
    assert buyer_client.get(URL).status_code == 403


def test_anonymous_is_refused(api_client):
    assert api_client.get(URL).status_code == 401


def test_revenue_and_funnel_endpoints(photographer_client, booking, photographer):
    complete(booking, photographer)
    rollup_day(timezone.localdate())
    rebuild_revenue_snapshots()

    revenue = photographer_client.get(f"{URL}revenue/?months=3").json()["data"]
    funnel = photographer_client.get(f"{URL}funnel/?days=7").json()["data"]

    assert len(revenue) == 3
    assert revenue[-1]["net_earnings"] == "76500.00"
    assert funnel["days"] == 7
    assert funnel["bookings"] == 1
