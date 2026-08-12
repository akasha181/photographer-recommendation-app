"""Celery application + the platform's scheduled jobs."""

import os

from celery import Celery
from celery.schedules import crontab

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

app = Celery("snapsphere")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


# ═══════════════════════════════════════════════════════════════════════════
# SCHEDULED JOBS  (docs/01-system-architecture.md §12.3)
# All times are Asia/Karachi via CELERY_TIMEZONE.
# ═══════════════════════════════════════════════════════════════════════════
app.conf.beat_schedule = {
    "expire-pending-bookings": {
        "task": "apps.bookings.tasks.expire_pending_bookings",
        "schedule": crontab(minute="*/15"),
    },
    "auto-complete-bookings": {
        "task": "apps.bookings.tasks.auto_complete_bookings",
        "schedule": crontab(hour=3, minute=0),
    },
    "send-booking-reminders": {
        "task": "apps.bookings.tasks.send_booking_reminders",
        "schedule": crontab(hour=9, minute=0),
    },
    "rollup-daily-analytics": {
        "task": "apps.analytics.tasks.rollup_daily_analytics",
        "schedule": crontab(hour=1, minute=0),
    },
    "retrain-models": {
        "task": "apps.recommendations.tasks.retrain_models",
        "schedule": crontab(hour=2, minute=0),
    },
    "refresh-photographer-features": {
        "task": "apps.recommendations.tasks.refresh_photographer_features",
        "schedule": crontab(hour=2, minute=30),
    },
    "cleanup-expired-tokens": {
        "task": "apps.accounts.tasks.cleanup_expired_tokens",
        "schedule": crontab(hour=4, minute=0),
    },
    "send-weekly-digest": {
        "task": "apps.analytics.tasks.send_weekly_digest",
        "schedule": crontab(day_of_week=1, hour=10, minute=0),
    },
    "check-review-eligibility": {
        "task": "apps.reviews.tasks.check_review_eligibility",
        "schedule": crontab(hour=11, minute=0),
    },
}


@app.task(bind=True, ignore_result=True)
def debug_task(self):  # pragma: no cover
    print(f"Request: {self.request!r}")
