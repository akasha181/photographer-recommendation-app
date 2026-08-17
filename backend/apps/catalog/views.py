"""
Catalogue endpoints.

Browsing is public; managing is not. `MyServiceViewSet` is the write half —
Module 5 — and every one of its querysets is scoped to the authenticated
photographer, so a listing that is not theirs is simply not found.
"""

from drf_spectacular.utils import extend_schema
from rest_framework import status as http
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet, ReadOnlyModelViewSet

from apps.catalog import selectors, services
from apps.catalog.models import Service, ServicePackage
from apps.catalog.serializers import (
    CategorySerializer,
    OwnServiceSerializer,
    ServicePackageSerializer,
    ServicePackageWriteSerializer,
    ServiceSerializer,
    ServiceWriteSerializer,
    SpecializationSerializer,
)
from apps.core.mixins import MessageResponseMixin, MultiSerializerMixin
from apps.core.permissions import IsPhotographer


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


# ═══════════════════════════════════════════════════════════════════════════
# MODULE 5 — MANAGING YOUR OWN SERVICES
# ═══════════════════════════════════════════════════════════════════════════
@extend_schema(tags=["Catalog"])
class MyServiceViewSet(
    MessageResponseMixin, MultiSerializerMixin, GenericViewSet
):
    """
    A photographer's own listings — what buyers can book from them.

    Everything here is scoped to `request.user.photographer_profile`, so the
    id in the URL can only ever address the caller's own row.
    """

    permission_classes = [IsAuthenticated, IsPhotographer]
    serializer_class = OwnServiceSerializer
    serializer_classes = {
        "create": ServiceWriteSerializer,
        "partial_update": ServiceWriteSerializer,
        "add_package": ServicePackageWriteSerializer,
        "update_package": ServicePackageWriteSerializer,
    }
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    pagination_class = None
    queryset = Service.objects.none()  # schema inference only
    success_messages = {
        "list": "Your services retrieved",
        "retrieve": "Service retrieved",
        "create": "Service published",
        "partial_update": "Service updated",
        "archive": "Service archived — buyers can no longer book it",
        "restore": "Service is live again",
        "destroy": "Service deleted",
        "add_package": "Tier added",
        "update_package": "Tier updated",
        "delete_package": "Tier removed",
    }

    def _profile(self):
        profile = getattr(self.request.user, "photographer_profile", None)
        if profile is None:
            raise NotFound("Only photographer accounts have a service catalogue.")
        return profile

    def _service(self, pk) -> Service:
        service = selectors.get_own_service(self._profile(), int(pk))
        if service is None:
            raise NotFound("Service not found.")
        return service

    def _detail(self, service: Service) -> Response:
        service.refresh_from_db()
        return Response(
            OwnServiceSerializer(service, context=self.get_serializer_context()).data
        )

    # ─── Read ────────────────────────────────────────────────────────────────
    @extend_schema(
        summary="Your services, archived ones included",
        responses=OwnServiceSerializer(many=True),
    )
    def list(self, request):
        rows = selectors.get_own_services(self._profile())
        return Response(
            OwnServiceSerializer(
                rows, many=True, context=self.get_serializer_context()
            ).data
        )

    @extend_schema(summary="One of your services", responses=OwnServiceSerializer)
    def retrieve(self, request, pk=None):
        return self._detail(self._service(pk))

    # ─── Write ───────────────────────────────────────────────────────────────
    @extend_schema(
        summary="Publish a new service",
        request=ServiceWriteSerializer,
        responses={201: OwnServiceSerializer},
    )
    def create(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        service = services.create_service(self._profile(), **serializer.validated_data)
        return Response(
            OwnServiceSerializer(service, context=self.get_serializer_context()).data,
            status=http.HTTP_201_CREATED,
        )

    @extend_schema(
        summary="Edit a service — never rewrites existing bookings",
        request=ServiceWriteSerializer,
        responses=OwnServiceSerializer,
    )
    def partial_update(self, request, pk=None):
        service = self._service(pk)
        serializer = self.get_serializer(service, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        return self._detail(services.update_service(service, **serializer.validated_data))

    @extend_schema(
        summary="Delete outright — refused once it has bookings",
        responses={204: None},
    )
    def destroy(self, request, pk=None):
        services.delete_service(self._service(pk))
        return Response(status=http.HTTP_204_NO_CONTENT)

    @extend_schema(summary="Hide from discovery, keep the history")
    @action(detail=True, methods=["post"])
    def archive(self, request, pk=None):
        return self._detail(services.archive_service(self._service(pk)))

    @extend_schema(summary="Put an archived service back on sale")
    @action(detail=True, methods=["post"])
    def restore(self, request, pk=None):
        return self._detail(services.restore_service(self._service(pk)))

    # ─── Packages (tiers) ────────────────────────────────────────────────────
    @extend_schema(
        summary="Add a tier (Silver / Gold / Platinum)",
        request=ServicePackageWriteSerializer,
        responses={201: ServicePackageSerializer},
    )
    @action(detail=True, methods=["post"], url_path="packages")
    def add_package(self, request, pk=None):
        service = self._service(pk)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        package = services.create_package(service, **serializer.validated_data)
        return Response(
            ServicePackageSerializer(package).data, status=http.HTTP_201_CREATED
        )

    @extend_schema(
        summary="Edit a tier",
        request=ServicePackageWriteSerializer,
        responses=ServicePackageSerializer,
    )
    @action(
        detail=True, methods=["patch"], url_path=r"packages/(?P<package_id>\d+)"
    )
    def update_package(self, request, pk=None, package_id=None):
        package = self._package(pk, package_id)
        serializer = self.get_serializer(package, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        return Response(
            ServicePackageSerializer(
                services.update_package(package, **serializer.validated_data)
            ).data
        )

    @extend_schema(summary="Remove a tier", responses={204: None})
    @action(
        detail=True,
        methods=["delete"],
        url_path=r"packages/(?P<package_id>\d+)/remove",
    )
    def delete_package(self, request, pk=None, package_id=None):
        services.delete_package(self._package(pk, package_id))
        return Response(status=http.HTTP_204_NO_CONTENT)

    def _package(self, service_pk, package_id) -> ServicePackage:
        service = self._service(service_pk)
        package = service.packages.filter(pk=int(package_id)).first()
        if package is None:
            raise NotFound("Tier not found on this service.")
        return package
