"""
Notification serializers.

THE DEEP LINK IS DATA, NOT PROSE
--------------------------------
`action_screen` + `action_id` are sent as a structured pair so the app can route
to `BookingDetail(42)`. The alternative — parsing meaning out of the title — is
how a notification list ends up navigating to the wrong screen after a copy
edit.
"""

from rest_framework import serializers

from apps.notifications.models import (
    Notification,
    NotificationPreference,
    NotificationType,
    PushToken,
)


class NotificationSerializer(serializers.ModelSerializer):
    actor_name = serializers.SerializerMethodField()
    actor_avatar = serializers.SerializerMethodField()
    category = serializers.SerializerMethodField()

    class Meta:
        model = Notification
        fields = (
            "id", "notification_type", "category", "title", "body", "image_url",
            "action_screen", "action_id", "payload",
            "is_read", "read_at", "actor_name", "actor_avatar", "created_at",
        )

    def get_actor_name(self, obj) -> str | None:
        return obj.actor.full_name if obj.actor_id else None

    def get_actor_avatar(self, obj) -> str | None:
        if not obj.actor_id or not obj.actor.avatar:
            return None
        request = self.context.get("request")
        url = obj.actor.avatar.url
        return request.build_absolute_uri(url) if request else url

    def get_category(self, obj) -> str:
        """
        Which filter chip this belongs to.

        Derived server-side from the same prefix map the queries use, so the
        chip a notification appears under and the chip that filters it can never
        disagree.
        """
        from apps.notifications.selectors import CATEGORY_PREFIXES

        for name, prefixes in CATEGORY_PREFIXES.items():
            if obj.notification_type.startswith(tuple(prefixes)):
                return name
        return "platform"


class BadgeCountSerializer(serializers.Serializer):
    total = serializers.IntegerField()
    bookings = serializers.IntegerField()
    messages = serializers.IntegerField()
    reviews = serializers.IntegerField()
    marketplace = serializers.IntegerField()


class MarkReadSerializer(serializers.Serializer):
    """
    Mark some or all.

    An empty `ids` list means "everything", which is what the "Mark all read"
    button sends. Making the client enumerate 200 ids to clear a badge would
    make the request size depend on how long they had ignored it.
    """

    ids = serializers.ListField(
        child=serializers.IntegerField(), required=False, allow_empty=True
    )


class MarkReadResponseSerializer(serializers.Serializer):
    updated = serializers.IntegerField()
    unread_count = serializers.IntegerField()


class NotificationPreferenceSerializer(serializers.ModelSerializer):
    """
    Channel switches.

    `booking_updates` is writable even though critical booking notifications
    ignore it (see `services.CRITICAL_TYPES`) — muting reminders and reducing
    noise is legitimate; being silently unable to mute anything is not. The
    exceptions are documented in the model, not hidden by making the field
    read-only.
    """

    class Meta:
        model = NotificationPreference
        fields = (
            "push_enabled", "email_enabled", "sms_enabled",
            "booking_updates", "chat_messages", "review_activity",
            "marketplace_activity", "promotions",
            "quiet_hours_enabled", "quiet_hours_start", "quiet_hours_end",
            "updated_at",
        )
        read_only_fields = ("updated_at",)

    def validate(self, attrs):
        start = attrs.get("quiet_hours_start", getattr(self.instance, "quiet_hours_start", None))
        end = attrs.get("quiet_hours_end", getattr(self.instance, "quiet_hours_end", None))
        if attrs.get("quiet_hours_enabled") and start == end:
            raise serializers.ValidationError(
                {"quiet_hours_end": "Quiet hours cannot start and end at the same time."}
            )
        return attrs


class PushTokenSerializer(serializers.ModelSerializer):
    class Meta:
        model = PushToken
        fields = ("id", "token", "platform", "device_id", "is_active", "created_at")
        read_only_fields = ("id", "is_active", "created_at")


class PushTokenRegisterSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=512)
    platform = serializers.ChoiceField(choices=["IOS", "ANDROID", "WEB"])
    device_id = serializers.CharField(max_length=255, required=False, allow_blank=True)


class TestNotificationSerializer(serializers.Serializer):
    """Payload for the developer-only self-notification endpoint."""

    title = serializers.CharField(max_length=160, required=False)
    body = serializers.CharField(max_length=500, required=False)
    notification_type = serializers.ChoiceField(
        choices=NotificationType.choices, required=False
    )
