"""
Dashboard queries — Module 15.

TWO SPEEDS, ON PURPOSE
----------------------
The headline numbers ("bookings this month", "pending requests") are computed
LIVE from the bookings table. They must be correct the moment a request comes
in, they are indexed on (photographer, status), and they are a handful of rows.

The charts read the PRE-AGGREGATED rollup tables. A 12-month revenue series
over 52,000 bookings is a scan plus a GROUP BY; reading 12 tiny rows is not.

Mixing the two is the point: a dashboard that is stale in its headline is
untrustworthy, and one that recomputes its charts on every load is slow.
"""

from __future__ import annotations

from datetime import date as date_cls
from datetime import timedelta
from decimal import Decimal

from django.db.models import Avg, Count, Q, Sum
from django.utils import timezone

from apps.analytics.models import DailyPhotographerStat, RevenueSnapshot


# ═══════════════════════════════════════════════════════════════════════════
# HEADLINE — live
# ═══════════════════════════════════════════════════════════════════════════
def overview(photographer) -> dict:
    """The tiles at the top. One aggregate query over an indexed column."""
    from apps.bookings.constants import BookingStatus
    from apps.bookings.models import Booking

    today = timezone.localdate()
    month_start = today.replace(day=1)

    row = Booking.objects.filter(photographer=photographer).aggregate(
        pending=Count("id", filter=Q(status=BookingStatus.PENDING)),
        upcoming=Count(
            "id",
            filter=Q(status=BookingStatus.ACCEPTED, event_date__gte=today),
        ),
        completed_total=Count("id", filter=Q(status=BookingStatus.COMPLETED)),
        month_bookings=Count("id", filter=Q(created_at__date__gte=month_start)),
        month_earnings=Sum(
            "photographer_payout",
            filter=Q(
                status=BookingStatus.COMPLETED, completed_at__date__gte=month_start
            ),
        ),
        lifetime_earnings=Sum(
            "photographer_payout", filter=Q(status=BookingStatus.COMPLETED)
        ),
    )

    return {
        "pending_requests": row["pending"] or 0,
        "upcoming_shoots": row["upcoming"] or 0,
        "completed_shoots": row["completed_total"] or 0,
        "bookings_this_month": row["month_bookings"] or 0,
        "earnings_this_month": row["month_earnings"] or Decimal("0.00"),
        "lifetime_earnings": row["lifetime_earnings"] or Decimal("0.00"),
        "avg_rating": photographer.avg_rating,
        "reviews_count": photographer.reviews_count,
        "success_rate": photographer.success_rate,
        "response_time_hours": photographer.avg_response_time_hours,
        "profile_views": photographer.profile_views,
        "is_accepting_bookings": photographer.is_accepting_bookings,
    }


# ═══════════════════════════════════════════════════════════════════════════
# CHARTS — pre-aggregated
# ═══════════════════════════════════════════════════════════════════════════
def revenue_series(photographer, months: int = 6) -> list[dict]:
    """
    Monthly earnings, oldest first, with gaps filled.

    A missing month means "earned nothing", not "no data" — leaving it out
    would draw a bar chart where December sits next to March and the gap is
    invisible.
    """
    today = timezone.localdate()
    wanted: list[tuple[int, int]] = []
    year, month = today.year, today.month
    for _ in range(months):
        wanted.append((year, month))
        month -= 1
        if month == 0:
            year, month = year - 1, 12
    wanted.reverse()

    rows = {
        (row.year, row.month): row
        for row in RevenueSnapshot.objects.filter(
            photographer=photographer,
            year__gte=wanted[0][0],
        )
    }

    series = []
    for year, month in wanted:
        row = rows.get((year, month))
        series.append(
            {
                "year": year,
                "month": month,
                "label": date_cls(year, month, 1).strftime("%b"),
                "bookings_completed": row.bookings_completed if row else 0,
                "gross_revenue": row.gross_revenue if row else Decimal("0.00"),
                "net_earnings": row.net_earnings if row else Decimal("0.00"),
                "growth_percent": row.growth_percent if row else 0.0,
            }
        )
    return series


