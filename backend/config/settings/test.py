"""Test settings — fast, isolated, no external services."""

from .base import *  # noqa: F401,F403

DEBUG = False

# Fast password hashing so fixtures don't dominate test runtime.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# Run Celery tasks inline instead of dispatching to a broker.
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# In-memory replacements for Redis-backed services.
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# Throttling off — it only creates flaky tests.
REST_FRAMEWORK["DEFAULT_THROTTLE_CLASSES"] = ()  # noqa: F405
REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"] = {}  # noqa: F405

MEDIA_ROOT = BASE_DIR / "test_media"  # noqa: F405
