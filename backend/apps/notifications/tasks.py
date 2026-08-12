"""Background delivery of notifications."""

import logging

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger("snapsphere")


@shared_task(bind=True, max_retries=2, default_retry_delay=30)
def send_push_notification(self, notification_id: int):
    """
    Deliver to every active device token for the recipient.

    The provider call is stubbed until FCM credentials are configured; the
    delivery-record bookkeeping around it is real, so wiring in the provider
    later is a one-function change.
    """
    from apps.notifications.models import (
        Notification,
        NotificationDelivery,
        PushToken,
    )

    notification = Notification.objects.select_related("recipient").filter(
        pk=notification_id
    ).first()
    if notification is None:
        return {"skipped": "notification deleted"}

    prefs = getattr(notification.recipient, "notification_preference", None)
    if prefs and not prefs.push_enabled:
        NotificationDelivery.objects.update_or_create(
            notification=notification, channel="PUSH",
            defaults={"status": "SKIPPED", "provider_response": "push disabled"},
        )
        return {"skipped": "push disabled"}

    tokens = list(
        PushToken.objects.filter(
            user=notification.recipient, is_active=True
        ).values_list("token", flat=True)
    )
    if not tokens:
        NotificationDelivery.objects.update_or_create(
            notification=notification, channel="PUSH",
            defaults={"status": "SKIPPED", "provider_response": "no active tokens"},
        )
        return {"skipped": "no tokens"}

    # TODO(module-12): replace with the Expo/FCM HTTP call once credentials exist.
    logger.info(
        "PUSH → %s device(s): %s",
        len(tokens), notification.title,
        extra={"user_id": notification.recipient_id},
    )

    NotificationDelivery.objects.update_or_create(
        notification=notification, channel="PUSH",
        defaults={
            "status": "SENT",
            "sent_at": timezone.now(),
            "provider_response": f"stub delivery to {len(tokens)} token(s)",
        },
    )
    return {"sent": len(tokens)}


@shared_task
def send_broadcast(broadcast_id: int):
    """Fan an admin announcement out to its filtered audience."""
    from django.contrib.auth import get_user_model

    from apps.core.constants import UserRole
    from apps.notifications.models import Broadcast
    from apps.notifications.services import notify_many

    User = get_user_model()
    broadcast = Broadcast.objects.get(pk=broadcast_id)

    audience = User.objects.filter(is_active=True, is_blocked=False)
    if broadcast.audience == "BUYERS":
        audience = audience.filter(role=UserRole.BUYER)
    elif broadcast.audience == "PHOTOGRAPHERS":
        audience = audience.filter(role=UserRole.PHOTOGRAPHER)
    elif broadcast.audience == "CITY":
        audience = audience.filter(city=broadcast.city_filter)

    sent = notify_many(
        audience.iterator(),
        "ADMIN_MESSAGE",
        title=broadcast.title,
        body=broadcast.body,
        push=broadcast.send_push,
    )

    broadcast.sent_at = timezone.now()
    broadcast.recipient_count = sent
    broadcast.save(update_fields=["sent_at", "recipient_count", "updated_at"])
    return {"sent": sent}
