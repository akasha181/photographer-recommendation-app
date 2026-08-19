"""Analytics & Reporting routes — mounted at /api/v1/analytics/"""

from rest_framework.routers import DefaultRouter

from apps.analytics.views import MyAnalyticsViewSet

app_name = "analytics"

router = DefaultRouter()
router.register("me", MyAnalyticsViewSet, basename="my-analytics")

urlpatterns = router.urls
