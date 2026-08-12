"""Model training and feature-store refresh."""

import logging

from celery import shared_task

logger = logging.getLogger("snapsphere")


@shared_task
def retrain_models():
    """Retrain, evaluate, and promote only if not worse than the live model."""
    # Implemented in Module 10 (AI Recommendation).
    logger.info("retrain_models: pending Module 10 implementation")
    return {"status": "not_implemented"}


@shared_task
def refresh_photographer_features():
    """Rebuild the PhotographerFeature rows the scorer reads at request time."""
    logger.info("refresh_photographer_features: pending Module 10 implementation")
    return {"status": "not_implemented"}
