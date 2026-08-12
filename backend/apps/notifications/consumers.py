"""
Live notification stream.

Each user joins a private group named after their own id, so a booking
acceptance can be pushed to exactly one person without any filtering on the
client side.
"""

import logging

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

logger = logging.getLogger("snapsphere")


class NotificationConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        self.user = self.scope["user"]
        if not self.user or not self.user.is_authenticated:
            await self.close(code=4001)
            return

        self.group_name = f"notifications_{self.user.id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        # Send the badge count immediately so the bell is correct on first paint.
        await self.send_json(
            {"type": "connected", "unread_count": await self._unread_count()}
        )

    async def disconnect(self, code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive_json(self, content, **kwargs):
        if content.get("type") == "mark_read":
            await self._mark_read(content.get("id"))
            await self.send_json(
                {"type": "unread_count", "count": await self._unread_count()}
            )

    async def notification_message(self, event):
        """Called by notifications.services.push_realtime()."""
        await self.send_json({"type": "notification", **event["notification"]})

    @database_sync_to_async
    def _unread_count(self) -> int:
        from apps.notifications.models import Notification

        return Notification.objects.filter(recipient=self.user, is_read=False).count()

    @database_sync_to_async
    def _mark_read(self, notification_id):
        from django.utils import timezone

        from apps.notifications.models import Notification

        qs = Notification.objects.filter(recipient=self.user, is_read=False)
        if notification_id:
            qs = qs.filter(pk=notification_id)
        qs.update(is_read=True, read_at=timezone.now())
