"""
Chat writes — Module 13.

MYSQL IS THE SOURCE OF TRUTH; THE SOCKET IS TRANSPORT
----------------------------------------------------
`send_message` writes the row, updates both participants' counters and only then
broadcasts. The WebSocket consumer calls the same path. A phone that switches
from Wi-Fi to mobile data mid-send reconnects and replays from
`GET /chat/conversations/{id}/messages/?after=<last_id>` — nothing is lost,
because nothing ever lived only in the socket.

WHO MAY OPEN A CONVERSATION
---------------------------
A buyer may message any listed photographer; a photographer may only reply
inside a thread that already exists. That asymmetry is the whole anti-spam
design: 200 photographers cold-messaging every buyer who viewed their profile is
exactly what a marketplace chat becomes without it.

BLOCKING IS ONE-SIDED AND SILENT
--------------------------------
`ConversationParticipant.is_blocked` means "this participant blocked the other
one". The blocker stops receiving messages; the blocked party gets a normal
success response. Telling them they were blocked is what makes people create a
second account.
"""

import logging

from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone

from apps.chat.models import (
    Conversation,
    ConversationParticipant,
    Message,
    MessageType,
)
from apps.core.exceptions import BusinessRuleViolation, ConflictError

logger = logging.getLogger("snapsphere")

#: Matches the `chat_send` throttle scope and the WebSocket consumer's limit.
MAX_MESSAGES_PER_MINUTE = 30


# ═══════════════════════════════════════════════════════════════════════════
# CONVERSATIONS
# ═══════════════════════════════════════════════════════════════════════════
@transaction.atomic
def get_or_create_conversation(initiator, other_user, *, booking=None) -> tuple:
    """
    Find the thread between these two, or open it. Returns (conversation, created).

    IDEMPOTENT BY DESIGN. Two taps on "Message" must not produce two threads —
    a duplicate conversation splits the history in half and neither side can
    tell which one the other is reading. There is no unique constraint that can
    express "exactly one thread per unordered pair" across a through-table, so
    the lookup below is the mechanism and it runs inside the transaction.
    """
    if other_user.id == initiator.id:
        raise BusinessRuleViolation("You cannot message yourself.")

    _assert_may_initiate(initiator, other_user)

    existing = (
        Conversation.objects.filter(participant_links__user=initiator)
        .filter(participant_links__user=other_user)
        .order_by("pk")
        .first()
    )
    if existing is not None:
        # Attach the booking if the thread predates it — buyers message before
        # booking, and the chat screen shows the booking status inline once
        # there is one.
        if booking is not None and existing.booking_id is None:
            Conversation.objects.filter(pk=existing.pk).update(booking=booking)
            existing.booking = booking
        # Re-opening a thread you had left rejoins you rather than starting over.
        ConversationParticipant.objects.filter(
            conversation=existing, user=initiator, left_at__isnull=False
        ).update(left_at=None)
        return existing, False

    conversation = Conversation.objects.create(booking=booking)
    ConversationParticipant.objects.bulk_create(
        [
            ConversationParticipant(conversation=conversation, user=initiator),
            ConversationParticipant(conversation=conversation, user=other_user),
        ]
    )
    logger.info(
        "Conversation opened",
        extra={"conversation_id": conversation.pk, "initiator_id": initiator.id},
    )
    return conversation, True


def _assert_may_initiate(initiator, other_user) -> None:
    """
    Only a buyer may start a cold thread, and only with a listed photographer.

    A photographer who has a booking with this buyer may also start one — after
    an accepted booking the two are working together, and making the buyer
    speak first would be an obstacle for no benefit.
    """
    from apps.bookings.selectors import has_booking_between
    from apps.core.constants import UserRole

    if other_user.is_blocked or not other_user.is_active:
        raise BusinessRuleViolation("This account is not available.")

    if initiator.role == UserRole.BUYER:
        profile = getattr(other_user, "photographer_profile", None)
        if profile is None:
            raise BusinessRuleViolation("You can only message photographers.")
        if not profile.is_approved:
            raise BusinessRuleViolation(
                "This photographer is not accepting messages yet."
            )
        return

    if initiator.role == UserRole.PHOTOGRAPHER:
        profile = getattr(initiator, "photographer_profile", None)
        if profile is None:
            raise BusinessRuleViolation("Photographer profile not found.")
        if other_user.role == UserRole.BUYER or has_booking_between(other_user, profile):
            return
        raise BusinessRuleViolation("You can message buyers on SnapSphere.")

    raise BusinessRuleViolation("Administrators do not participate in chats.")