def daily_series(photographer, days: int = 30) -> list[dict]:
    """Per-day activity for the trend chart, gaps filled with zeroes."""
    today = timezone.localdate()
    start = today - timedelta(days=days - 1)

    rows = {
        row.date: row
        for row in DailyPhotographerStat.objects.filter(
            photographer=photographer, date__gte=start, date__lte=today
        )
    }

    series = []
    cursor = start
    while cursor <= today:
        row = rows.get(cursor)
        series.append(
            {
                "date": cursor,
                "profile_views": row.profile_views if row else 0,
                "bookings_created": row.bookings_created if row else 0,
                "bookings_completed": row.bookings_completed if row else 0,
                "revenue": row.revenue if row else Decimal("0.00"),
            }
        )
        cursor += timedelta(days=1)
    return series


def funnel(photographer, days: int = 30) -> dict:
    """
    Seen → clicked → enquired → booked.

    The useful thing about a funnel is where it narrows: a photographer with
    plenty of views and no bookings has a pricing or portfolio problem, while
    one with no views has a visibility problem. Those need opposite fixes.
    """
    start = timezone.localdate() - timedelta(days=days - 1)
    row = DailyPhotographerStat.objects.filter(
        photographer=photographer, date__gte=start
    ).aggregate(
        impressions=Sum("search_visibility"),
        views=Sum("profile_views"),
        clicks=Sum("clicks"),
        inquiries=Sum("inquiries"),
        bookings=Sum("bookings_created"),
        completed=Sum("bookings_completed"),
    )

    views = row["views"] or 0
    bookings = row["bookings"] or 0
    return {
        "days": days,
        "impressions": row["impressions"] or 0,
        "profile_views": views,
        "clicks": row["clicks"] or 0,
        "inquiries": row["inquiries"] or 0,
        "bookings": bookings,
        "completed": row["completed"] or 0,
        "view_to_booking_rate": round(bookings / views, 4) if views else 0.0,
    }


def top_services(photographer, limit: int = 5) -> list[dict]:
    """Which listings actually earn — computed live; a photographer has few."""
    from apps.bookings.constants import BookingStatus
    from apps.bookings.models import Booking

    rows = (
        Booking.objects.filter(photographer=photographer)
        .values("service_id", "service__title")
        .annotate(
            bookings=Count("id"),
            completed=Count("id", filter=Q(status=BookingStatus.COMPLETED)),
            revenue=Sum(
                "photographer_payout", filter=Q(status=BookingStatus.COMPLETED)
            ),
        )
        .order_by("-revenue", "-bookings")[:limit]
    )
    return [
        {
            "service_id": row["service_id"],
            "title": row["service__title"],
            "bookings": row["bookings"],
            "completed": row["completed"],
            "revenue": row["revenue"] or Decimal("0.00"),
        }
        for row in rows
    ]


def category_split(photographer) -> list[dict]:
    """Where the work comes from — one row per event type."""
    from apps.bookings.constants import BookingStatus
    from apps.bookings.models import Booking

    rows = (
        Booking.objects.filter(
            photographer=photographer, status=BookingStatus.COMPLETED
        )
        .values("category__name")
        .annotate(bookings=Count("id"), revenue=Sum("photographer_payout"))
        .order_by("-bookings")
    )
    return [
        {
            "category": row["category__name"] or "Other",
            "bookings": row["bookings"],
            "revenue": row["revenue"] or Decimal("0.00"),
        }
        for row in rows
    ]


def dashboard(photographer, *, days: int = 30, months: int = 6) -> dict:
    """Everything the Dashboard screen renders, in one response."""
    from apps.bookings.selectors import upcoming_bookings

    return {
        "overview": overview(photographer),
        "revenue_series": revenue_series(photographer, months=months),
        "daily_series": daily_series(photographer, days=days),
        "funnel": funnel(photographer, days=days),
        "top_services": top_services(photographer),
        "category_split": category_split(photographer),
        "upcoming": list(upcoming_bookings(photographer.user, limit=3)),
    }
