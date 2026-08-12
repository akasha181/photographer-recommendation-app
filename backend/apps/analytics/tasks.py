"""Nightly rollups that keep the dashboards fast."""

import logging

from celery import shared_task

logger = logging.getLogger("snapsphere")


@shared_task
def rollup_daily_analytics():
    """Aggregate yesterday's activity into DailyPhotographerStat/PlatformStat."""
    # Implemented in Module 15 (Analytics Dashboard).
    logger.info("rollup_daily_analytics: pending Module 15 implementation")
    return {"status": "not_implemented"}


@shared_task
def send_weekly_digest():
    """Email photographers their weekly performance summary."""
    logger.info("send_weekly_digest: pending Module 15 implementation")
    return {"status": "not_implemented"}