@transaction.atomic
def set_muted(conversation, user, *, muted: bool) -> ConversationParticipant:
    link = _link(conversation, user)
    link.is_muted = muted
    link.save(update_fields=["is_muted", "updated_at"])
    return link


@transaction.atomic
def set_blocked(conversation, user, *, blocked: bool) -> ConversationParticipant:
    link = _link(conversation, user)
    link.is_blocked = blocked
    link.save(update_fields=["is_blocked", "updated_at"])
    logger.info(
        "Conversation block toggled",
        extra={"conversation_id": conversation.pk, "user_id": user.id, "blocked": blocked},
    )
    return link


@transaction.atomic
def set_archived(conversation, user, *, archived: bool) -> Conversation:
    """
    Archiving is per-thread, not per-participant.

    A limitation stated rather than hidden: `Conversation.is_archived` is a
    single column, so archiving hides the thread for both sides. It is used by
    admin cleanup and by a mutual "we're done here", not offered as a per-user
    tidy-up — which would need a column on the participant link and a migration.
    """
    _link(conversation, user)  # membership check
    conversation.is_archived = archived
    conversation.save(update_fields=["is_archived", "updated_at"])
    return conversation


@transaction.atomic
def leave_conversation(conversation, user) -> ConversationParticipant:
    link = _link(conversation, user)
    link.left_at = timezone.now()
    link.unread_count = 0
    link.save(update_fields=["left_at", "unread_count", "updated_at"])
    return link


def _link(conversation, user) -> ConversationParticipant:
    link = ConversationParticipant.objects.filter(
        conversation=conversation, user=user
    ).first()
    if link is None:
        raise BusinessRuleViolation("You are not a participant in this conversation.")
    return link


# ═══════════════════════════════════════════════════════════════════════════
# MESSAGES
# ═══════════════════════════════════════════════════════════════════════════
def send_message(
    conversation,
    sender,
    *,
    body: str = "",
    message_type: str = MessageType.TEXT,
    client_id: str = "",
    attachments: list | None = None,
) -> Message:
    """
    Persist, then broadcast. Returns the stored message.

    `client_id` is echoed back with the server id so the app can reconcile the
    optimistic bubble it drew instantly with the real row — and, because
    (conversation, client_id) is uniquely constrained, a retry after a dropped
    response returns the SAME message instead of posting it twice.
    """
    message = _write_message(
        conversation,
        sender,
        body=body,
        message_type=message_type,
        client_id=client_id,
        attachments=attachments or [],
    )
    _broadcast(conversation, message)
    _notify_recipients(conversation, message)
    return message


@transaction.atomic
def _write_message(conversation, sender, *, body, message_type, client_id, attachments):
    link = _link(conversation, sender)
    if link.left_at is not None:
        raise BusinessRuleViolation("You have left this conversation.")

    body = (body or "").strip()
    if not body and message_type == MessageType.TEXT and not attachments:
        raise BusinessRuleViolation("Write something before sending.")

    if client_id:
        # The retry path. Checked before the INSERT so a duplicate is a 200 with
        # the original message rather than a 409 the app has to interpret.
        duplicate = Message.objects.filter(
            conversation=conversation, client_id=client_id
        ).first()
        if duplicate is not None:
            return duplicate

    message = Message.objects.create(
        conversation=conversation,
        sender=sender,
        body=body,
        message_type=message_type,
        client_id=client_id,
    )
    for attachment in attachments:
        _attach(message, attachment)

    Conversation.objects.filter(pk=conversation.pk).update(
        last_message_text=message.preview[:200],
        last_message_at=message.created_at,
        last_message_sender=sender,
        message_count=F("message_count") + 1,
    )
    # Only participants who have NOT blocked the sender get an unread bump.
    # A blocker's badge must not light up for a thread they have muted shut.
    ConversationParticipant.objects.filter(
        conversation=conversation, left_at__isnull=True
    ).exclude(user=sender).filter(is_blocked=False).update(
        unread_count=F("unread_count") + 1
    )
    return message


