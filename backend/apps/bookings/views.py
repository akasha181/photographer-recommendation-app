"""
Booking endpoints.

Views stay thin: authenticate, authorise, validate, delegate, return. Every
state change goes through `services.py`, so there is exactly one
implementation of the rules no matter which route reached it.

TWO ACCESS CONTROLS, ON PURPOSE
-------------------------------
`selectors.get_booking_for_user()` scopes the query to the caller, so a
booking that is not theirs is simply not found — a 404, not a 403, because
"this exists but is not yours" is itself information. `IsBookingParticipant`
then re-checks at the object level. Either alone would be enough today; both
means a future refactor that loosens one does not silently open the door.
"""

import logging

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status as http
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from apps.bookings import selectors, services
from apps.bookings.models import Booking
from apps.bookings.serializers import (
    BookingActionSerializer,
    BookingCancelSerializer,
    BookingCountsSerializer,
    BookingCreateSerializer,
    BookingDetailSerializer,
    BookingListSerializer,
    BookingRejectSerializer,
)
from apps.core.mixins import (
    ActionPermissionsMixin,
    MessageResponseMixin,
    MultiSerializerMixin,
)
from apps.core.permissions import IsBookingParticipant, IsBuyer, IsPhotographer

logger = logging.getLogger("snapsphere")

MAX_IDEMPOTENCY_KEY_LENGTH = 128


