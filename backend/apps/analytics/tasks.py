"""Nightly rollups that keep the dashboards fast."""

import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger("snapsphere")


@shared_task
def rollup_daily_analytics():
    """
    Aggregate yesterday into DailyPhotographerStat and PlatformStat.

    Yesterday, not today: a rollup of a day still in progress is wrong the
    moment another booking lands, and the dashboard computes its headline
    numbers live precisely so today does not need a rollup to be correct.

    Idempotent — every write is an update_or_create keyed on the date, so a
    retry after a failure corrects the row instead of double-counting.
    """
    from apps.analytics.services import rollup_day, rollup_platform_day

    yesterday = timezone.localdate() - timedelta(days=1)
    photographers = rollup_day(yesterday)
    rollup_platform_day(yesterday)

    logger.info("Daily rollup complete for %s", yesterday)
    return {"date": str(yesterday), "photographers": photographers}


@shared_task
def rebuild_monthly_revenue():
    """Refresh month-grained earnings — cheap, and self-healing if a day was missed."""
    from apps.analytics.services import rebuild_revenue_snapshots

    written = rebuild_revenue_snapshots()
    return {"snapshots": written}


@shared_task
def send_weekly_digest():
    """Email photographers their weekly performance summary."""
    logger.info("send_weekly_digest: pending")
    return {"status": "not_implemented"}
