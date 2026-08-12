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

from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402
from channels.security.websocket import AllowedHostsOriginValidator  # noqa: E402

from apps.core.ws_auth import JWTAuthMiddlewareStack  # noqa: E402
from config.ws_urls import websocket_urlpatterns  # noqa: E402

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": AllowedHostsOriginValidator(
            JWTAuthMiddlewareStack(URLRouter(websocket_urlpatterns))
        ),
    }
)
