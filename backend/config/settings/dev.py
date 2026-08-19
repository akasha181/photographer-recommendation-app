"""Development settings — verbose, permissive, no external services required."""

from .base import *  # noqa: F401,F403

DEBUG = True
ALLOWED_HOSTS = ["*"]

# Allow any origin while developing against Expo Go on a phone.
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
