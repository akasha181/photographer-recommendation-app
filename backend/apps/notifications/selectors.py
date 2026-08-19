"""
Notification reads — Module 12.

EVERY QUERY IS SCOPED TO ONE RECIPIENT
--------------------------------------
There is no "notifications for user X" path and no admin list here. A
notification is addressed mail: the only person entitled to read it is the
person it was sent to. `recipient=user` is therefore not a filter that could be
forgotten in some future view — it is the first argument of every function in
this file.

THE UNREAD BADGE IS A COUNT, NOT A LIST
---------------------------------------
The bell renders a number. Fetching 30 notifications to call `.length` on the
unread ones costs a page of JSON on every app resume; `idx_notif_inbox` covers
`(recipient, is_read, -created_at)`, so the count is an index-only scan.
"""

from django.db.models import Count, Q

from apps.notifications.models import Notification, NotificationPreference

#: Coarse groups the app offers as filter chips. Mapped to type prefixes rather
#: than to an enumerated list so a new BOOKING_* type joins the right chip
#: without a change here.
CATEGORY_PREFIXES = {
    "bookings": ("BOOKING_",),
    "messages": ("NEW_MESSAGE",),
    "reviews": ("REVIEW_",),
    "marketplace": ("PRODUCT_",),
    "account": ("ACCOUNT_", "WALLET_", "PAYOUT_"),
    "platform": ("ADMIN_MESSAGE", "PROMOTION"),
}


def inbox(user, *, unread_only: bool = False, category: str | None = None):
    """The bell list, newest first."""
    qs = Notification.objects.filter(recipient=user).select_related("actor")

    if unread_only:
        qs = qs.filter(is_read=False)

    prefixes = CATEGORY_PREFIXES.get((category or "").lower())
    if prefixes:
        clause = Q()
        for prefix in prefixes:
            clause |= Q(notification_type__startswith=prefix)
        qs = qs.filter(clause)

    return qs.order_by("-created_at")


def unread_count(user) -> int:
    return Notification.objects.filter(recipient=user, is_read=False).count()


def badge_counts(user) -> dict:
    """
    Total unread plus a per-category split, in ONE query.

    The app draws a badge on the bell and, on the photographer's tab bar, a
    separate one on Messages. Two endpoints for that would mean two round trips
    on every resume from background.
    """
    agg = Notification.objects.filter(recipient=user, is_read=False).aggregate(
        total=Count("id"),
        bookings=Count("id", filter=Q(notification_type__startswith="BOOKING_")),
        messages=Count("id", filter=Q(notification_type="NEW_MESSAGE")),
        reviews=Count("id", filter=Q(notification_type__startswith="REVIEW_")),
        marketplace=Count("id", filter=Q(notification_type__startswith="PRODUCT_")),
    )
    return {key: value or 0 for key, value in agg.items()}


def get_notification(user, pk) -> Notification | None:
    """Scoped fetch — somebody else's notification is simply not found."""
    return Notification.objects.filter(pk=pk, recipient=user).first()


def preferences(user) -> NotificationPreference:
    """
    The user's channel switches, created on first read.

    `get_or_create` rather than a nullable read: the settings screen needs
    something to render, and defaults that only exist in the model definition
    would mean the screen shows different values before and after the first
    save.
    """
    prefs, _ = NotificationPreference.objects.get_or_create(user=user)
    return prefs


def active_push_tokens(user):
    return user.push_tokens.filter(is_active=True).order_by("-updated_at")
