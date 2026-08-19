"""
Notifications — Module 12.

THE PROPERTIES UNDER TEST
------------------------
1. A notification reaches exactly one inbox, and no endpoint can read or clear
   somebody else's.
2. The badge number always equals the unread rows behind it.
3. Muting silences the channel it names and nothing else — and never silences a
   cancelled booking.
"""

from datetime import time, timedelta

import pytest
from django.utils import timezone

from apps.notifications import selectors, services
from apps.notifications.models import (
    Notification,
    NotificationPreference,
    NotificationType,
    PushToken,
)

pytestmark = pytest.mark.django_db

URL = "/api/v1/notifications/"


def make(user, **overrides):
    payload = {
        "notification_type": NotificationType.BOOKING_REQUEST,
        "title": "New booking request",
        "body": "Ayesha wants to book you.",
    }
    payload.update(overrides)
    return Notification.objects.create(recipient=user, **payload)


# ═══════════════════════════════════════════════════════════════════════════
# SCOPING — addressed mail
# ═══════════════════════════════════════════════════════════════════════════
def test_the_inbox_shows_only_your_own(buyer_client, buyer, other_buyer):
    make(buyer, title="Yours")
    make(other_buyer, title="Theirs")

    rows = buyer_client.get(URL).json()["data"]

    assert [row["title"] for row in rows] == ["Yours"]


def test_you_cannot_delete_somebody_elses(other_buyer_client, buyer):
    notification = make(buyer)

    response = other_buyer_client.delete(f"{URL}{notification.pk}/")

    assert response.status_code == 404
    assert Notification.objects.filter(pk=notification.pk).exists()


def test_marking_all_read_does_not_touch_another_inbox(buyer_client, buyer, other_buyer):
    make(buyer)
    theirs = make(other_buyer)

    buyer_client.post(f"{URL}mark-read/", {}, format="json")

    theirs.refresh_from_db()
    assert theirs.is_read is False


def test_anonymous_callers_are_refused(api_client):
    assert api_client.get(URL).status_code == 401


# ═══════════════════════════════════════════════════════════════════════════
# THE BADGE MATCHES THE ROWS
# ═══════════════════════════════════════════════════════════════════════════
def test_unread_count_matches(buyer_client, buyer):
    make(buyer)
    make(buyer)
    read = make(buyer)
    services.mark_read(buyer, [read.pk])

    body = buyer_client.get(f"{URL}unread-count/").json()["data"]

    assert body["total"] == 2
    assert body["bookings"] == 2


def test_badge_counts_split_by_category(buyer_client, buyer):
    make(buyer, notification_type=NotificationType.BOOKING_REQUEST)
    make(buyer, notification_type=NotificationType.NEW_MESSAGE)
    make(buyer, notification_type=NotificationType.REVIEW_REPLIED)
    make(buyer, notification_type=NotificationType.PRODUCT_SOLD)

    body = buyer_client.get(f"{URL}unread-count/").json()["data"]

    assert body == {
        "total": 4, "bookings": 1, "messages": 1, "reviews": 1, "marketplace": 1
    }


def test_mark_read_with_ids_leaves_the_rest(buyer_client, buyer):
    first = make(buyer)
    make(buyer)

    body = buyer_client.post(
        f"{URL}mark-read/", {"ids": [first.pk]}, format="json"
    ).json()["data"]

    assert body == {"updated": 1, "unread_count": 1}


def test_empty_ids_means_everything(buyer_client, buyer):
    make(buyer)
    make(buyer)

    body = buyer_client.post(f"{URL}mark-read/", {}, format="json").json()["data"]

    assert body == {"updated": 2, "unread_count": 0}


def test_the_list_does_not_mark_anything_read(buyer_client, buyer):
    """
    Opening the bell is not reading the items.

    Auto-clearing on GET makes a badge vanish when the user glances at the
    screen, and then they cannot find what it was about.
    """
    notification = make(buyer)

    buyer_client.get(URL)
    notification.refresh_from_db()

    assert notification.is_read is False


def test_unread_can_be_undone(buyer_client, buyer):
    notification = make(buyer)
    services.mark_read(buyer, [notification.pk])

    body = buyer_client.post(f"{URL}{notification.pk}/unread/").json()["data"]
    notification.refresh_from_db()

    assert notification.is_read is False
    assert notification.read_at is None
    assert body["unread_count"] == 1


def test_clear_removes_only_what_was_read(buyer_client, buyer):
    read = make(buyer, title="Read")
    make(buyer, title="Unread")
    services.mark_read(buyer, [read.pk])

    body = buyer_client.post(f"{URL}clear/").json()["data"]

    assert body["removed"] == 1
    assert list(Notification.objects.filter(recipient=buyer).values_list("title", flat=True)) == [
        "Unread"
    ]


