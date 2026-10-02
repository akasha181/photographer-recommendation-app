"""
WebSocket consumers for chat and presence.

SECURITY NOTE
-------------
The participant check happens BEFORE `self.accept()`. Accepting first and
checking afterwards would briefly join the attacker to the Redis group, and
any message broadcast in that window would reach them. Reject first, always.
"""

import json
import logging
from datetime import timedelta

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger("snapsphere")

# Matches the chat_send throttle scope in settings.
MAX_MESSAGES_PER_MINUTE = 30


class ChatConsumer(AsyncJsonWebsocketConsumer):
    """One connection per open conversation."""

    async def connect(self):
        self.user = self.scope["user"]
        self.conversation_id = self.scope["url_route"]["kwargs"]["conversation_id"]
        self.group_name = f"chat_{self.conversation_id}"

        if not self.user or not self.user.is_authenticated:
            await self.close(code=4001)  # unauthenticated
            return

        if not await self._is_participant():
            await self.close(code=4003)  # forbidden
            return

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        other_user_id = await self._get_other_user_id()
        other_online = await self._check_is_online(other_user_id) if other_user_id else False

        cache.set(f"presence:{self.user.id}", "1", 120)
        await self._persist_user_online(True)

        await self.send_json(
            {
                "type": "connected",
                "conversation_id": self.conversation_id,
                "unread_count": await self._unread_count(),
                "other_user_id": other_user_id,
                "other_online": other_online,
            }
        )
        await self._broadcast_presence(True)

    async def disconnect(self, code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive_json(self, content, **kwargs):
        action = content.get("type")

        if action == "message":
            await self._handle_message(content)
        elif action == "heartbeat":
            cache.set(f"presence:{self.user.id}", "1", 120)
            await self._persist_user_online(True)
            await self.send_json({"type": "heartbeat_ack"})
        elif action == "typing":
            await self.channel_layer.group_send(
                self.group_name,
                {
                    "type": "typing.event",
                    "user_id": self.user.id,
                    "is_typing": bool(content.get("is_typing", True)),
                },
            )
        elif action == "read":
            await self._handle_read(content)
        else:
            await self.send_json({"type": "error", "message": "Unknown action."})

    # ─── Handlers ────────────────────────────────────────────────────────────
    async def _handle_message(self, content):
        body = (content.get("body") or "").strip()
        if not body:
            await self.send_json({"type": "error", "message": "Message is empty."})
            return
        if len(body) > 5000:
            await self.send_json({"type": "error", "message": "Message is too long."})
            return

        # Rate limit here as well as in the REST layer — a WebSocket bypasses
        # DRF throttling entirely.
        key = f"chat_rate:{self.user.id}"
        count = cache.get(key, 0)
        if count >= MAX_MESSAGES_PER_MINUTE:
            await self.send_json(
                {"type": "error", "message": "You're sending messages too quickly."}
            )
            return
        cache.set(key, count + 1, 60)

        message = await self._persist_message(body, content.get("client_id", ""))

        await self.channel_layer.group_send(
            self.group_name,
            {
                "type": "chat.message",
                "message": {
                    "id": message["id"],
                    "conversation_id": self.conversation_id,
                    "sender_id": self.user.id,
                    "sender_name": self.user.full_name,
                    "body": body,
                    "message_type": "TEXT",
                    "client_id": content.get("client_id", ""),
                    "created_at": message["created_at"],
                },
            },
        )

    async def _handle_read(self, content):
        up_to = int(content.get("up_to") or 0)
        await self._mark_read(up_to)
        await self.channel_layer.group_send(
            self.group_name,
            {"type": "read.receipt", "user_id": self.user.id, "up_to": up_to},
        )

    # ─── Group event fan-out (names map to the "type" keys above) ────────────
    async def chat_message(self, event):
        msg = dict(event["message"])
        msg["is_mine"] = bool(
            self.user and self.user.is_authenticated and msg.get("sender_id") == self.user.id
        )
        await self.send_json({"type": "message", **msg})

    async def typing_event(self, event):
        if event["user_id"] != self.user.id:  # don't echo your own typing
            await self.send_json(
                {"type": "typing", "user_id": event["user_id"],
                 "is_typing": event["is_typing"]}
            )

    async def read_receipt(self, event):
        if event["user_id"] != self.user.id:
            await self.send_json(
                {"type": "read", "user_id": event["user_id"], "up_to": event["up_to"]}
            )

    async def message_delete(self, event):
        await self.send_json({"type": "delete", "id": event["message_id"]})

    async def presence_event(self, event):
        if event["user_id"] != self.user.id:
            await self.send_json(
                {"type": "presence", "user_id": event["user_id"],
                 "is_online": event["is_online"]}
            )

    async def _broadcast_presence(self, is_online: bool):
        await self.channel_layer.group_send(
            self.group_name,
            {"type": "presence.event", "user_id": self.user.id, "is_online": is_online},
        )

    # ─── DB access (sync ORM wrapped for the async event loop) ───────────────
    @database_sync_to_async
    def _is_participant(self) -> bool:
        from apps.chat.models import ConversationParticipant

        return ConversationParticipant.objects.filter(
            conversation_id=self.conversation_id, user=self.user, left_at__isnull=True
        ).exists()

    @database_sync_to_async
    def _unread_count(self) -> int:
        from apps.chat.models import ConversationParticipant

        link = ConversationParticipant.objects.filter(
            conversation_id=self.conversation_id, user=self.user
        ).first()
        return link.unread_count if link else 0

    @database_sync_to_async
    def _persist_message(self, body: str, client_id: str) -> dict:
        """
        Write to MySQL FIRST, broadcast second.

        The database is the source of truth; the socket is only transport. A
        client that reconnects after a dropped connection replays from the
        table and never loses a message.
        """
        from django.db import transaction
        from django.db.models import F

        from apps.chat.models import Conversation, ConversationParticipant, Message

        with transaction.atomic():
            message = Message.objects.create(
                conversation_id=self.conversation_id,
                sender=self.user,
                body=body,
                client_id=client_id,
            )
            Conversation.objects.filter(pk=self.conversation_id).update(
                last_message_text=body[:200],
                last_message_at=message.created_at,
                last_message_sender=self.user,
                message_count=F("message_count") + 1,
            )
            ConversationParticipant.objects.filter(
                conversation_id=self.conversation_id
            ).exclude(user=self.user).update(unread_count=F("unread_count") + 1)

        return {"id": message.pk, "created_at": message.created_at.isoformat()}

    @database_sync_to_async
    def _mark_read(self, up_to: int):
        from apps.chat.models import ConversationParticipant

        ConversationParticipant.objects.filter(
            conversation_id=self.conversation_id, user=self.user
        ).update(last_read_message_id=up_to, unread_count=0)

    @database_sync_to_async
    def _get_other_user_id(self) -> int | None:
        from apps.chat.models import ConversationParticipant

        link = (
            ConversationParticipant.objects.filter(conversation_id=self.conversation_id)
            .exclude(user=self.user)
            .first()
        )
        return link.user_id if link else None

    @database_sync_to_async
    def _check_is_online(self, user_id: int | None) -> bool:
        if not user_id:
            return False
        from django.core.cache import cache

        return bool(cache.get(f"presence:{user_id}"))

    @database_sync_to_async
    def _persist_user_online(self, is_online: bool):
        from apps.chat.models import Presence
        from django.utils import timezone

        presence, _ = Presence.objects.get_or_create(user=self.user)
        Presence.objects.filter(pk=presence.pk).update(
            is_online=is_online,
            last_seen_at=timezone.now(),
        )


class PresenceConsumer(AsyncJsonWebsocketConsumer):
    """
    Global online/offline heartbeat.

    Presence lives in Redis with a TTL rather than only in MySQL: if a phone
    loses signal there is no disconnect event, and a database flag would leave
    the user showing "online" forever. A TTL expires on its own.
    """

    TTL_SECONDS = 40

    async def connect(self):
        self.user = self.scope["user"]
        if not self.user or not self.user.is_authenticated:
            await self.close(code=4001)
            return

        await self.channel_layer.group_add("presence", self.channel_name)
        await self.accept()
        await self._set_online(True)

    async def disconnect(self, code):
        if getattr(self, "user", None) and self.user.is_authenticated:
            await self.channel_layer.group_discard("presence", self.channel_name)
            await self._set_online(False)

    async def receive_json(self, content, **kwargs):
        action = content.get("type")
        if action == "heartbeat":
            cache.set(f"presence:{self.user.id}", "1", self.TTL_SECONDS)
            await self._persist_presence(True)
            await self.send_json({"type": "heartbeat_ack"})
        elif action == "offline":
            await self._set_online(False)

    async def presence_event(self, event):
        await self.send_json(
            {"type": "presence", "user_id": event["user_id"],
             "is_online": event["is_online"]}
        )

    async def _set_online(self, is_online: bool):
        if is_online:
            cache.set(f"presence:{self.user.id}", "1", self.TTL_SECONDS)
        else:
            cache.delete(f"presence:{self.user.id}")
        await self._persist_presence(is_online)

        event = {
            "type": "presence.event",
            "user_id": self.user.id,
            "is_online": is_online,
        }
        await self.channel_layer.group_send("presence", event)

        # Broadcast to all active chat thread channels this user belongs to
        # so any open chat screen instantly shows the updated status.
        conversation_ids = await self._get_user_conversation_ids()
        for cid in conversation_ids:
            await self.channel_layer.group_send(f"chat_{cid}", event)

    @database_sync_to_async
    def _get_user_conversation_ids(self) -> list[int]:
        from apps.chat.models import ConversationParticipant

        return list(
            ConversationParticipant.objects.filter(
                user=self.user, left_at__isnull=True
            ).values_list("conversation_id", flat=True)
        )

    @database_sync_to_async
    def _persist_presence(self, is_online: bool):
        from apps.chat.models import Presence
        from django.utils import timezone

        presence, _ = Presence.objects.get_or_create(user=self.user)
        Presence.objects.filter(pk=presence.pk).update(
            is_online=is_online,
            last_seen_at=timezone.now(),
        )
