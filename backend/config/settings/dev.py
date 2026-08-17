"""Development settings — verbose, permissive, no external services required."""

from .base import *  # noqa: F401,F403

DEBUG = True
ALLOWED_HOSTS = ["*"]

# ═══════════════════════════════════════════════════════════════════════════
# CORS — wide open, dev only
#
# Any origin, so Expo Go on a phone, `expo start --web` on :8081 and a browser
# on the LAN IP all work without listing each one. django-cors-headers echoes
# the request's Origin rather than sending `*` because CORS_ALLOW_CREDENTIALS is
# on, which is what makes credentialled requests legal.
#
# `ALLOWED_HOSTS = ["*"]` also satisfies channels' AllowedHostsOriginValidator,
# so the chat / notification / presence WebSockets accept any origin too.
# ═══════════════════════════════════════════════════════════════════════════
CORS_ALLOW_ALL_ORIGINS = True

# Required by Django 4+ for any non-localhost origin that POSTs a form — which
# in practice means the browsable API or /django-admin/ opened on this machine's
# LAN IP from a phone or another laptop. The mobile app itself never needs it:
# it authenticates with a Bearer token, and CSRF only applies to cookie auth.
#
# The IP is DERIVED rather than listed, because it changes with the network and a
# stale hard-coded entry fails in a way ("CSRF verification failed") that reads
# as a code problem rather than a config one. Django does not wildcard IP octets,
# so a pattern is not an option.
CSRF_TRUSTED_ORIGINS = [
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "http://localhost:8081",
    "http://localhost:19006",
]


def _lan_origins(port: int = 8000) -> list[str]:
    """This machine's LAN address, the way start.sh reports it."""
    import socket

    try:
        # A UDP socket to a public address never sends a packet, but it makes the
        # OS pick the interface it would route through — which is the address the
        # phone can actually reach.
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.settimeout(0.2)
            probe.connect(("8.8.8.8", 80))
            return [f"http://{probe.getsockname()[0]}:{port}"]
    except OSError:
        # No network is not an error in development.
        return []


CSRF_TRUSTED_ORIGINS += _lan_origins()

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Show SQL in the console when hunting N+1 queries.
LOGGING["loggers"]["django.db.backends"]["level"] = "INFO"  # noqa: F405

# Relax throttling so manual testing isn't blocked.
REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"].update(  # noqa: F405
    {
        "anon": "1000/min",
        "user": "5000/min",
        "login": "100/min",
        "register": "100/hour",
        "otp": "100/hour",
        "booking_create": "1000/hour",
    }
)

# Browsable API is handy in dev but must never ship to production.
REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"] = (  # noqa: F405
    "apps.core.renderers.EnvelopeJSONRenderer",
    "rest_framework.renderers.BrowsableAPIRenderer",
)
