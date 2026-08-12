"""Availability Calendar routes — mounted at /api/v1/availability/"""

from rest_framework.routers import DefaultRouter

from apps.availability.views import PhotographerAvailabilityViewSet

app_name = "availability"

router = DefaultRouter()
router.register(
    "photographers", PhotographerAvailabilityViewSet, basename="availability"
)

urlpatterns = router.urls