def _attach(message, uploaded):
    """
    Store one attachment.

    Images are re-encoded through `process_image`, which strips EXIF — a photo
    sent in chat carries the same GPS coordinates a portfolio upload does, and
    the privacy requirement does not change because the audience is one person.
    """
    from apps.chat.models import MessageAttachment
    from apps.core.utils import process_image

    is_image = (getattr(uploaded, "content_type", "") or "").startswith("image/")
    row = MessageAttachment(
        message=message,
        file_name=getattr(uploaded, "name", "attachment")[:200],
        file_size_kb=int(getattr(uploaded, "size", 0) / 1024),
        mime_type=getattr(uploaded, "content_type", "") or "",
    )
    if is_image:
        from PIL import Image as PILImage

        uploaded.seek(0)
        with PILImage.open(uploaded) as probe:
            row.width, row.height = probe.size

        uploaded.seek(0)
        processed = process_image(uploaded, size_key="medium")
        row.file.save(processed.name, processed, save=False)

        uploaded.seek(0)
        thumb = process_image(uploaded, size_key="thumb")
        row.thumbnail.save(thumb.name, thumb, save=False)
    else:
        uploaded.seek(0)
        row.file.save(getattr(uploaded, "name", "attachment"), uploaded, save=False)
    row.save()
    return row


@transaction.atomic
def mark_read(conversation, user, *, up_to: int | None = None) -> int:
    """
    Move this participant's read watermark. Returns the new unread count (0).

    A single integer, not a row per message (see models.py): "everything up to
    here is read" answers the unread count with one indexed comparison instead
    of a COUNT over millions of receipt rows.
    """
    link = _link(conversation, user)

    if up_to is None:
        up_to = (
            Message.objects.filter(conversation=conversation)
            .order_by("-id")
            .values_list("id", flat=True)
            .first()
            or link.last_read_message_id
        )

    # Never move the watermark backwards: an out-of-order request from a
    # reconnecting client would otherwise resurrect messages as unread.
    up_to = max(int(up_to), link.last_read_message_id)

    ConversationParticipant.objects.filter(pk=link.pk).update(
        last_read_message_id=up_to, unread_count=0
    )

    # Delivery receipts for the other side's UI. Scoped to messages this user
    # did NOT send, because reading your own message is meaningless.
    Message.objects.filter(
        conversation=conversation, pk__lte=up_to, read_at__isnull=True
    ).exclude(sender=user).update(read_at=timezone.now())

    _broadcast_read(conversation, user, up_to)
    return 0


@transaction.atomic
def delete_message(message, user) -> Message:
    """
    Soft delete — "This message was deleted".

    The row stays because the other party has already read it, and silently
    erasing text from someone else's history is worse than admitting it was
    withdrawn. Also the only honest option when a message is evidence in a
    dispute.
    """
    if message.sender_id != user.id:
        raise BusinessRuleViolation("You can only delete your own messages.")
    if message.is_deleted:
        raise ConflictError("This message is already deleted.")

    message.is_deleted = True
    message.deleted_at = timezone.now()
    message.body = ""
    message.save(update_fields=["is_deleted", "deleted_at", "body", "updated_at"])

    # Keep the conversation preview honest if this was the last message.
    if _is_latest(message):
        Conversation.objects.filter(pk=message.conversation_id).update(
            last_message_text="This message was deleted"
        )
    _broadcast_delete(message)
    return message


@transaction.atomic
def edit_message(message, user, body: str) -> Message:
    if message.sender_id != user.id:
        raise BusinessRuleViolation("You can only edit your own messages.")
    if message.is_deleted:
        raise BusinessRuleViolation("This message was deleted.")

    message.body = body.strip()
    message.is_edited = True
    message.save(update_fields=["body", "is_edited", "updated_at"])

    if _is_latest(message):
        Conversation.objects.filter(pk=message.conversation_id).update(
            last_message_text=message.preview[:200]
        )
    return message


def _is_latest(message) -> bool:
    """
    Whether this is the newest message in its thread.

    Compares ids rather than `message.conversation.last_message_at`. Django
    caches the related object that was passed into `Message.objects.create()`,
    so `message.conversation` can be an in-memory instance whose denormalised
    columns predate the write — the preview would then never be corrected. Same
    stale-instance trap as `user.wallet.balance`.
    """
    return not Message.objects.filter(
        conversation_id=message.conversation_id, pk__gt=message.pk
    ).exists()


