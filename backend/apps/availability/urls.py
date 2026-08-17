"""Availability Calendar routes — mounted at /api/v1/availability/"""

from rest_framework.routers import DefaultRouter

from apps.availability.views import (
    MyAvailabilityViewSet,
    PhotographerAvailabilityViewSet,
)

app_name = "availability"

router = DefaultRouter()
# `me` before `photographers` is not strictly required (the prefixes differ),
# but keeping the owner routes first matches how they are read.
router.register("me", MyAvailabilityViewSet, basename="my-availability")
router.register(
    "photographers", PhotographerAvailabilityViewSet, basename="availability"
)

urlpatterns = router.urls