def test_the_list_carries_the_unread_count_in_meta(buyer_client, buyer):
    """One request draws the screen: the rows and the number cannot disagree."""
    make(buyer)

    envelope = buyer_client.get(URL).json()

    assert envelope["meta"]["unread_count"] == 1


# ═══════════════════════════════════════════════════════════════════════════
# CATEGORY FILTER
# ═══════════════════════════════════════════════════════════════════════════
def test_category_filter_uses_the_same_prefix_map_as_the_serializer(buyer_client, buyer):
    make(buyer, notification_type=NotificationType.BOOKING_ACCEPTED, title="Booking")
    make(buyer, notification_type=NotificationType.NEW_MESSAGE, title="Message")

    rows = buyer_client.get(f"{URL}?category=bookings").json()["data"]

    assert [row["title"] for row in rows] == ["Booking"]
    assert rows[0]["category"] == "bookings"


def test_unread_filter(buyer_client, buyer):
    read = make(buyer, title="Read")
    make(buyer, title="Unread")
    services.mark_read(buyer, [read.pk])

    rows = buyer_client.get(f"{URL}?unread=1").json()["data"]

    assert [row["title"] for row in rows] == ["Unread"]


# ═══════════════════════════════════════════════════════════════════════════
# PREFERENCES
# ═══════════════════════════════════════════════════════════════════════════
def test_preferences_exist_on_first_read(buyer_client, buyer):
    NotificationPreference.objects.filter(user=buyer).delete()

    body = buyer_client.get(f"{URL}preferences/").json()["data"]

    assert body["push_enabled"] is True
    assert NotificationPreference.objects.filter(user=buyer).exists()


def test_preferences_can_be_changed(buyer_client, buyer):
    body = buyer_client.patch(
        f"{URL}preferences/", {"promotions": True, "chat_messages": False},
        format="json",
    ).json()["data"]

    assert body["promotions"] is True
    assert body["chat_messages"] is False


def test_quiet_hours_cannot_start_and_end_together(buyer_client):
    response = buyer_client.patch(
        f"{URL}preferences/",
        {
            "quiet_hours_enabled": True,
            "quiet_hours_start": "22:00",
            "quiet_hours_end": "22:00",
        },
        format="json",
    )
    assert response.status_code == 400


def test_muting_a_category_stops_the_notification_being_written(buyer):
    services.update_preferences(buyer, review_activity=False)

    result = services.notify(
        buyer, NotificationType.REVIEW_REPLIED, title="Reply", body="..."
    )

    assert result is None
    assert Notification.objects.filter(recipient=buyer).count() == 0


def test_a_critical_notification_ignores_every_mute(buyer):
    """
    Somebody who muted everything still has to learn that a paid booking was
    cancelled. This is the one rule the preference table does not govern.
    """
    services.update_preferences(
        buyer, booking_updates=False, push_enabled=False, promotions=False
    )

    result = services.notify(
        buyer,
        NotificationType.BOOKING_CANCELLED,
        title="Your shoot was cancelled",
        body="The photographer had to cancel.",
    )

    assert result is not None


def test_muting_bookings_still_silences_a_reminder(buyer):
    services.update_preferences(buyer, booking_updates=False)

    assert (
        services.notify(
            buyer, NotificationType.BOOKING_REMINDER, title="Tomorrow", body="..."
        )
        is None
    )


# ═══════════════════════════════════════════════════════════════════════════
# QUIET HOURS
# ═══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize(
    "now,expected",
    [
        (time(23, 0), True),   # inside, after midnight boundary start
        (time(2, 0), True),    # inside, past midnight
        (time(7, 59), True),   # inside, just before the end
        (time(8, 0), False),   # the end is exclusive
        (time(12, 0), False),  # the middle of the day
        (time(21, 59), False), # just before the start
    ],
)
def test_quiet_hours_span_midnight(buyer, now, expected):
    """
    22:00 → 08:00 is the default window and it crosses midnight.

    A naive `start <= now <= end` returns False for every hour of the night,
    which is precisely the period the feature exists for.
    """
    prefs = services.update_preferences(
        buyer,
        quiet_hours_enabled=True,
        quiet_hours_start=time(22, 0),
        quiet_hours_end=time(8, 0),
    )
    stamp = timezone.localtime().replace(hour=now.hour, minute=now.minute)

    assert services.in_quiet_hours(prefs, stamp) is expected


