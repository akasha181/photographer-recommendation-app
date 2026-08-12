"""Production settings — hardened."""

from decouple import config

from .base import *  # noqa: F401,F403

DEBUG = False

# ─── HTTPS enforcement ───────────────────────────────────────────────────────
SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_HSTS_SECONDS = 31_536_000  # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# ─── Cookies ─────────────────────────────────────────────────────────────────
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Strict"
CSRF_COOKIE_SAMESITE = "Strict"

# ─── Headers ─────────────────────────────────────────────────────────────────
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
X_FRAME_OPTIONS = "DENY"

# ─── No browsable API in production ──────────────────────────────────────────
REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"] = (  # noqa: F405
    "apps.core.renderers.EnvelopeJSONRenderer",
)

# ─── Private downloads ───────────────────────────────────────────────────────
# The deployment in docs/01 §12 puts Nginx in front of gunicorn, so digital
# product files are streamed by Nginx after Django authorises the token.
# Requires the matching `internal` location block — see the deployment notes.
PRIVATE_MEDIA_X_ACCEL = config(  # noqa: F405
    "PRIVATE_MEDIA_X_ACCEL", default=True, cast=bool
)

# ─── S3 media ────────────────────────────────────────────────────────────────
if config("USE_S3", default=False, cast=bool):
    INSTALLED_APPS += ["storages"]  # noqa: F405
    STORAGES = {
        "default": {"BACKEND": "storages.backends.s3boto3.S3Boto3Storage"},
        "staticfiles": {
            "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"
        },
    }
    AWS_ACCESS_KEY_ID = config("AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY = config("AWS_SECRET_ACCESS_KEY")
    AWS_STORAGE_BUCKET_NAME = config("AWS_STORAGE_BUCKET_NAME")
    AWS_S3_REGION_NAME = config("AWS_S3_REGION_NAME", default="eu-west-1")
    AWS_QUERYSTRING_AUTH = True
    AWS_DEFAULT_ACL = None

# ─── Error tracking ──────────────────────────────────────────────────────────
SENTRY_DSN = config("SENTRY_DSN", default="")
if SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.celery import CeleryIntegration
    from sentry_sdk.integrations.django import DjangoIntegration

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[DjangoIntegration(), CeleryIntegration()],
        traces_sample_rate=0.1,
        send_default_pii=False,
    )
