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
from django.utils import timezone

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
    """
    Whether this user has silenced this category.

    READS THE DATABASE, NOT `user.notification_preference`. Django caches a
    reverse one-to-one on the instance the moment it is touched, and
    `_ensure_notification_preference` touches it during registration — so the
    attribute on a long-lived `user` object can be the row as it was before the
    settings screen saved. Same trap as `user.wallet.balance`, same fix: the
    database is the authority. One narrow indexed SELECT per notification, next
    to an INSERT that was happening anyway.
    """
    if notification_type in CRITICAL_TYPES:
        return False

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


# ═══════════════════════════════════════════════════════════════════════════
# READ STATE
# The REST layer for these is Module 12. Every function takes the acting user
# and filters on `recipient=user`, so there is no code path — present or
# future — that marks somebody else's mail as read.
# ═══════════════════════════════════════════════════════════════════════════
def mark_read(user, ids: list[int] | None = None) -> int:
    """
    Mark some notifications read, or all of them when `ids` is empty.

    `.update()` in one statement rather than a loop of saves: clearing a badge
    of 200 must not be 200 round trips, and `read_at` should be the same instant
    for all of them — they were read in one gesture.
    """
    qs = Notification.objects.filter(recipient=user, is_read=False)
    if ids:
        qs = qs.filter(pk__in=ids)
    return qs.update(is_read=True, read_at=timezone.now())


def mark_unread(user, notification_id: int) -> bool:
    """Undo — "I'll deal with this later" is a real thing people want."""
    updated = Notification.objects.filter(
        pk=notification_id, recipient=user, is_read=True
    ).update(is_read=False, read_at=None)
    return bool(updated)


def delete_notification(user, notification_id: int) -> bool:
    """
    Hard delete, deliberately.

    `Notification` is a delivery record, not a financial one — nothing
    references it and nobody audits it. Soft-deleting would leave a table that
    grows forever and an inbox that has to filter on two flags.
    """
    deleted, _ = Notification.objects.filter(
        pk=notification_id, recipient=user
    ).delete()
    return bool(deleted)


def clear_inbox(user, *, read_only: bool = True) -> int:
    """
    Empty the bell. Defaults to clearing only what has been read, because
    "Clear all" wiping an unread booking cancellation would be destructive in a
    way the button does not look.
    """
    qs = Notification.objects.filter(recipient=user)
    if read_only:
        qs = qs.filter(is_read=True)
    deleted, _ = qs.delete()
    return deleted


# ═══════════════════════════════════════════════════════════════════════════
# PREFERENCES & DEVICES
# ═══════════════════════════════════════════════════════════════════════════
def update_preferences(user, **data) -> NotificationPreference:
    prefs, _ = NotificationPreference.objects.get_or_create(user=user)
    for field, value in data.items():
        setattr(prefs, field, value)
    prefs.save()

    # Drop the stale reverse-one-to-one cache on the caller's user instance so
    # anything later in the same request reads the row that was just saved.
    user.__dict__.pop("notification_preference", None)
    return prefs


def register_push_token(user, *, token: str, platform: str, device_id: str = ""):
    """
    Idempotent device registration.

    The app calls this on every launch, because a push token can be rotated by
    the OS at any time. `update_or_create` on (user, token) — which is the
    unique constraint — makes a repeat launch a no-op instead of an
    IntegrityError, and reactivates a token that was disabled after earlier
    provider rejections.
    """
    from apps.notifications.models import PushToken

    row, created = PushToken.objects.update_or_create(
        user=user,
        token=token,
        defaults={
            "platform": platform,
            "device_id": device_id,
            "is_active": True,
            "failure_count": 0,
        },
    )
    # One device, one token: when the OS rotates a token the old row would
    # otherwise keep receiving pushes that silently go nowhere.
    if device_id:
        PushToken.objects.filter(user=user, device_id=device_id).exclude(
            pk=row.pk
        ).update(is_active=False)
    return row, created


def unregister_push_token(user, token: str) -> bool:
    """
    Called on logout.

    Deactivated rather than deleted so `failure_count` history survives — a
    token that keeps failing is a signal, and a deleted row starts that count
    from zero on the next launch.
    """
    from apps.notifications.models import PushToken

    updated = PushToken.objects.filter(user=user, token=token).update(is_active=False)
    return bool(updated)


def in_quiet_hours(prefs, at=None) -> bool:
    """
    Whether push should be held back right now.

    Handles the window that crosses midnight (22:00 → 08:00), which is the
    default and the case a naive `start <= now <= end` gets wrong for every
    hour of the night.
    """
    if prefs is None or not prefs.quiet_hours_enabled:
        return False

    now = (at or timezone.localtime()).time()
    start, end = prefs.quiet_hours_start, prefs.quiet_hours_end
    if start == end:
        return False
    if start < end:
        return start <= now < end
    return now >= start or now < end
