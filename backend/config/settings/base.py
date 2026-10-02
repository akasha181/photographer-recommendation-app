"""
SnapSphere — shared Django settings.

Environment-specific modules (dev.py / prod.py / test.py) import * from here
and override only what differs. Never import this module directly at runtime;
set DJANGO_SETTINGS_MODULE to one of the concrete environments instead.
"""

import sys
from datetime import timedelta
from pathlib import Path

from decouple import Csv, config

# ═══════════════════════════════════════════════════════════════════════════
# PATHS
# ═══════════════════════════════════════════════════════════════════════════
# base.py lives at  <root>/backend/config/settings/base.py
BASE_DIR = Path(__file__).resolve().parents[2]   # -> <root>/backend
ROOT_DIR = BASE_DIR.parent                       # -> <root>

APPS_DIR = BASE_DIR / "apps"
ML_DIR = ROOT_DIR / "ml"

# The trained ranker is pickled as an ml.pipelines.scorer.SnapSphereRanker
# instance. joblib.load() re-imports that class by its module path, so the
# repository root must be importable from Django — otherwise loading the
# artifact fails with ModuleNotFoundError: No module named 'ml'.
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# ═══════════════════════════════════════════════════════════════════════════
# SECURITY
# ═══════════════════════════════════════════════════════════════════════════
SECRET_KEY = config("SECRET_KEY", default="insecure-dev-key-change-me")
DEBUG = config("DEBUG", default=False, cast=bool)
ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="localhost,127.0.0.1", cast=Csv())

# Argon2 is the current OWASP recommendation for password storage.
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.BCryptSHA256PasswordHasher",
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 8},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ═══════════════════════════════════════════════════════════════════════════
# APPLICATIONS
# ═══════════════════════════════════════════════════════════════════════════
DJANGO_APPS = [
    "daphne",  # must precede staticfiles so its runserver override wins
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "django_filters",
    "drf_spectacular",
    "channels",
    "django_celery_beat",
]

