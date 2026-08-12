"""
Root URL configuration.

Every business endpoint is namespaced under /api/v1/. A future breaking change
becomes /api/v2/ while v1 keeps serving existing app installs.
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

from apps.core.views import health_check

API = "api/v1/"

urlpatterns = [
    # ─── Django's built-in admin (emergency ops only, not the product admin) ──
    path("django-admin/", admin.site.urls),

    # ─── Health & docs ───────────────────────────────────────────────────────
    path("health/", health_check, name="health-check"),
    path(f"{API}schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        f"{API}docs/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
    path(
        f"{API}redoc/",
        SpectacularRedocView.as_view(url_name="schema"),
        name="redoc",
    ),

    # ─── Domain APIs ─────────────────────────────────────────────────────────
    path(f"{API}auth/", include("apps.accounts.urls")),
    path(f"{API}profiles/", include("apps.profiles.urls")),
    path(f"{API}catalog/", include("apps.catalog.urls")),
    path(f"{API}portfolio/", include("apps.portfolio.urls")),
    path(f"{API}availability/", include("apps.availability.urls")),
    path(f"{API}bookings/", include("apps.bookings.urls")),
    path(f"{API}marketplace/", include("apps.marketplace.urls")),
    path(f"{API}reviews/", include("apps.reviews.urls")),
    path(f"{API}wishlist/", include("apps.wishlist.urls")),
    path(f"{API}chat/", include("apps.chat.urls")),
    path(f"{API}notifications/", include("apps.notifications.urls")),
    path(f"{API}recommendations/", include("apps.recommendations.urls")),
    path(f"{API}analytics/", include("apps.analytics.urls")),
    path(f"{API}admin/", include("apps.administration.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
