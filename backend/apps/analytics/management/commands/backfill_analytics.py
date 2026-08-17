"""
Rebuild the analytics rollups from the live tables.

    python manage.py backfill_analytics --days 365

Needed after a data import, after a fix to the aggregation, or simply to give
a fresh install charts that are not empty. Idempotent: every write is an
update_or_create keyed on the date, so running it twice over the same range
corrects rather than double-counts.
"""

from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = "Rebuild DailyPhotographerStat, RevenueSnapshot and PlatformStat."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days", type=int, default=365, help="How far back to rebuild."
        )
        parser.add_argument(
            "--platform",
            action="store_true",
            help="Also rebuild PlatformStat (slower — it counts users per day).",
        )

    def handle(self, *args, **options):
        from datetime import timedelta

        from apps.analytics.services import (
            rebuild_revenue_snapshots,
            rollup_day,
            rollup_platform_day,
        )

        days = options["days"]
        until = timezone.localdate()
        start = until - timedelta(days=days - 1)

        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f"\nRebuilding analytics from {start} to {until}\n"
            )
        )

        rows = 0
        cursor = start
        processed = 0
        while cursor <= until:
            rows += rollup_day(cursor)
            if options["platform"]:
                rollup_platform_day(cursor)
            processed += 1
            if processed % 30 == 0:
                self.stdout.write(f"  …{processed}/{days} days, {rows} stat rows")
            cursor += timedelta(days=1)

        self.stdout.write("  rebuilding monthly revenue…")
        snapshots = rebuild_revenue_snapshots()

        self.stdout.write(
            self.style.SUCCESS(
                f"\n  ✓ {rows} daily rows · {snapshots} monthly snapshots\n"
            )
        )