def report_message(message, reporter, *, reason: str, detail: str = ""):
    """Feed a chat message into the same moderation queue as everything else."""
    from apps.administration.services import report_content

    if message.sender_id == reporter.id:
        raise BusinessRuleViolation("This is your own message.")

    return report_content(
        reporter=reporter,
        content_type="MESSAGE",
        object_id=message.pk,
        reason=reason,
        detail=detail,
    )


def rate_limited(user) -> bool:
    """
    Cheap per-user send limit, shared with the WebSocket consumer.

    DRF throttling does not apply to a WebSocket frame at all, so the limit has
    to live somewhere both paths reach. The counter is in Redis with a 60-second
    TTL; losing it on a cache restart lets one user send a few extra messages,
    which is the right failure mode for a chat app.
    """
    from django.core.cache import cache

    key = f"chat_rate:{user.id}"
    count = cache.get(key, 0)
    if count >= MAX_MESSAGES_PER_MINUTE:
        return True
    cache.set(key, count + 1, 60)
    return False


# ═══════════════════════════════════════════════════════════════════════════
# FAN-OUT
# ═══════════════════════════════════════════════════════════════════════════
def _broadcast(conversation, message) -> None:
    """
    Push to anyone with the thread open.

    Wrapped and swallowed: the message is already committed, so a Redis outage
    must degrade to "the other phone sees it on next fetch", never to a failed
    send for a message that exists.
    """
    from asgiref.sync import async_to_sync
    from channels.layers import get_channel_layer

    layer = get_channel_layer()
    if layer is None:
        return
    try:
        async_to_sync(layer.group_send)(
            f"chat_{conversation.pk}",
            {
                "type": "chat.message",
                "message": {
                    "id": message.pk,
                    "conversation_id": conversation.pk,
                    "sender_id": message.sender_id,
                    "sender_name": message.sender.full_name,
                    "body": message.body,
                    "message_type": message.message_type,
                    "client_id": message.client_id,
                    "created_at": message.created_at.isoformat(),
                },
            },
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Chat broadcast failed: %s", exc)


def _broadcast_read(conversation, user, up_to: int) -> None:
    from asgiref.sync import async_to_sync
    from channels.layers import get_channel_layer

    layer = get_channel_layer()
    if layer is None:
        return
    try:
        async_to_sync(layer.group_send)(
            f"chat_{conversation.pk}",
            {"type": "read.receipt", "user_id": user.id, "up_to": up_to},
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Read receipt broadcast failed: %s", exc)


def _broadcast_delete(message) -> None:
    from asgiref.sync import async_to_sync
    from channels.layers import get_channel_layer

    layer = get_channel_layer()
    if layer is None:
        return
    try:
        async_to_sync(layer.group_send)(
            f"chat_{message.conversation_id}",
            {"type": "message.delete", "message_id": message.pk},
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Delete broadcast failed: %s", exc)


def _notify_recipients(conversation, message) -> None:
    """
    A bell notification for a message nobody is looking at.

    Muted links are skipped here rather than inside `notify()`: muting THIS
    thread is a different decision from muting chat entirely, and only this
    layer knows about the thread.
    """
    from apps.notifications.models import NotificationType
    from apps.notifications.services import notify

    links = (
        ConversationParticipant.objects.filter(
            conversation=conversation, left_at__isnull=True, is_muted=False,
            is_blocked=False,
        )
        .exclude(user=message.sender)
        .select_related("user")
    )
    for link in links:
        notify(
            link.user,
            NotificationType.NEW_MESSAGE,
            title=f"New message from {message.sender.full_name}",
            body=message.preview[:140],
            action_screen="Chat",
            action_id=str(conversation.pk),
            actor=message.sender,
            payload={"conversation_id": conversation.pk, "message_id": message.pk},
        )


def unread_total(user) -> int:
    """Badge on the Messages tab — one indexed aggregate."""
    from django.db.models import Sum

    total = ConversationParticipant.objects.filter(
        user=user, left_at__isnull=True
    ).filter(~Q(unread_count=0)).aggregate(total=Sum("unread_count"))["total"]
    return total or 0
