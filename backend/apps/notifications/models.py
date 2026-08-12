"""
Notifications.

DELIVERY IS SEPARATE FROM THE NOTIFICATION ITSELF
-------------------------------------------------
A `Notification` row is the fact ("your booking was accepted"). How it reaches
the user — in-app bell, push, email — is a delivery concern with its own
success/failure state. Merging them would mean a failed push marks the
notification itself as failed, and the user would never see it in the app
either.

`NotificationPreference` then lets each user mute channels per event type
without losing the in-app record.
"""

from django.db import models

from apps.core.models import TimeStampedModel


class NotificationType(models.TextChoices):
    # Bookings
    BOOKING_REQUEST = "BOOKING_REQUEST", "New booking request"
    BOOKING_ACCEPTED = "BOOKING_ACCEPTED", "Booking accepted"
    BOOKING_REJECTED = "BOOKING_REJECTED", "Booking rejected"
    BOOKING_CANCELLED = "BOOKING_CANCELLED", "Booking cancelled"
    BOOKING_COMPLETED = "BOOKING_COMPLETED", "Booking completed"
    BOOKING_EXPIRED = "BOOKING_EXPIRED", "Booking expired"
    BOOKING_REMINDER = "BOOKING_REMINDER", "Upcoming shoot reminder"
    # Marketplace
    PRODUCT_PURCHASED = "PRODUCT_PURCHASED", "Product purchased"
    PRODUCT_SOLD = "PRODUCT_SOLD", "Your product sold"
    PRODUCT_APPROVED = "PRODUCT_APPROVED", "Product approved"
    PRODUCT_REJECTED = "PRODUCT_REJECTED", "Product rejected"
    # Reviews
    REVIEW_RECEIVED = "REVIEW_RECEIVED", "New review received"
    REVIEW_REPLIED = "REVIEW_REPLIED", "Photographer replied to your review"
    REVIEW_REMINDER = "REVIEW_REMINDER", "Leave a review"
    # Chat
    NEW_MESSAGE = "NEW_MESSAGE", "New message"
    # Account
    ACCOUNT_APPROVED = "ACCOUNT_APPROVED", "Account approved"
    ACCOUNT_REJECTED = "ACCOUNT_REJECTED", "Account rejected"
    ACCOUNT_BLOCKED = "ACCOUNT_BLOCKED", "Account blocked"
    WALLET_CREDITED = "WALLET_CREDITED", "Wallet credited"
    PAYOUT_SENT = "PAYOUT_SENT", "Payout sent"
    # Platform
    ADMIN_MESSAGE = "ADMIN_MESSAGE", "Message from SnapSphere"
    PROMOTION = "PROMOTION", "Promotion"


class NotificationChannel(models.TextChoices):
    IN_APP = "IN_APP", "In-app"
    PUSH = "PUSH", "Push"
    EMAIL = "EMAIL", "Email"
    SMS = "SMS", "SMS"


class Notification(TimeStampedModel):
    recipient = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="notifications"
    )
    notification_type = models.CharField(
        max_length=32, choices=NotificationType.choices, db_index=True
    )

    title = models.CharField(max_length=160)
    body = models.CharField(max_length=500)
    image_url = models.URLField(blank=True)

    # Deep-link target: the app routes to `{screen: 'BookingDetail', id: 42}`
    # instead of trying to parse meaning out of the notification text.
    action_screen = models.CharField(max_length=60, blank=True)
    action_id = models.CharField(max_length=64, blank=True)
    payload = models.JSONField(default=dict, blank=True)

    is_read = models.BooleanField(default=False, db_index=True)
    read_at = models.DateTimeField(null=True, blank=True)

    actor = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="notifications_triggered",
        help_text="Who caused this — used for the avatar in the bell list.",
    )

    class Meta:
        db_table = "notifications"
        ordering = ("-created_at",)
        indexes = [
            # Powers both the list screen and the unread badge count.
            models.Index(
                fields=["recipient", "is_read", "-created_at"],
                name="idx_notif_inbox",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.notification_type} → {self.recipient_id}"


class NotificationDelivery(TimeStampedModel):
    """One row per attempted channel, so failures are visible and retryable."""

    notification = models.ForeignKey(
        Notification, on_delete=models.CASCADE, related_name="deliveries"
    )
    channel = models.CharField(max_length=16, choices=NotificationChannel.choices)
    status = models.CharField(
        max_length=16,
        choices=[
            ("PENDING", "Pending"), ("SENT", "Sent"),
            ("FAILED", "Failed"), ("SKIPPED", "Skipped by preference"),
        ],
        default="PENDING", db_index=True,
    )
    provider_response = models.TextField(blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "notification_deliveries"
        constraints = [
            models.UniqueConstraint(
                fields=["notification", "channel"], name="uniq_delivery_per_channel"
            )
        ]


class NotificationPreference(TimeStampedModel):
    """
    Per-user, per-type channel switches.

    Booking-critical notifications ignore these settings — a photographer who
    muted everything must still learn that a paid booking was cancelled.
    """

    user = models.OneToOneField(
        "accounts.User", on_delete=models.CASCADE, related_name="notification_preference"
    )

    push_enabled = models.BooleanField(default=True)
    email_enabled = models.BooleanField(default=True)
    sms_enabled = models.BooleanField(default=False)

    booking_updates = models.BooleanField(default=True)
    chat_messages = models.BooleanField(default=True)
    review_activity = models.BooleanField(default=True)
    marketplace_activity = models.BooleanField(default=True)
    promotions = models.BooleanField(default=False)

    quiet_hours_enabled = models.BooleanField(default=False)
    quiet_hours_start = models.TimeField(default="22:00")
    quiet_hours_end = models.TimeField(default="08:00")

    class Meta:
        db_table = "notification_preferences"

    def __str__(self) -> str:
        return f"Preferences for {self.user_id}"


class PushToken(TimeStampedModel):
    """FCM/APNs token, one per device install."""

    user = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="push_tokens"
    )
    token = models.CharField(max_length=512, db_index=True)
    platform = models.CharField(
        max_length=16, choices=[("IOS", "iOS"), ("ANDROID", "Android"), ("WEB", "Web")]
    )
    device_id = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
    failure_count = models.PositiveSmallIntegerField(
        default=0, help_text="Deactivated after repeated provider rejections."
    )

    class Meta:
        db_table = "push_tokens"
        constraints = [
            models.UniqueConstraint(fields=["user", "token"], name="uniq_push_token")
        ]


class Broadcast(TimeStampedModel):
    """An admin announcement fanned out to a filtered audience."""

    title = models.CharField(max_length=160)
    body = models.TextField(max_length=1000)
    audience = models.CharField(
        max_length=20,
        choices=[
            ("ALL", "Everyone"), ("BUYERS", "Buyers only"),
            ("PHOTOGRAPHERS", "Photographers only"), ("CITY", "Specific city"),
        ],
        default="ALL",
    )
    city_filter = models.CharField(max_length=80, blank=True)
    send_push = models.BooleanField(default=True)
    send_email = models.BooleanField(default=False)

    created_by = models.ForeignKey(
        "accounts.User", null=True, on_delete=models.SET_NULL,
        related_name="broadcasts_created",
    )
    scheduled_for = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    recipient_count = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "broadcasts"
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return self.title
