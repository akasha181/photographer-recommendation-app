"""Catalogue routes — mounted at /api/v1/catalog/"""

from rest_framework.routers import DefaultRouter

from apps.catalog.views import (
    CategoryViewSet,
    MyServiceViewSet,
    ServiceViewSet,
    SpecializationViewSet,
)

app_name = "catalog"

router = DefaultRouter()
router.register("categories", CategoryViewSet, basename="category")
router.register("specializations", SpecializationViewSet, basename="specialization")
# Registered before the public `services` prefix so `my-services` is never
# swallowed by the public detail lookup.
router.register("my-services", MyServiceViewSet, basename="my-service")
router.register("services", ServiceViewSet, basename="service")

urlpatterns = router.urls
