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

EMAIL_BACKEND = config(
    "EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend"
)

# Execute Celery tasks synchronously in dev so emails send without background worker
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# Show SQL in the console when hunting N+1 queries.
LOGGING["loggers"]["django.db.backends"]["level"] = "INFO"  # noqa: F405

# Disable all throttling in dev so manual testing is never blocked
REST_FRAMEWORK["DEFAULT_THROTTLE_CLASSES"] = ()

# Browsable API is handy in dev but must never ship to production.
REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"] = (  # noqa: F405
    "apps.core.renderers.EnvelopeJSONRenderer",
    "rest_framework.renderers.BrowsableAPIRenderer",
)