@extend_schema(tags=["Bookings"])
class BookingViewSet(
    MessageResponseMixin, MultiSerializerMixin, ActionPermissionsMixin, GenericViewSet
):
    """Request, track and resolve bookings."""

    permission_classes = [IsAuthenticated]
    serializer_class = BookingListSerializer
    serializer_classes = {
        "create": BookingCreateSerializer,
        "retrieve": BookingDetailSerializer,
        "accept": BookingActionSerializer,
        "complete": BookingActionSerializer,
        "reject": BookingRejectSerializer,
        "cancel": BookingCancelSerializer,
        "counts": BookingCountsSerializer,
    }
    action_permissions = {
        "create": [IsAuthenticated, IsBuyer],
        "retrieve": [IsAuthenticated, IsBookingParticipant],
        "accept": [IsAuthenticated, IsPhotographer, IsBookingParticipant],
        "reject": [IsAuthenticated, IsPhotographer, IsBookingParticipant],
        "cancel": [IsAuthenticated, IsBookingParticipant],
        "complete": [IsAuthenticated, IsBookingParticipant],
    }
    success_messages = {
        "list": "Bookings retrieved",
        "retrieve": "Booking retrieved",
        "create": "Booking request sent to the photographer",
        "accept": "Booking accepted",
        "reject": "Booking declined",
        "cancel": "Booking cancelled",
        "complete": "Booking marked complete",
        "counts": "Counts retrieved",
        "upcoming": "Upcoming bookings retrieved",
    }

    def get_throttles(self):
        """Only creation is rate-limited; reading your own bookings is not."""
        self.throttle_scope = "booking_create" if self.action == "create" else None
        return super().get_throttles()

    def get_queryset(self):
        # drf-spectacular introspects this with an AnonymousUser to work out
        # the model behind the view. Without the guard, schema generation
        # raises and the path parameter falls back to an untyped string.
        if getattr(self, "swagger_fake_view", False):
            return Booking.objects.none()
        return selectors.get_user_bookings(
            self.request.user,
            group=self.request.query_params.get("group"),
            status=self.request.query_params.get("status"),
        )

    def get_object(self):
        booking = selectors.get_booking_for_user(self.request.user, self.kwargs["pk"])
        if booking is None:
            raise NotFound("Booking not found.")
        self.check_object_permissions(self.request, booking)
        return booking

    # ─── Read ────────────────────────────────────────────────────────────────
    @extend_schema(
        summary="List the caller's bookings",
        parameters=[
            OpenApiParameter(
                "group", str,
                description="pending | upcoming | completed | cancelled — the "
                            "tabs the app shows",
            ),
            OpenApiParameter(
                "status", str,
                description="Exact status, when `group` is not specific enough",
            ),
        ],
        responses=BookingListSerializer(many=True),
    )
    def list(self, request):
        page = self.paginate_queryset(self.get_queryset())
        serializer = self.get_serializer(page, many=True)
        return self.get_paginated_response(serializer.data)

    @extend_schema(summary="One booking, with its full timeline")
    def retrieve(self, request, pk=None):
        return Response(self.get_serializer(self.get_object()).data)

    @extend_schema(summary="Counts for the status tabs", responses=BookingCountsSerializer)
    @action(detail=False, methods=["get"], pagination_class=None)
    def counts(self, request):
        return Response(BookingCountsSerializer(selectors.booking_counts(request.user)).data)

    @extend_schema(
        summary="The caller's next confirmed shoots",
        responses=BookingListSerializer(many=True),
    )
    @action(detail=False, methods=["get"], pagination_class=None)
    def upcoming(self, request):
        rows = selectors.upcoming_bookings(request.user, limit=5)
        return Response(BookingListSerializer(rows, many=True, context=self.get_serializer_context()).data)

    # ─── Create ──────────────────────────────────────────────────────────────
    @extend_schema(
        summary="Request a booking",
        description=(
            "Send an `Idempotency-Key` header — any unique string per attempt. "
            "A retry carrying the same key returns the booking the first call "
            "created instead of making a second one."
        ),
        request=BookingCreateSerializer,
        responses={201: BookingDetailSerializer},
    )
    def create(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        booking = services.create_booking(
            buyer=request.user,
            idempotency_key=self._idempotency_key(request),
            **serializer.validated_data,
        )
        return Response(
            BookingDetailSerializer(booking, context=self.get_serializer_context()).data,
            status=http.HTTP_201_CREATED,
        )

    @staticmethod
    def _idempotency_key(request) -> str | None:
        key = (request.headers.get("Idempotency-Key") or "").strip()
        if not key:
            return None
        if len(key) > MAX_IDEMPOTENCY_KEY_LENGTH:
            raise ValidationError(
                {"Idempotency-Key": f"Must be at most {MAX_IDEMPOTENCY_KEY_LENGTH} characters."}
            )
        return key

    # ─── Transitions ─────────────────────────────────────────────────────────
    @extend_schema(summary="Photographer accepts the request", request=BookingActionSerializer)
    @action(detail=True, methods=["post"])
    def accept(self, request, pk=None):
        data = self._validated(request)
        booking = services.accept_booking(
            self.get_object(), request.user, note=data.get("note", "")
        )
        return self._detail(booking)

    @extend_schema(summary="Photographer declines the request", request=BookingRejectSerializer)
    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        data = self._validated(request)
        booking = services.reject_booking(
            self.get_object(), request.user, reason=data["reason"]
        )
        return self._detail(booking)

    @extend_schema(summary="Either party cancels", request=BookingCancelSerializer)
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        data = self._validated(request)
        booking = services.cancel_booking(
            self.get_object(),
            request.user,
            reason=data.get("reason", ""),
            note=data.get("note", ""),
        )
        return self._detail(booking)

    @extend_schema(summary="Mark the shoot as done", request=BookingActionSerializer)
    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        data = self._validated(request)
        booking = services.complete_booking(
            self.get_object(), request.user, note=data.get("note", "")
        )
        return self._detail(booking)

    # ─── Helpers ─────────────────────────────────────────────────────────────
    def _validated(self, request) -> dict:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data

    def _detail(self, booking) -> Response:
        """
        Every transition returns the whole booking.

        The app then re-renders from one authoritative payload — including the
        refreshed `available_actions` — instead of patching its local copy and
        hoping the two agree.
        """
        fresh = selectors.get_booking_for_user(self.request.user, booking.pk)
        return Response(
            BookingDetailSerializer(
                fresh or booking, context=self.get_serializer_context()
            ).data
        )
