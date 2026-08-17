"""
Chat reads — Module 13.

WHY THE CONVERSATION LIST NEEDS NO SUBQUERY PER ROW
--------------------------------------------------
`Conversation.last_message_text` / `last_message_at` / `message_count` are
denormalised, written by `services._write_message` in the same transaction as
the message. Without them, rendering 20 threads is 20 "latest message" lookups —
the single most common performance bug in a chat list.

WHY MESSAGES PAGE BY `after` / `before` AND NOT BY PAGE NUMBER
-------------------------------------------------------------
New rows are inserted constantly at the end of a thread. Page 2 of a paginated
thread means something different by the time it is fetched, so messages get
shown twice or skipped. `?after=<id>` is what a reconnecting client uses to
replay exactly what it missed; `?before=<id>` is scroll-back.
"""

from django.db.models import Prefetch, Q

from apps.chat.models import Conversation, ConversationParticipant, Message


def conversations_for(user, *, archived: bool = False, unread_only: bool = False):
    """
    Every thread this user is still in, most recent first.

    Threads they have left are excluded — the conversation still exists for the
    other side, which is why leaving sets `left_at` rather than deleting a row.
    """
    qs = (
        Conversation.objects.filter(
            participant_links__user=user, participant_links__left_at__isnull=True
        )
        .filter(is_archived=archived)
        .select_related("last_message_sender", "booking", "booking__service")
        .prefetch_related(
            Prefetch(
                "participant_links",
                queryset=ConversationParticipant.objects.select_related(
                    "user", "user__photographer_profile"
                ),
            )
        )
        .distinct()
    )
    if unread_only:
        qs = qs.filter(
            participant_links__user=user, participant_links__unread_count__gt=0
        )
    # Threads with no messages yet have `last_message_at = NULL`; ordering on
    # created_at as the tiebreaker keeps a freshly opened thread at the top
    # instead of dropping it to the bottom of the list.
    return qs.order_by("-last_message_at", "-created_at")


def get_conversation(user, pk) -> Conversation | None:
    """Scoped fetch: a thread the caller is not in simply does not exist."""
    return (
        Conversation.objects.filter(pk=pk, participant_links__user=user)
        .select_related("booking", "booking__service", "booking__photographer")
        .prefetch_related(
            Prefetch(
                "participant_links",
                queryset=ConversationParticipant.objects.select_related("user"),
            )
        )
        .first()
    )


def messages_in(
    conversation,
    *,
    after: int | None = None,
    before: int | None = None,
    limit: int = 50,
):
    """
    A window of a thread.

    Returned oldest-first so the app can append without reversing, but the
    `before` (scroll-back) window is selected newest-first and flipped — taking
    the OLDEST 50 of everything before an id would hand back the start of the
    conversation instead of the 50 messages just above the current scroll
    position.
    """
    qs = (
        Message.objects.filter(conversation=conversation)
        .select_related("sender")
        .prefetch_related("attachments")
    )
    limit = max(1, min(int(limit), 100))

    if after is not None:
        return qs.filter(pk__gt=after).order_by("pk")[:limit]
    if before is not None:
        rows = list(qs.filter(pk__lt=before).order_by("-pk")[:limit])
        rows.reverse()
        return rows
    rows = list(qs.order_by("-pk")[:limit])
    rows.reverse()
    return rows


def get_message(user, pk) -> Message | None:
    return (
        Message.objects.filter(pk=pk, conversation__participant_links__user=user)
        .select_related("sender", "conversation")
        .first()
    )


def participant_link(conversation, user) -> ConversationParticipant | None:
    return ConversationParticipant.objects.filter(
        conversation=conversation, user=user
    ).first()


def other_participant(conversation, user):
    """
    The person on the other side.

    Reads from the prefetched links when they are available (the list endpoint
    prefetches them), so rendering 20 threads does not cost 20 queries for the
    other party's name.
    """
    for link in conversation.participant_links.all():
        if link.user_id != user.id:
            return link.user
    return None


def unread_count(conversation, user) -> int:
    link = participant_link(conversation, user)
    return link.unread_count if link else 0


def is_online(user_id) -> bool:
    """
    Live presence, from Redis.

    The TTL is the point: a phone that loses signal never sends a disconnect,
    so a database flag would leave them "online" forever. The `Presence` row
    persists `last_seen_at` for the "last seen 2 hours ago" label; this answers
    "right now".
    """
    from django.core.cache import cache

    return bool(cache.get(f"presence:{user_id}"))


def presence_for(user_ids) -> dict[int, bool]:
    """Batched presence lookup — one cache round trip for a whole list screen."""
    from django.core.cache import cache

    keys = {f"presence:{uid}": uid for uid in user_ids}
    found = cache.get_many(list(keys))
    return {uid: f"presence:{uid}" in found for uid in user_ids}


def searchable_contacts(user, term: str = ""):
    """
    Who this user can start a thread with, for the "New message" screen.

    Buyers see approved photographers; photographers see buyers they have a
    booking with. This mirrors `services._assert_may_initiate` exactly — a
    picker offering somebody the server will refuse is worse than a shorter
    list.
    """
    from django.contrib.auth import get_user_model

    from apps.bookings.models import Booking
    from apps.core.constants import UserRole

    User = get_user_model()
    base = User.objects.filter(is_active=True, is_blocked=False)

    if user.role == UserRole.BUYER:
        qs = base.filter(
            role=UserRole.PHOTOGRAPHER, photographer_profile__is_approved=True
        ).select_related("photographer_profile")
    elif user.role == UserRole.PHOTOGRAPHER:
        profile = getattr(user, "photographer_profile", None)
        if profile is None:
            return base.none()
        buyer_ids = Booking.objects.filter(photographer=profile).values_list(
            "buyer_id", flat=True
        )
        qs = base.filter(pk__in=buyer_ids)
    else:
        return base.none()

    if term:
        qs = qs.filter(
            Q(full_name__icontains=term)
            | Q(photographer_profile__business_name__icontains=term)
        )
    return qs.order_by("full_name")[:30]
