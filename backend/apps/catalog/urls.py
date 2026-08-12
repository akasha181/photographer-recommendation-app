"""Catalogue routes — mounted at /api/v1/catalog/"""

from rest_framework.routers import DefaultRouter

from apps.catalog.views import CategoryViewSet, ServiceViewSet, SpecializationViewSet

app_name = "catalog"

router = DefaultRouter()
router.register("categories", CategoryViewSet, basename="category")
router.register("specializations", SpecializationViewSet, basename="specialization")
router.register("services", ServiceViewSet, basename="service")

urlpatterns = router.urls
