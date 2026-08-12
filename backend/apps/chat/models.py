"""
Chat.

WHY MYSQL IS THE SOURCE OF TRUTH, NOT THE WEBSOCKET
---------------------------------------------------
The WebSocket is transport only. Every message is written to `messages` before
it is broadcast. If the socket drops mid-send, the recipient reconnects and
calls GET /chat/conversations/{id}/messages/?after=<last_id> and loses nothing.

Designing it the other way round — trusting the socket — is how chat apps lose
messages when a phone switches from Wi-Fi to mobile data.

READ RECEIPTS USE A WATERMARK, NOT A ROW PER MESSAGE
----------------------------------------------------
`ConversationParticipant.last_read_message_id` is a single integer meaning
"I have read everything up to here". The alternative — one MessageRead row per
message per user — would generate millions of rows and make the unread count a
COUNT() over them. The watermark makes unread count a single indexed range
query.
"""

from django.db import models
from django.utils import timezone

from apps.core.models import TimeStampedModel


class Conversation(TimeStampedModel):
    """
    A 1-to-1 thread between a buyer and a photographer.

    `booking` is optional: buyers often message before booking. When a booking
    exists it is linked so the chat screen can show its status inline.
    """

    participants = models.ManyToManyField(
        "accounts.User", through="ConversationParticipant",
        related_name="conversations",
    )
    booking = models.ForeignKey(
        "bookings.Booking", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="conversations",
    )

    # Denormalised so the conversation list renders without a subquery per row.
    last_message_text = models.CharField(max_length=200, blank=True)
    last_message_at = models.DateTimeField(null=True, blank=True, db_index=True)
    last_message_sender = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="+",
    )
    message_count = models.PositiveIntegerField(default=0)

    is_archived = models.BooleanField(default=False)

    class Meta:
        db_table = "conversations"
        ordering = ("-last_message_at",)
        indexes = [
            models.Index(fields=["-last_message_at"], name="idx_conv_recent"),
        ]

    def __str__(self) -> str:
        return f"Conversation #{self.pk}"


class ConversationParticipant(TimeStampedModel):
    """Through-model holding each side's private view of the thread."""

    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name="participant_links"
    )
    user = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="conversation_links"
    )

    last_read_message_id = models.BigIntegerField(
        default=0, help_text="Read watermark — everything up to here is read."
    )
    unread_count = models.PositiveIntegerField(default=0)

    is_muted = models.BooleanField(default=False)
    is_blocked = models.BooleanField(
        default=False, help_text="This participant blocked the other one."
    )
    joined_at = models.DateTimeField(default=timezone.now)
    left_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "conversation_participants"
        constraints = [
            models.UniqueConstraint(
                fields=["conversation", "user"], name="uniq_participant_per_conv"
            )
        ]
        indexes = [
            models.Index(fields=["user", "-unread_count"], name="idx_participant_unread"),
        ]


class MessageType(models.TextChoices):
    TEXT = "TEXT", "Text"
    IMAGE = "IMAGE", "Image"
    FILE = "FILE", "File"
    BOOKING_REF = "BOOKING_REF", "Booking reference card"
    SYSTEM = "SYSTEM", "System message"


class Message(TimeStampedModel):
    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name="messages"
    )
    sender = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="sent_messages"
    )

    message_type = models.CharField(
        max_length=16, choices=MessageType.choices, default=MessageType.TEXT
    )
    body = models.TextField(max_length=5000, blank=True)

    # Echoed back with the server id so the client can reconcile the optimistic
    # bubble it drew instantly with the real, persisted message.
    client_id = models.CharField(max_length=64, blank=True, db_index=True)

    is_edited = models.BooleanField(default=False)
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)

    delivered_at = models.DateTimeField(null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "messages"
        ordering = ("created_at",)
        indexes = [
            # The exact access pattern of "load this thread, newest first".
            models.Index(
                fields=["conversation", "-created_at"], name="idx_message_thread"
            ),
            models.Index(fields=["sender", "-created_at"], name="idx_message_by_sender"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["conversation", "client_id"],
                condition=~models.Q(client_id=""),
                name="uniq_message_client_id",
            ),
        ]

    def __str__(self) -> str:
        return f"Msg #{self.pk} in conv {self.conversation_id}"

    @property
    def preview(self) -> str:
        if self.message_type == MessageType.IMAGE:
            return "📷 Photo"
        if self.message_type == MessageType.FILE:
            return "📎 File"
        return self.body[:100]


class MessageAttachment(TimeStampedModel):
    message = models.ForeignKey(
        Message, on_delete=models.CASCADE, related_name="attachments"
    )
    file = models.FileField(upload_to="chat/%Y/%m/")
    thumbnail = models.ImageField(upload_to="chat/thumbs/%Y/%m/", null=True, blank=True)
    file_name = models.CharField(max_length=200)
    file_size_kb = models.PositiveIntegerField(default=0)
    mime_type = models.CharField(max_length=100, blank=True)
    width = models.PositiveSmallIntegerField(default=0)
    height = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = "message_attachments"


class Presence(TimeStampedModel):
    """
    Online status.

    Redis holds the live signal (with a TTL, so a crashed client goes offline
    automatically). This table persists `last_seen_at` so the UI can still say
    "last seen 2 hours ago" after a Redis restart.
    """

    user = models.OneToOneField(
        "accounts.User", on_delete=models.CASCADE, related_name="presence"
    )
    is_online = models.BooleanField(default=False, db_index=True)
    last_seen_at = models.DateTimeField(default=timezone.now, db_index=True)
    active_connections = models.PositiveSmallIntegerField(
        default=0, help_text="A user may have the app open on several devices."
    )

    class Meta:
        db_table = "user_presence"
        verbose_name_plural = "User presence"

    def __str__(self) -> str:
        return f"{self.user_id}: {'online' if self.is_online else 'offline'}"
