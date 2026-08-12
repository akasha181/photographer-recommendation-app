"""
JWT authentication for WebSocket connections.

Browsers and React Native cannot set an Authorization header on a WebSocket
handshake, so the token travels as a query parameter:

    wss://api.snapsphere.pk/ws/chat/42/?token=<access_jwt>

That is acceptable because the connection is TLS-encrypted end to end (the
query string is inside the encrypted payload, not visible on the wire) and the
access token lives only 30 minutes. We still avoid logging full WS URLs.
"""

from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from channels.sessions import CookieMiddleware, SessionMiddleware
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser


@database_sync_to_async
def _get_user(token_key: str):
    from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
    from rest_framework_simplejwt.tokens import AccessToken

    User = get_user_model()
    try:
        token = AccessToken(token_key)
        user = User.objects.get(pk=token["user_id"])
    except (InvalidToken, TokenError, KeyError, User.DoesNotExist):
        return AnonymousUser()

    # A token issued before a ban or password change must stop working now,
    # not in 30 minutes.
    if user.is_blocked or not user.is_active:
        return AnonymousUser()
    if token.get("token_version") != user.token_version:
        return AnonymousUser()
    return user


class JWTAuthMiddleware(BaseMiddleware):
    async def __call__(self, scope, receive, send):
        query = parse_qs(scope.get("query_string", b"").decode())
        token = (query.get("token") or [None])[0]
        scope["user"] = await _get_user(token) if token else AnonymousUser()
        return await super().__call__(scope, receive, send)


def JWTAuthMiddlewareStack(inner):  # noqa: N802 — mirrors Channels' naming
    return CookieMiddleware(SessionMiddleware(JWTAuthMiddleware(inner)))
