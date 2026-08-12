"""
Notification creation and fan-out.

`notify()` is the single entry point used by every other app. It writes the
in-app record synchronously (so the bell badge is instantly correct) and
schedules the slower channels for after the transaction commits.
"""

import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction

from apps.notifications.models import (
    Notification,
    NotificationPreference,
    NotificationType,
)

logger = logging.getLogger("snapsphere")

#: These reach the user regardless of preference settings. Someone who muted
#: notifications still needs to know their paid booking was cancelled.
CRITICAL_TYPES = {
    NotificationType.BOOKING_CANCELLED,
    NotificationType.BOOKING_REJECTED,
    NotificationType.ACCOUNT_BLOCKED,
    NotificationType.ACCOUNT_APPROVED,
    NotificationType.WALLET_CREDITED,
}

#: Maps a notification-type prefix to the preference flag that can silence it.
_PREFERENCE_FIELD = {
    "BOOKING_": "booking_updates",
    "NEW_MESSAGE": "chat_messages",
    "REVIEW_": "review_activity",
    "PRODUCT_": "marketplace_activity",
    "PROMOTION": "promotions",
}


def _is_muted(user, notification_type: str) -> bool:
    if notification_type in CRITICAL_TYPES:
        return False
    prefs = getattr(user, "notification_preference", None)
    if prefs is None:
        prefs = NotificationPreference.objects.filter(user=user).first()
    if prefs is None:
        return False
    for prefix, field in _PREFERENCE_FIELD.items():
        if notification_type.startswith(prefix):
            return not getattr(prefs, field, True)
    return False


def notify(
    recipient,
    notification_type: str,
    *,
    title: str,
    body: str,
    action_screen: str = "",
    action_id: str = "",
    actor=None,
    payload: dict | None = None,
    push: bool = True,
) -> Notification | None:
    """
    Create a notification and deliver it.

    Returns None when the user has muted this category, so callers never need
    to check preferences themselves.
    """
    if _is_muted(recipient, notification_type):
        logger.debug(
            "Notification muted",
            extra={"user_id": recipient.id, "type": notification_type},
        )
        return None

    notification = Notification.objects.create(
        recipient=recipient,
        notification_type=notification_type,
        title=title,
        body=body,
        action_screen=action_screen,
        action_id=action_id,
        actor=actor,
        payload=payload or {},
    )

    # Deliver only after the surrounding transaction commits. Pushing for a
    # transaction that then rolls back would tell the user something happened
    # when it did not.
    transaction.on_commit(lambda: push_realtime(notification))
    if push:
        transaction.on_commit(lambda: _queue_push(notification.pk))
    return notification


def push_realtime(notification: Notification) -> None:
    """Stream over the recipient's private WebSocket group, if connected."""
    layer = get_channel_layer()
    if layer is None:  # tests, or Redis unavailable
        return
    try:
        async_to_sync(layer.group_send)(
            f"notifications_{notification.recipient_id}",
            {
                "type": "notification.message",
                "notification": {
                    "id": notification.pk,
                    "notification_type": notification.notification_type,
                    "title": notification.title,
                    "body": notification.body,
                    "action_screen": notification.action_screen,
                    "action_id": notification.action_id,
                    "created_at": notification.created_at.isoformat(),
                    "is_read": False,
                },
            },
        )
    except Exception as exc:  # noqa: BLE001
        # A notification that fails to stream is still in the database and
        # appears next time the bell is opened. This must never break the
        # request that triggered it.
        logger.warning("Realtime notification failed: %s", exc)


def _queue_push(notification_id: int) -> None:
    from apps.notifications.tasks import send_push_notification

    send_push_notification.delay(notification_id)


def notify_many(recipients, notification_type: str, **kwargs) -> int:
    return sum(1 for r in recipients if notify(r, notification_type, **kwargs))
