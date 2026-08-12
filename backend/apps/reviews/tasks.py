"""Review-related background jobs."""

import logging

from celery import shared_task

logger = logging.getLogger("snapsphere")


@shared_task
def check_review_eligibility():
    """Nudge buyers who completed a booking but haven't reviewed it yet."""
    # Implemented in Module 9 (Review & Rating).
    logger.info("check_review_eligibility: pending Module 9 implementation")
    return {"status": "not_implemented"}