def test_quiet_hours_off_is_never_quiet(buyer):
    prefs = services.update_preferences(buyer, quiet_hours_enabled=False)

    assert services.in_quiet_hours(prefs) is False


def test_push_is_skipped_during_quiet_hours_but_the_record_survives(buyer):
    """The in-app row is written either way — only the buzz is suppressed."""
    from apps.notifications.models import NotificationDelivery
    from apps.notifications.tasks import send_push_notification

    services.update_preferences(
        buyer,
        quiet_hours_enabled=True,
        quiet_hours_start=(timezone.localtime() - timedelta(hours=1)).time(),
        quiet_hours_end=(timezone.localtime() + timedelta(hours=1)).time(),
    )
    PushToken.objects.create(user=buyer, token="tok-1", platform="ANDROID")
    notification = make(buyer)

    result = send_push_notification(notification.pk)

    assert result == {"skipped": "quiet hours"}
    assert Notification.objects.filter(pk=notification.pk).exists()
    assert (
        NotificationDelivery.objects.get(
            notification=notification, channel="PUSH"
        ).status
        == "SKIPPED"
    )


# ═══════════════════════════════════════════════════════════════════════════
# DEVICES
# ═══════════════════════════════════════════════════════════════════════════
def test_registering_the_same_token_twice_is_not_an_error(buyer_client, buyer):
    """The app calls this on every launch — a repeat must be a no-op."""
    body = {"token": "abc123", "platform": "ANDROID", "device_id": "pixel-7"}

    first = buyer_client.post(f"{URL}devices/", body, format="json")
    second = buyer_client.post(f"{URL}devices/", body, format="json")

    assert first.status_code == 201
    assert second.status_code == 200
    assert PushToken.objects.filter(user=buyer).count() == 1


def test_a_rotated_token_deactivates_the_old_one_for_that_device(buyer_client, buyer):
    buyer_client.post(
        f"{URL}devices/",
        {"token": "old", "platform": "IOS", "device_id": "iphone-15"},
        format="json",
    )
    buyer_client.post(
        f"{URL}devices/",
        {"token": "new", "platform": "IOS", "device_id": "iphone-15"},
        format="json",
    )

    assert PushToken.objects.get(user=buyer, token="old").is_active is False
    assert PushToken.objects.get(user=buyer, token="new").is_active is True


def test_logout_deactivates_rather_than_deletes(buyer_client, buyer):
    buyer_client.post(
        f"{URL}devices/", {"token": "abc", "platform": "WEB"}, format="json"
    )

    buyer_client.post(f"{URL}devices/remove/", {"token": "abc"}, format="json")

    token = PushToken.objects.get(user=buyer, token="abc")
    assert token.is_active is False


def test_devices_lists_only_active_ones(buyer_client, buyer):
    PushToken.objects.create(user=buyer, token="live", platform="IOS")
    PushToken.objects.create(
        user=buyer, token="dead", platform="IOS", is_active=False
    )

    rows = buyer_client.get(f"{URL}devices/").json()["data"]

    assert [row["token"] for row in rows] == ["live"]


# ═══════════════════════════════════════════════════════════════════════════
# RETENTION
# ═══════════════════════════════════════════════════════════════════════════
def test_purge_keeps_unread_three_times_longer(buyer):
    from apps.notifications.tasks import (
        RETAIN_READ_DAYS,
        RETAIN_UNREAD_DAYS,
        purge_old_notifications,
    )

    old_read = make(buyer, title="old read")
    old_unread = make(buyer, title="old unread")
    ancient_unread = make(buyer, title="ancient unread")
    services.mark_read(buyer, [old_read.pk])

    # Pinned as INTERVALS from now, not as fixed dates.
    Notification.objects.filter(pk=old_read.pk).update(
        created_at=timezone.now() - timedelta(days=RETAIN_READ_DAYS + 1)
    )
    Notification.objects.filter(pk=old_unread.pk).update(
        created_at=timezone.now() - timedelta(days=RETAIN_READ_DAYS + 1)
    )
    Notification.objects.filter(pk=ancient_unread.pk).update(
        created_at=timezone.now() - timedelta(days=RETAIN_UNREAD_DAYS + 1)
    )

    purge_old_notifications()
    survivors = set(
        Notification.objects.filter(recipient=buyer).values_list("title", flat=True)
    )

    assert survivors == {"old unread"}


# ═══════════════════════════════════════════════════════════════════════════
# SELECTORS
# ═══════════════════════════════════════════════════════════════════════════
def test_get_notification_is_scoped(buyer, other_buyer):
    notification = make(buyer)

    assert selectors.get_notification(buyer, notification.pk) is not None
    assert selectors.get_notification(other_buyer, notification.pk) is None