# Order matters: an app may only depend on apps listed above it.
LOCAL_APPS = [
    "apps.core",
    "apps.accounts",
    "apps.profiles",
    "apps.catalog",
    "apps.portfolio",
    "apps.availability",
    "apps.bookings",
    "apps.marketplace",
    "apps.reviews",
    "apps.wishlist",
    "apps.chat",
    "apps.notifications",
    "apps.recommendations",
    "apps.analytics",
    "apps.administration",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# ═══════════════════════════════════════════════════════════════════════════
# MIDDLEWARE  (order is significant — see docs/01-system-architecture.md §3)
# ═══════════════════════════════════════════════════════════════════════════
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.core.middleware.RequestIDMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# ═══════════════════════════════════════════════════════════════════════════
# DATABASE
# ═══════════════════════════════════════════════════════════════════════════
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": config("DB_NAME", default="snapsphere"),
        "USER": config("DB_USER", default="root"),
        "PASSWORD": config("DB_PASSWORD", default=""),
        "HOST": config("DB_HOST", default="127.0.0.1"),
        "PORT": config("DB_PORT", default="3306"),
        "OPTIONS": {
            "charset": "utf8mb4",
            # STRICT_TRANS_TABLES turns silent truncation into a loud error.
            "init_command": "SET sql_mode='STRICT_TRANS_TABLES'",
        },
        "CONN_MAX_AGE": 60,
        "TEST": {"CHARSET": "utf8mb4", "COLLATION": "utf8mb4_unicode_ci"},
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "accounts.User"

# We deliberately do NOT wrap every request in a transaction. Atomicity is
# declared explicitly inside service functions where it is actually needed.
ATOMIC_REQUESTS = False

# ═══════════════════════════════════════════════════════════════════════════
# INTERNATIONALISATION
# ═══════════════════════════════════════════════════════════════════════════
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"          # store UTC; clients render Asia/Karachi
USE_I18N = True
USE_TZ = True

DISPLAY_TIME_ZONE = "Asia/Karachi"
CURRENCY_CODE = "PKR"
CURRENCY_SYMBOL = "Rs"

# ═══════════════════════════════════════════════════════════════════════════
# STATIC & MEDIA
# ═══════════════════════════════════════════════════════════════════════════
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"] if (BASE_DIR / "static").exists() else []

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# Digital-product files live OUTSIDE MEDIA_ROOT so they can never be reached
# by guessing a URL. They are served only through a signed download token.
PRIVATE_MEDIA_ROOT = BASE_DIR / "private_media"

# Hand the actual byte-streaming to Nginx via X-Accel-Redirect instead of
# holding a Python worker for the length of a 500 MB transfer.
#
# This is a separate switch from DEBUG on purpose: keying it on DEBUG would
# mean any non-Nginx deployment (a bare gunicorn, a test run) silently returns
# an empty body with a header nothing acts on. Enabled explicitly in prod.py,
# where the reverse proxy is known to exist.
PRIVATE_MEDIA_X_ACCEL = config("PRIVATE_MEDIA_X_ACCEL", default=False, cast=bool)
PRIVATE_MEDIA_X_ACCEL_PREFIX = config(
    "PRIVATE_MEDIA_X_ACCEL_PREFIX", default="/protected/"
)

FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024      # 5 MB
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024     # 10 MB

MAX_IMAGE_SIZE_MB = 5
MAX_VIDEO_SIZE_MB = 100
MAX_PRODUCT_FILE_SIZE_MB = 500
ALLOWED_IMAGE_TYPES = ["image/jpeg", "image/png", "image/webp"]
ALLOWED_VIDEO_TYPES = ["video/mp4", "video/quicktime"]

# ═══════════════════════════════════════════════════════════════════════════
# DJANGO REST FRAMEWORK
# ═══════════════════════════════════════════════════════════════════════════
REST_FRAMEWORK = {
    # NOT the stock JWTAuthentication — ours additionally enforces
    # token_version and account state on every request. See
    # apps/accounts/authentication.py for why that matters.
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "apps.accounts.authentication.SnapSphereJWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_PAGINATION_CLASS": "apps.core.pagination.StandardPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ),
    "DEFAULT_RENDERER_CLASSES": ("apps.core.renderers.EnvelopeJSONRenderer",),
    "EXCEPTION_HANDLER": "apps.core.exceptions.custom_exception_handler",
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_THROTTLE_CLASSES": (),
    "DEFAULT_THROTTLE_RATES": {},
    "DATETIME_FORMAT": "%Y-%m-%dT%H:%M:%S%z",
    "COERCE_DECIMAL_TO_STRING": True,  # money as string — avoids JS float errors
}

SPECTACULAR_SETTINGS = {
    "TITLE": "SnapSphere API",
    "DESCRIPTION": "Photographer booking, marketplace and AI recommendation platform.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "SCHEMA_PATH_PREFIX": "/api/v1",
    "TAGS": [
        {"name": "Auth", "description": "Registration, login, tokens, password"},
        {"name": "Profiles", "description": "Buyer & photographer profiles"},
        {"name": "Catalog", "description": "Categories, services, packages"},
        {"name": "Portfolio", "description": "Images, videos, albums"},
        {"name": "Availability", "description": "Calendar & bookable slots"},
        {"name": "Bookings", "description": "Booking lifecycle"},
        {"name": "Marketplace", "description": "Digital products & orders"},
        {"name": "Reviews", "description": "Ratings, reviews, replies"},
        {"name": "Wishlist", "description": "Saved photographers & products"},
        {"name": "Chat", "description": "Conversations & messages"},
        {"name": "Notifications", "description": "In-app & push notifications"},
        {"name": "Recommendations", "description": "AI recommendation engine"},
        {"name": "Analytics", "description": "Dashboards & reports"},
        {"name": "Admin", "description": "Platform administration"},
    ],
    # Several serializers expose the same choice set under different field
    # names (`status`, `from_status`, `to_status`). Naming them explicitly
    # keeps one enum component per concept instead of Status5d0Enum.
    "ENUM_NAME_OVERRIDES": {
        "BookingStatusEnum": "apps.bookings.constants.BookingStatus.choices",
        "CancellationReasonEnum": "apps.bookings.constants.CancellationReason.choices",
        "PaymentMethodEnum": "apps.bookings.constants.PaymentMethod.choices",
        "PaymentStatusEnum": "apps.bookings.constants.PaymentStatus.choices",
    },
}

# ═══════════════════════════════════════════════════════════════════════════
# JWT
# ═══════════════════════════════════════════════════════════════════════════
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(
        minutes=config("ACCESS_TOKEN_LIFETIME_MINUTES", default=30, cast=int)
    ),
    "REFRESH_TOKEN_LIFETIME": timedelta(
        days=config("REFRESH_TOKEN_LIFETIME_DAYS", default=14, cast=int)
    ),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "ALGORITHM": "HS256",
    "SIGNING_KEY": SECRET_KEY,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
    "TOKEN_OBTAIN_SERIALIZER": "apps.accounts.serializers.SnapSphereTokenObtainPairSerializer",
}

# ═══════════════════════════════════════════════════════════════════════════
# CORS
# ═══════════════════════════════════════════════════════════════════════════
CORS_ALLOWED_ORIGINS = config(
    "CORS_ALLOWED_ORIGINS",
    default="http://localhost:5173,http://localhost:19006,http://localhost:8081",
    cast=Csv(),
)
CORS_ALLOW_CREDENTIALS = True

# The default allow-list does NOT include our own custom headers, and a header
# missing from it is refused at the preflight — so `POST /bookings/` and
# `POST /marketplace/orders/checkout/` would fail from any browser origin while
# working perfectly from Expo Go (native requests never preflight). That is the
# worst possible shape for a bug: invisible on the device it was tested on.
#
# `Idempotency-Key` is part of the API contract in every environment, so it
# belongs here rather than in dev.py.
CORS_ALLOW_HEADERS = (
    "accept",
    "accept-encoding",
    "authorization",
    "content-type",
    "dnt",
    "idempotency-key",
    "origin",
    "user-agent",
    "x-csrftoken",
    "x-requested-with",
)

