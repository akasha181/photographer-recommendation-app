"""
Chat serializers.

THE LIST AND THE THREAD ARE DIFFERENT SHAPES ON PURPOSE
------------------------------------------------------
`ConversationSerializer` carries the other party, the preview and this caller's
unread count — enough to draw a row and nothing more. Sending every thread's
messages with the list would make opening the Messages tab download the user's
entire chat history.
"""

from rest_framework import serializers

from apps.chat.models import Conversation, Message, MessageAttachment, MessageType


def _absolute(request, filefield) -> str | None:
    if not filefield:
        return None
    try:
        url = filefield.url
    except (ValueError, NotImplementedError):
        return None
    return request.build_absolute_uri(url) if request else url


class ChatUserSerializer(serializers.Serializer):
    """The other side of a thread, as the header renders it."""

    id = serializers.IntegerField()
    full_name = serializers.CharField()
    role = serializers.CharField()
    avatar_url = serializers.SerializerMethodField()
    business_name = serializers.SerializerMethodField()
    is_online = serializers.SerializerMethodField()
    last_seen_at = serializers.SerializerMethodField()

    def get_avatar_url(self, obj) -> str | None:
        return _absolute(self.context.get("request"), obj.avatar)

    def get_business_name(self, obj) -> str | None:
        profile = getattr(obj, "photographer_profile", None)
        return profile.display_name if profile else None

    def get_is_online(self, obj) -> bool:
        """
        Reads a presence map the view loads once per response.

        Falling back to a per-user cache hit would be one Redis round trip per
        row; `presence_for()` batches the whole list into one.
        """
        presence = self.context.get("presence") or {}
        return bool(presence.get(obj.id))

    def get_last_seen_at(self, obj):
        presence = getattr(obj, "presence", None)
        return presence.last_seen_at if presence else None


class MessageAttachmentSerializer(serializers.ModelSerializer):
    file_url = serializers.SerializerMethodField()
    thumbnail_url = serializers.SerializerMethodField()

    class Meta:
        model = MessageAttachment
        fields = (
            "id", "file_name", "file_size_kb", "mime_type",
            "width", "height", "file_url", "thumbnail_url",
        )

    def get_file_url(self, obj) -> str | None:
        return _absolute(self.context.get("request"), obj.file)

    def get_thumbnail_url(self, obj) -> str | None:
        return _absolute(self.context.get("request"), obj.thumbnail or obj.file)


class MessageSerializer(serializers.ModelSerializer):
    sender_name = serializers.SerializerMethodField()
    sender_avatar = serializers.SerializerMethodField()
    is_mine = serializers.SerializerMethodField()
    attachments = MessageAttachmentSerializer(many=True, read_only=True)
    body = serializers.SerializerMethodField()

    class Meta:
        model = Message
        fields = (
            "id", "conversation", "sender", "sender_name", "sender_avatar",
            "is_mine", "message_type", "body", "client_id",
            "is_edited", "is_deleted", "attachments",
            "delivered_at", "read_at", "created_at",
        )

    def get_sender_name(self, obj) -> str:
        return obj.sender.full_name

    def get_sender_avatar(self, obj) -> str | None:
        return _absolute(self.context.get("request"), obj.sender.avatar)

    def get_is_mine(self, obj) -> bool:
        """
        Which side of the thread to draw the bubble on.

        Server-computed rather than left to the client comparing sender ids: the
        app already has the id, but this makes the payload self-describing and
        the WebSocket frame and the REST row identical in shape.
        """
        request = self.context.get("request")
        user = getattr(request, "user", None)
        return bool(user and user.is_authenticated and obj.sender_id == user.id)

    def get_body(self, obj) -> str:
        """A withdrawn message keeps its place in the thread, without its text."""
        return "This message was deleted" if obj.is_deleted else obj.body


