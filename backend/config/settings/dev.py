"""Development settings — verbose, permissive, no external services required."""

from .base import *  # noqa: F401,F403

DEBUG = True
ALLOWED_HOSTS = ["*"]

# Allow any origin while developing against Expo Go on a phone.
CORS_ALLOW_ALL_ORIGINS = True

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
