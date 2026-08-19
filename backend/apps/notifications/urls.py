"""Notifications routes — mounted at /api/v1/notifications/"""

from rest_framework.routers import DefaultRouter

from apps.notifications.views import NotificationViewSet

app_name = "notifications"

router = DefaultRouter()
router.register("", NotificationViewSet, basename="notification")

urlpatterns = router.urls
