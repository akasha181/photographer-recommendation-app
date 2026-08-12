"""Catalogue endpoints — public, read-only."""

from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.viewsets import ReadOnlyModelViewSet

from apps.catalog import selectors
from apps.catalog.serializers import (
    CategorySerializer,
    ServiceSerializer,
    SpecializationSerializer,
)
from apps.core.mixins import MessageResponseMixin


@extend_schema(tags=["Catalog"])
class CategoryViewSet(MessageResponseMixin, ReadOnlyModelViewSet):
    """
    The five canonical event categories.

    Public: a buyer browses categories before signing up, and requiring auth
    here would put a login wall in front of the first screen of the app.
    """

    serializer_class = CategorySerializer
    permission_classes = [AllowAny]
    pagination_class = None  # only five rows — pagination would be noise
    lookup_field = "slug"
    success_messages = {"list": "Categories retrieved"}

    def get_queryset(self):
        return selectors.get_active_categories()


@extend_schema(tags=["Catalog"])
class SpecializationViewSet(MessageResponseMixin, ReadOnlyModelViewSet):
    """Free-form tags (Bridal Portrait, Drone, Newborn, …)."""

    serializer_class = SpecializationSerializer
    permission_classes = [AllowAny]
    pagination_class = None

    def get_queryset(self):
        return selectors.get_specializations(
            self.request.query_params.get("category")
        )


@extend_schema(tags=["Catalog"])
class ServiceViewSet(MessageResponseMixin, ReadOnlyModelViewSet):
    """Bookable services, filterable by photographer."""

    serializer_class = ServiceSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        from apps.catalog.models import Service

        qs = (
            Service.objects.filter(is_active=True, is_deleted=False)
            .select_related("category", "photographer", "photographer__user")
            .prefetch_related("packages")
        )
        photographer = self.request.query_params.get("photographer")
        if photographer:
            qs = qs.filter(photographer_id=photographer)
        category = self.request.query_params.get("category")
        if category:
            qs = qs.filter(category__slug=category)
        return qs.order_by("display_order", "price")
