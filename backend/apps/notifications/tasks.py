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

    # Quiet hours suppress the PUSH channel only — the in-app record was
    # already written, so nothing is lost, it just does not buzz at 03:00.
    # Critical types (a cancelled booking, a blocked account) ignore the window:
    # somebody who muted everything still has to learn that a paid shoot is off.
    from apps.notifications.services import CRITICAL_TYPES, in_quiet_hours

    if (
        notification.notification_type not in CRITICAL_TYPES
        and in_quiet_hours(prefs)
    ):
        NotificationDelivery.objects.update_or_create(
            notification=notification, channel="PUSH",
            defaults={"status": "SKIPPED", "provider_response": "quiet hours"},
        )
        return {"skipped": "quiet hours"}

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


#: A notification is a nudge, not a record. Past this it is scrollback nobody
#: reads, and the table is one of the fastest-growing in the schema.
RETAIN_READ_DAYS = 30
RETAIN_UNREAD_DAYS = 90


@shared_task
def purge_old_notifications():
    """
    Trim the notification table.

    Read rows go after 30 days, unread after 90. The asymmetry is deliberate: a
    notification nobody has opened may still be the only record of something
    they need, so it gets three times as long before it is dropped.
    """
    from datetime import timedelta

    from apps.notifications.models import Notification

    now = timezone.now()
    read_deleted, _ = Notification.objects.filter(
        is_read=True, created_at__lt=now - timedelta(days=RETAIN_READ_DAYS)
    ).delete()
    unread_deleted, _ = Notification.objects.filter(
        is_read=False, created_at__lt=now - timedelta(days=RETAIN_UNREAD_DAYS)
    ).delete()

    logger.info(
        "Notifications purged: %s read, %s unread", read_deleted, unread_deleted
    )
    return {"read": read_deleted, "unread": unread_deleted}