# `X-Request-ID` is echoed on every response (see core.middleware). Exposing it
# is what lets a browser client quote it in a bug report — without this the
# header is present on the wire and unreadable from JavaScript.
CORS_EXPOSE_HEADERS = ("x-request-id",)

# ═══════════════════════════════════════════════════════════════════════════
# REDIS — /0 cache, /1 celery broker, /2 channels layer
# ═══════════════════════════════════════════════════════════════════════════
REDIS_URL = config("REDIS_URL", default="redis://127.0.0.1:6379")

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": f"{REDIS_URL}/0",
        "KEY_PREFIX": "snapsphere",
        "TIMEOUT": 300,
    }
}

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.pubsub.RedisPubSubChannelLayer",
        "CONFIG": {"hosts": [f"{REDIS_URL}/2"]},
    }
}

# ═══════════════════════════════════════════════════════════════════════════
# CELERY
# ═══════════════════════════════════════════════════════════════════════════
CELERY_BROKER_URL = f"{REDIS_URL}/1"
CELERY_RESULT_BACKEND = f"{REDIS_URL}/1"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "Asia/Karachi"
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"

EMAIL_BACKEND = config(
    "EMAIL_BACKEND", default="django.core.mail.backends.smtp.EmailBackend"
)
EMAIL_HOST = config("EMAIL_HOST", default="smtp.gmail.com")
EMAIL_PORT = config("EMAIL_PORT", default=587, cast=int)
EMAIL_HOST_USER = config("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = config("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = config("EMAIL_USE_TLS", default=True, cast=bool)
EMAIL_USE_SSL = config("EMAIL_USE_SSL", default=False, cast=bool)
DEFAULT_FROM_EMAIL = config("DEFAULT_FROM_EMAIL", default="SnapSphere <noreply@snapsphere.pk>")

# ═══════════════════════════════════════════════════════════════════════════
# BUSINESS RULES
# Kept in settings (not hard-coded) so behaviour is tunable per environment.
# Values that admins must change at runtime live in the PlatformSetting table.
# ═══════════════════════════════════════════════════════════════════════════
BOOKING_EXPIRY_HOURS = config("BOOKING_EXPIRY_HOURS", default=48, cast=int)
BOOKING_MIN_LEAD_HOURS = config("BOOKING_MIN_LEAD_HOURS", default=24, cast=int)
BOOKING_AUTO_COMPLETE_HOURS = config("BOOKING_AUTO_COMPLETE_HOURS", default=72, cast=int)
MAX_PENDING_BOOKINGS_PER_BUYER = config(
    "MAX_PENDING_BOOKINGS_PER_BUYER", default=5, cast=int
)
PLATFORM_COMMISSION_PERCENT = config(
    "PLATFORM_COMMISSION_PERCENT", default=10, cast=int
)
FREE_CANCELLATION_HOURS = config("FREE_CANCELLATION_HOURS", default=48, cast=int)
DOWNLOAD_TOKEN_TTL_MINUTES = config("DOWNLOAD_TOKEN_TTL_MINUTES", default=15, cast=int)
MAX_DOWNLOADS_PER_PURCHASE = config("MAX_DOWNLOADS_PER_PURCHASE", default=5, cast=int)

# ═══════════════════════════════════════════════════════════════════════════
# MACHINE LEARNING
# ═══════════════════════════════════════════════════════════════════════════
ML_ARTIFACTS_DIR = Path(config("ML_ARTIFACTS_DIR", default=str(ML_DIR / "artifacts")))
ML_DATA_RAW_DIR = ML_DIR / "data" / "raw"

REC_WEIGHT_CONTENT = config("REC_WEIGHT_CONTENT", default=0.55, cast=float)
REC_WEIGHT_COLLAB = config("REC_WEIGHT_COLLAB", default=0.30, cast=float)
REC_WEIGHT_BUSINESS = config("REC_WEIGHT_BUSINESS", default=0.15, cast=float)
REC_CACHE_TTL_SECONDS = config("REC_CACHE_TTL_SECONDS", default=1800, cast=int)
REC_MIN_INTERACTIONS_FOR_CF = config("REC_MIN_INTERACTIONS_FOR_CF", default=3, cast=int)
REC_EXPLORATION_SLOTS = config("REC_EXPLORATION_SLOTS", default=2, cast=int)

# Bayesian rating smoothing — same formula the prototype already used.
BAYESIAN_PRIOR_COUNT = 10     # m
BAYESIAN_PRIOR_RATING = 4.0   # C

# ═══════════════════════════════════════════════════════════════════════════
# LOGGING — structured JSON in prod, readable in dev
# ═══════════════════════════════════════════════════════════════════════════
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "[{asctime}] {levelname} {name} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "verbose"},
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "django.db.backends": {"level": "WARNING", "handlers": ["console"], "propagate": False},
        "snapsphere": {"level": "DEBUG", "handlers": ["console"], "propagate": False},
    },
}
