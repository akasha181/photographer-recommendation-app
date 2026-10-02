"""
ASGI entry point — routes HTTP *and* WebSocket traffic.

HTTP  →  the normal Django/DRF stack
WS    →  JWT-authenticated Channels consumers (chat, notifications, presence)
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

# The HTTP application must be created before importing anything that touches
# the app registry (consumers import models).
django_asgi_app = get_asgi_application()

from django.conf import settings  # noqa: E402
from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402
from channels.security.websocket import AllowedHostsOriginValidator  # noqa: E402

from apps.core.ws_auth import JWTAuthMiddlewareStack  # noqa: E402
from config.ws_urls import websocket_urlpatterns  # noqa: E402


class MobilePermissiveOriginValidator:
    """
    Channels AllowedHostsOriginValidator rejects any WebSocket connection that lacks
    an Origin header (parsed_origin is None). Native mobile apps (React Native / iOS / Android)
    do not send an Origin header. This validator allows native mobile clients and dev connections
    while enforcing AllowedHostsOriginValidator when a browser Origin header is present.
    """
    def __init__(self, inner):
        self.inner = inner
        self.validator = AllowedHostsOriginValidator(inner)

    async def __call__(self, scope, receive, send):
        if scope.get("type") == "websocket":
            headers = dict(scope.get("headers", []))
            origin = headers.get(b"origin")
            if not origin or settings.DEBUG or "*" in getattr(settings, "ALLOWED_HOSTS", []):
                return await self.inner(scope, receive, send)
            return await self.validator(scope, receive, send)
        return await self.inner(scope, receive, send)


application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": MobilePermissiveOriginValidator(
            JWTAuthMiddlewareStack(URLRouter(websocket_urlpatterns))
        ),
    }
)
