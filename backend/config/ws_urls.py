"""WebSocket URL routing (mirrors config/urls.py for the WS protocol)."""

from django.urls import path

from apps.chat.consumers import ChatConsumer, PresenceConsumer
from apps.notifications.consumers import NotificationConsumer

websocket_urlpatterns = [
    path("ws/chat/<int:conversation_id>/", ChatConsumer.as_asgi()),
    path("ws/presence/", PresenceConsumer.as_asgi()),
    path("ws/notifications/", NotificationConsumer.as_asgi()),
]
