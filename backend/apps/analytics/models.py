"""
Analytics rollups.

WHY PRE-AGGREGATED TABLES INSTEAD OF LIVE QUERIES
-------------------------------------------------
"Revenue per month for the last 12 months" over a growing bookings table is a
full scan with a GROUP BY. Run it every time a dashboard loads and the
dashboard becomes the slowest screen in the product — and it gets slower as
the business succeeds.

A nightly Celery job writes one row per photographer per day. The dashboard
then reads 30 or 365 tiny pre-computed rows. The cost is bounded and constant.

These tables mirror the schema of service_engagement_dataset.csv /
service_revenue_dataset.csv, so those files load directly as historical data.
"""

from decimal import Decimal

from django.db import models

from apps.core.models import TimeStampedModel


class DailyPhotographerStat(TimeStampedModel):
    """One row per photographer per day — the analytics fact table."""

    photographer = models.ForeignKey(
        "profiles.PhotographerProfile", on_delete=models.CASCADE,
        related_name="daily_stats",
    )
    date = models.DateField(db_index=True)
    category = models.ForeignKey(
        "catalog.Category", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="daily_stats",
    )

    # ─── Funnel (matches the CSV columns exactly) ────────────────────────────
    search_visibility = models.IntegerField(default=0)
    profile_views = models.IntegerField(default=0)
    clicks = models.IntegerField(default=0)
    portfolio_interactions = models.IntegerField(default=0)
    inquiries = models.IntegerField(default=0)

    # ─── Bookings ────────────────────────────────────────────────────────────
    bookings_created = models.IntegerField(default=0)
    bookings_accepted = models.IntegerField(default=0)
    bookings_completed = models.IntegerField(default=0)
    bookings_cancelled = models.IntegerField(default=0)
    bookings_rejected = models.IntegerField(default=0)

    # ─── Money ───────────────────────────────────────────────────────────────
    revenue = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal("0.00")
    )
    commission_paid = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal("0.00")
    )
    product_revenue = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal("0.00")
    )

    # ─── Derived rates (stored, so charts don't divide on the client) ────────
    conversion_rate = models.FloatField(
        default=0.0, help_text="bookings_created / profile_views"
    )
    response_rate = models.FloatField(
        default=0.0, help_text="responded / requests received"
    )

    # ─── Reviews ─────────────────────────────────────────────────────────────
    reviews_received = models.IntegerField(default=0)
    avg_rating_snapshot = models.DecimalField(
        max_digits=3, decimal_places=2, default=Decimal("0.00")
    )

    class Meta:
        db_table = "daily_photographer_stats"
        ordering = ("-date",)
        constraints = [
            models.UniqueConstraint(
                fields=["photographer", "date"], name="uniq_daily_stat_per_photog"
            )
        ]
        indexes = [
            # The exact shape of "last N days for this photographer".
            models.Index(
                fields=["photographer", "-date"], name="idx_dailystat_timeline"
            ),
            models.Index(fields=["date"], name="idx_dailystat_by_date"),
        ]

    def __str__(self) -> str:
        return f"{self.photographer_id} on {self.date}"


class PlatformStat(TimeStampedModel):
    """One row per day for the whole platform — powers the admin dashboard."""

    date = models.DateField(unique=True, db_index=True)

    # ─── Users ───────────────────────────────────────────────────────────────
    total_users = models.IntegerField(default=0)
    new_users = models.IntegerField(default=0)
    total_buyers = models.IntegerField(default=0)
    total_photographers = models.IntegerField(default=0)
    approved_photographers = models.IntegerField(default=0)
    active_users = models.IntegerField(default=0)

    # ─── Bookings ────────────────────────────────────────────────────────────
    bookings_created = models.IntegerField(default=0)
    bookings_completed = models.IntegerField(default=0)
    bookings_cancelled = models.IntegerField(default=0)
    bookings_expired = models.IntegerField(default=0)

    # ─── Money ───────────────────────────────────────────────────────────────
    gross_booking_value = models.DecimalField(
        max_digits=16, decimal_places=2, default=Decimal("0.00")
    )
    platform_commission = models.DecimalField(
        max_digits=16, decimal_places=2, default=Decimal("0.00")
    )
    marketplace_revenue = models.DecimalField(
        max_digits=16, decimal_places=2, default=Decimal("0.00")
    )

    # ─── Marketplace ─────────────────────────────────────────────────────────
    products_sold = models.IntegerField(default=0)
    products_published = models.IntegerField(default=0)

    # ─── Quality ─────────────────────────────────────────────────────────────
    reviews_posted = models.IntegerField(default=0)
    avg_platform_rating = models.DecimalField(
        max_digits=3, decimal_places=2, default=Decimal("0.00")
    )
    cancellation_rate = models.FloatField(default=0.0)

    class Meta:
        db_table = "platform_stats"
        ordering = ("-date",)

    def __str__(self) -> str:
        return f"Platform stats {self.date}"


class RevenueSnapshot(TimeStampedModel):
    """
    Monthly per-photographer earnings summary.

    Separate from the daily table because the earnings screen and payout
    reports are month-grained, and summing 30 daily rows per month per
    photographer on every page load is waste that compounds.
    """

    photographer = models.ForeignKey(
        "profiles.PhotographerProfile", on_delete=models.CASCADE,
        related_name="revenue_snapshots",
    )
    year = models.PositiveSmallIntegerField()
    month = models.PositiveSmallIntegerField()

    bookings_completed = models.IntegerField(default=0)
    gross_revenue = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal("0.00")
    )
    commission = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal("0.00")
    )
    net_earnings = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal("0.00")
    )
    product_earnings = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal("0.00")
    )

    payout_status = models.CharField(
        max_length=16,
        choices=[
            ("PENDING", "Pending"), ("PROCESSING", "Processing"),
            ("PAID", "Paid"), ("HELD", "Held"),
        ],
        default="PENDING", db_index=True,
    )
    paid_at = models.DateTimeField(null=True, blank=True)

    # Month-over-month change, stored so the "+18%" badge needs no extra query.
    growth_percent = models.FloatField(default=0.0)

    class Meta:
        db_table = "revenue_snapshots"
        ordering = ("-year", "-month")
        constraints = [
            models.UniqueConstraint(
                fields=["photographer", "year", "month"],
                name="uniq_revenue_per_month",
            )
        ]
        indexes = [
            models.Index(
                fields=["photographer", "-year", "-month"], name="idx_revenue_timeline"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.photographer_id} {self.year}-{self.month:02d}: Rs {self.net_earnings}"


class SearchQueryLog(TimeStampedModel):
    """
    What buyers actually search for.

    Zero-result queries are the single most actionable dataset a marketplace
    has: they name the supply you are missing.
    """

    user = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="search_logs",
    )
    query = models.CharField(max_length=200, db_index=True)
    filters = models.JSONField(default=dict, blank=True)
    result_count = models.IntegerField(default=0, db_index=True)
    clicked_position = models.PositiveSmallIntegerField(null=True, blank=True)
    session_id = models.CharField(max_length=64, blank=True)

    class Meta:
        db_table = "search_query_logs"
        indexes = [
            models.Index(fields=["result_count", "-created_at"], name="idx_zero_results"),
        ]

    def __str__(self) -> str:
        return f"'{self.query}' → {self.result_count} results"