class ConversationSerializer(serializers.ModelSerializer):
    other_participant = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()
    is_muted = serializers.SerializerMethodField()
    is_blocked = serializers.SerializerMethodField()
    booking = serializers.SerializerMethodField()

    class Meta:
        model = Conversation
        fields = (
            "id", "other_participant", "last_message_text", "last_message_at",
            "message_count", "unread_count", "is_muted", "is_blocked",
            "is_archived", "booking", "created_at",
        )

    def _link(self, obj):
        user = self.context["request"].user
        for link in obj.participant_links.all():
            if link.user_id == user.id:
                return link
        return None

    def get_other_participant(self, obj) -> dict | None:
        from apps.chat.selectors import other_participant

        other = other_participant(obj, self.context["request"].user)
        if other is None:
            return None
        return ChatUserSerializer(other, context=self.context).data

    def get_unread_count(self, obj) -> int:
        link = self._link(obj)
        return link.unread_count if link else 0

    def get_is_muted(self, obj) -> bool:
        link = self._link(obj)
        return bool(link and link.is_muted)

    def get_is_blocked(self, obj) -> bool:
        link = self._link(obj)
        return bool(link and link.is_blocked)

    def get_booking(self, obj) -> dict | None:
        """
        The booking this thread is about, when there is one.

        Inline rather than a separate fetch: the chat header shows "Wedding —
        25 Sep, Accepted", and a second request for it would leave the header
        blank for as long as it is in flight.
        """
        if obj.booking_id is None:
            return None
        booking = obj.booking
        return {
            "id": booking.pk,
            "status": booking.status,
            "event_date": booking.event_date,
            "service_title": booking.service.title if booking.service_id else "",
        }


class ConversationDetailSerializer(ConversationSerializer):
    """Adds the caller's read watermark so the app can place the divider line."""

    last_read_message_id = serializers.SerializerMethodField()

    class Meta(ConversationSerializer.Meta):
        fields = ConversationSerializer.Meta.fields + ("last_read_message_id",)

    def get_last_read_message_id(self, obj) -> int:
        link = self._link(obj)
        return link.last_read_message_id if link else 0


# ═══════════════════════════════════════════════════════════════════════════
# WRITE
# ═══════════════════════════════════════════════════════════════════════════
class ConversationStartSerializer(serializers.Serializer):
    """
    Open (or find) a thread.

    `user` is the other party's user id, `booking` is optional context. Neither
    grants access: `services.get_or_create_conversation` re-checks who is
    allowed to initiate.
    """

    user = serializers.IntegerField()
    booking = serializers.IntegerField(required=False, allow_null=True)
    message = serializers.CharField(
        max_length=5000, required=False, allow_blank=True,
        help_text="Optional first message, sent in the same request.",
    )

    def validate_user(self, value: int):
        from django.contrib.auth import get_user_model

        User = get_user_model()
        other = User.objects.filter(pk=value).first()
        if other is None:
            raise serializers.ValidationError("User not found.")
        return other

    def validate_booking(self, value):
        if value in (None, ""):
            return None
        from apps.bookings.models import Booking

        user = self.context["request"].user
        booking = Booking.objects.filter(pk=value).first()
        if booking is None:
            raise serializers.ValidationError("Booking not found.")
        if booking.buyer_id != user.id and booking.photographer.user_id != user.id:
            raise serializers.ValidationError("That booking is not yours.")
        return booking


class MessageSendSerializer(serializers.Serializer):
    body = serializers.CharField(max_length=5000, required=False, allow_blank=True)
    message_type = serializers.ChoiceField(
        choices=MessageType.choices, required=False, default=MessageType.TEXT
    )
    client_id = serializers.CharField(max_length=64, required=False, allow_blank=True)
    attachments = serializers.ListField(
        child=serializers.FileField(), required=False, max_length=5
    )


class MessageEditSerializer(serializers.Serializer):
    body = serializers.CharField(max_length=5000)


class ConversationReadSerializer(serializers.Serializer):
    up_to = serializers.IntegerField(
        required=False, allow_null=True,
        help_text="Highest message id the user has seen. Omit for 'everything'.",
    )


class ReportMessageSerializer(serializers.Serializer):
    reason = serializers.ChoiceField(
        choices=[
            "INAPPROPRIATE", "COPYRIGHT", "SPAM", "FAKE",
            "HARASSMENT", "OFF_PLATFORM", "OTHER",
        ]
    )
    detail = serializers.CharField(max_length=1000, required=False, allow_blank=True)


class ContactSerializer(serializers.Serializer):
    """A row in the "New message" picker."""

    id = serializers.IntegerField()
    full_name = serializers.CharField()
    role = serializers.CharField()
    avatar_url = serializers.SerializerMethodField()
    business_name = serializers.SerializerMethodField()

    def get_avatar_url(self, obj) -> str | None:
        return _absolute(self.context.get("request"), obj.avatar)

    def get_business_name(self, obj) -> str | None:
        profile = getattr(obj, "photographer_profile", None)
        return profile.display_name if profile else None
