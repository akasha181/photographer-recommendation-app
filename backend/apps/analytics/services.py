"""
Analytics rollups — Module 15.

WHY A ROLLUP AND NOT A LIVE QUERY
---------------------------------
"Revenue per month for the last 12 months" over 52,000 bookings is a scan plus
a GROUP BY. Run it on every dashboard load and the dashboard becomes the
slowest screen in the product — and it gets slower as the business succeeds.

These functions write one small row per photographer per day. The dashboard
then reads 30 or 365 pre-computed rows, and the cost is bounded and constant
no matter how large the fact tables get.

IDEMPOTENT BY DESIGN
--------------------
Every rollup is an `update_or_create` keyed on (photographer, date). Re-running
a day corrects it rather than double-counting, which is what makes a backfill
safe to run twice and a failed nightly job safe to simply run again.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date as date_cls
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Avg, Count, Q, Sum
from django.utils import timezone

from apps.analytics.models import DailyPhotographerStat, PlatformStat, RevenueSnapshot

logger = logging.getLogger("snapsphere")


# ═══════════════════════════════════════════════════════════════════════════
# DAILY ROLLUP
# ═══════════════════════════════════════════════════════════════════════════
@transaction.atomic
def rollup_day(target: date_cls) -> int:
    """
    Aggregate one calendar day for every photographer who had activity.

    Photographers with no activity get no row — writing 200 zero rows a day
    would be 73,000 rows a year saying nothing, and the dashboard treats a
    missing day as zero anyway.
    """
    from apps.bookings.models import Booking
    from apps.marketplace.models import OrderItem, OrderStatus
    from apps.recommendations.models import BuyerInteraction
    from apps.reviews.models import Review

    bookings = _bookings_by_photographer(Booking, target)
    interactions = _interactions_by_photographer(BuyerInteraction, target)
    products = _product_earnings_by_seller(OrderItem, OrderStatus, target)
    reviews = _reviews_by_photographer(Review, target)

    touched = set(bookings) | set(interactions) | set(products) | set(reviews)
    for photographer_id in touched:
        booking = bookings.get(photographer_id, {})
        funnel = interactions.get(photographer_id, {})
        review = reviews.get(photographer_id, {})

        views = funnel.get("profile_views", 0)
        created = booking.get("created", 0)
        received = booking.get("created", 0)
        responded = booking.get("accepted", 0) + booking.get("rejected", 0)

        DailyPhotographerStat.objects.update_or_create(
            photographer_id=photographer_id,
            date=target,
            defaults={
                "search_visibility": funnel.get("search_visibility", 0),
                "profile_views": views,
                "clicks": funnel.get("clicks", 0),
                "portfolio_interactions": funnel.get("portfolio_interactions", 0),
                "inquiries": funnel.get("inquiries", 0),
                "bookings_created": created,
                "bookings_accepted": booking.get("accepted", 0),
                "bookings_completed": booking.get("completed", 0),
                "bookings_cancelled": booking.get("cancelled", 0),
                "bookings_rejected": booking.get("rejected", 0),
                "revenue": booking.get("revenue", Decimal("0.00")),
                "commission_paid": booking.get("commission", Decimal("0.00")),
                "product_revenue": products.get(photographer_id, Decimal("0.00")),
                # Stored rather than divided on the client: a chart that has to
                # guard against dividing by zero in three places is a chart
                # that will show NaN in one of them.
                "conversion_rate": round(created / views, 4) if views else 0.0,
                "response_rate": round(responded / received, 4) if received else 0.0,
                "reviews_received": review.get("count", 0),
                "avg_rating_snapshot": review.get("avg", Decimal("0.00")),
            },
        )

    logger.info("Rolled up %s photographers for %s", len(touched), target)
    return len(touched)


def _bookings_by_photographer(Booking, target: date_cls) -> dict[int, dict]:
    """
    One query for the whole day.

    Each counter keys off the timestamp of the event it counts, not off
    `created_at` — a booking created in June and completed in August is
    August's revenue, which is the month the photographer was actually paid
    for it.
    """
    rows = (
        Booking.objects.filter(
            Q(created_at__date=target)
            | Q(accepted_at__date=target)
            | Q(completed_at__date=target)
            | Q(cancelled_at__date=target)
            | Q(rejected_at__date=target)
        )
        .values("photographer_id")
        .annotate(
            created=Count("id", filter=Q(created_at__date=target)),
            accepted=Count("id", filter=Q(accepted_at__date=target)),
            completed=Count("id", filter=Q(completed_at__date=target)),
            cancelled=Count("id", filter=Q(cancelled_at__date=target)),
            rejected=Count("id", filter=Q(rejected_at__date=target)),
            revenue=Sum("total_price", filter=Q(completed_at__date=target)),
            commission=Sum("commission_amount", filter=Q(completed_at__date=target)),
        )
    )
    return {
        row["photographer_id"]: {
            "created": row["created"],
            "accepted": row["accepted"],
            "completed": row["completed"],
            "cancelled": row["cancelled"],
            "rejected": row["rejected"],
            "revenue": row["revenue"] or Decimal("0.00"),
            "commission": row["commission"] or Decimal("0.00"),
        }
        for row in rows
    }


def _interactions_by_photographer(BuyerInteraction, target: date_cls) -> dict[int, dict]:
    """The discovery funnel, from real implicit-feedback rows."""
    rows = (
        BuyerInteraction.objects.filter(created_at__date=target)
        .values("photographer_id")
        .annotate(
            profile_views=Count("id", filter=Q(interaction_type="VIEW")),
            clicks=Count("id", filter=Q(interaction_type="CLICK")),
            portfolio_interactions=Count("id", filter=Q(interaction_type="PORTFOLIO")),
            inquiries=Count("id", filter=Q(interaction_type="INQUIRY")),
            search_visibility=Count("id", filter=Q(interaction_type="SEARCH")),
        )
    )
    return {row.pop("photographer_id"): row for row in rows}


def _product_earnings_by_seller(OrderItem, OrderStatus, target: date_cls) -> dict[int, Decimal]:
    rows = (
        OrderItem.objects.filter(
            order__status=OrderStatus.PAID, order__paid_at__date=target
        )
        .values("seller_id")
        .annotate(total=Sum("seller_earning"))
    )
    return {row["seller_id"]: row["total"] or Decimal("0.00") for row in rows}


def _reviews_by_photographer(Review, target: date_cls) -> dict[int, dict]:
    rows = (
        Review.objects.filter(created_at__date=target)
        .values("photographer_id")
        .annotate(count=Count("id"), avg=Avg("rating"))
    )
    return {
        row["photographer_id"]: {
            "count": row["count"],
            "avg": Decimal(f"{row['avg'] or 0:.2f}"),
        }
        for row in rows
    }


def backfill(days: int = 365, *, until: date_cls | None = None) -> dict:
    """
    Rebuild the rollup for a window, oldest day first.

    Used after a data import or a fix to the aggregation — and to give a fresh
    install charts that are not empty. Idempotent, so running it twice over the
    same range is harmless.
    """
    until = until or timezone.localdate()
    start = until - timedelta(days=days - 1)

    total_rows = 0
    cursor = start
    while cursor <= until:
        total_rows += rollup_day(cursor)
        cursor += timedelta(days=1)

    snapshots = rebuild_revenue_snapshots()
    return {"days": days, "stat_rows": total_rows, "revenue_snapshots": snapshots}


# ═══════════════════════════════════════════════════════════════════════════
# MONTHLY REVENUE
# ═══════════════════════════════════════════════════════════════════════════
@transaction.atomic
def rebuild_revenue_snapshots(photographer=None) -> int:
    """
    Recompute month-grained earnings from completed bookings.

    Separate from the daily table because the earnings screen and payout
    reports are month-grained, and summing 30 daily rows per month per
    photographer on every load is waste that compounds.
    """
    from apps.bookings.constants import BookingStatus
    from apps.bookings.models import Booking

    qs = Booking.objects.filter(
        status=BookingStatus.COMPLETED, completed_at__isnull=False
    )
    if photographer is not None:
        qs = qs.filter(photographer=photographer)

    rows = (
        qs.values("photographer_id", "completed_at__year", "completed_at__month")
        .annotate(
            completed=Count("id"),
            gross=Sum("total_price"),
            commission=Sum("commission_amount"),
            net=Sum("photographer_payout"),
        )
        .order_by("photographer_id", "completed_at__year", "completed_at__month")
    )

    # Growth needs the previous month, so the rows are grouped per photographer
    # and walked in order rather than written one at a time.
    by_photographer: dict[int, list[dict]] = defaultdict(list)
    for row in rows:
        by_photographer[row["photographer_id"]].append(row)

    written = 0
    for photographer_id, months in by_photographer.items():
        previous_net = None
        for row in months:
            net = row["net"] or Decimal("0.00")
            growth = 0.0
            if previous_net:
                growth = round(float((net - previous_net) / previous_net) * 100, 2)

            RevenueSnapshot.objects.update_or_create(
                photographer_id=photographer_id,
                year=row["completed_at__year"],
                month=row["completed_at__month"],
                defaults={
                    "bookings_completed": row["completed"],
                    "gross_revenue": row["gross"] or Decimal("0.00"),
                    "commission": row["commission"] or Decimal("0.00"),
                    "net_earnings": net,
                    "growth_percent": growth,
                },
            )
            previous_net = net
            written += 1

    logger.info("Rebuilt %s revenue snapshots", written)
    return written


# ═══════════════════════════════════════════════════════════════════════════
# PLATFORM-WIDE
# ═══════════════════════════════════════════════════════════════════════════
@transaction.atomic
def rollup_platform_day(target: date_cls) -> PlatformStat:
    """One row per day for the whole platform — powers the admin dashboard."""
    from django.contrib.auth import get_user_model

    from apps.bookings.constants import BookingStatus
    from apps.bookings.models import Booking
    from apps.marketplace.models import DigitalProduct, OrderItem, OrderStatus
    from apps.profiles.models import PhotographerProfile
    from apps.reviews.models import Review

    User = get_user_model()

    bookings = Booking.objects.filter(
        Q(created_at__date=target)
        | Q(completed_at__date=target)
        | Q(cancelled_at__date=target)
    ).aggregate(
        created=Count("id", filter=Q(created_at__date=target)),
        completed=Count("id", filter=Q(completed_at__date=target)),
        cancelled=Count("id", filter=Q(cancelled_at__date=target)),
        expired=Count(
            "id", filter=Q(status=BookingStatus.EXPIRED, updated_at__date=target)
        ),
        gross=Sum("total_price", filter=Q(completed_at__date=target)),
        commission=Sum("commission_amount", filter=Q(completed_at__date=target)),
    )

    marketplace = OrderItem.objects.filter(
        order__status=OrderStatus.PAID, order__paid_at__date=target
    ).aggregate(sold=Count("id"), revenue=Sum("commission_amount"))

    reviews = Review.objects.filter(created_at__date=target).aggregate(
        posted=Count("id"), avg=Avg("rating")
    )

    created = bookings["created"] or 0
    cancelled = bookings["cancelled"] or 0

    stat, _ = PlatformStat.objects.update_or_create(
        date=target,
        defaults={
            "total_users": User.objects.filter(created_at__date__lte=target).count(),
            "new_users": User.objects.filter(created_at__date=target).count(),
            "total_buyers": User.objects.buyers().filter(created_at__date__lte=target).count(),
            "total_photographers": PhotographerProfile.objects.filter(
                created_at__date__lte=target
            ).count(),
            "approved_photographers": PhotographerProfile.objects.filter(
                is_approved=True, created_at__date__lte=target
            ).count(),
            "bookings_created": created,
            "bookings_completed": bookings["completed"] or 0,
            "bookings_cancelled": cancelled,
            "bookings_expired": bookings["expired"] or 0,
            "gross_booking_value": bookings["gross"] or Decimal("0.00"),
            "platform_commission": bookings["commission"] or Decimal("0.00"),
            "marketplace_revenue": marketplace["revenue"] or Decimal("0.00"),
            "products_sold": marketplace["sold"] or 0,
            "products_published": DigitalProduct.objects.filter(
                is_published=True, created_at__date__lte=target
            ).count(),
            "reviews_posted": reviews["posted"] or 0,
            "avg_platform_rating": Decimal(f"{reviews['avg'] or 0:.2f}"),
            "cancellation_rate": round(cancelled / created, 4) if created else 0.0,
        },
    )
    return stat
