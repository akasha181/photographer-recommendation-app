"""
Availability endpoints — the calendar behind the booking form.

Public, like photographer discovery: a buyer decides whether to book by
looking at which dates are free, and forcing a login before they can see that
loses them at exactly the wrong moment. Nothing here exposes anything the
photographer's own profile page does not already show.
"""

from dataclasses import asdict
from datetime import datetime

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from apps.availability import selectors
from apps.availability.models import AvailabilityRule
from apps.availability.serializers import (
    AvailabilityCalendarSerializer,
    AvailabilityRuleSerializer,
    DayDetailSerializer,
)
from apps.core.mixins import MessageResponseMixin


def _parse_date(raw: str | None, field: str):
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        raise ValidationError({field: "Use the format YYYY-MM-DD."})


def _parse_int(raw: str | None, field: str, default: int | None = None):
    if raw in (None, ""):
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        raise ValidationError({field: "Must be a whole number."})


@extend_schema(tags=["Availability"])
class PhotographerAvailabilityViewSet(MessageResponseMixin, GenericViewSet):
    """When is this photographer free?"""

    permission_classes = [AllowAny]
    serializer_class = AvailabilityCalendarSerializer
    pagination_class = None
    throttle_scope = "search"
    success_messages = {
        "retrieve": "Availability retrieved",
        "day": "Date availability retrieved",
        "rules": "Weekly schedule retrieved",
    }

    def get_queryset(self):
        from apps.profiles.selectors import visible_photographers

        return visible_photographers()

    def _photographer(self, pk):
        photographer = self.get_queryset().filter(pk=pk).first()
        if photographer is None:
            raise NotFound("This photographer is not available.")
        return photographer

    @extend_schema(
        summary="Booking calendar for a date window",
        parameters=[
            OpenApiParameter("start", str, description="YYYY-MM-DD, defaults to today"),
            OpenApiParameter(
                "days", int,
                description=f"Window length, 1-{selectors.MAX_WINDOW_DAYS} "
                            f"(default {selectors.DEFAULT_WINDOW_DAYS})",
            ),
        ],
        responses=AvailabilityCalendarSerializer,
    )
    def retrieve(self, request, pk=None):
        photographer = self._photographer(pk)
        start = _parse_date(request.query_params.get("start"), "start")
        days = _parse_int(request.query_params.get("days"), "days")

        calendar = selectors.availability_calendar(photographer, start=start, days=days)
        payload = {
            "photographer_id": photographer.pk,
            "start_date": calendar[0].date,
            "end_date": calendar[-1].date,
            "earliest_bookable_date": selectors.earliest_bookable_date(),
            "is_accepting_bookings": photographer.is_accepting_bookings,
            "days": calendar,
        }
        return Response(AvailabilityCalendarSerializer(payload).data)

    @extend_schema(
        summary="One date, with the start times the form may offer",
        parameters=[
            OpenApiParameter("date", str, required=True, description="YYYY-MM-DD"),
            OpenApiParameter(
                "duration_hours", int,
                description="Shoot length, so late starts that would overrun the "
                            "photographer's day are excluded (default 4)",
            ),
        ],
        responses=DayDetailSerializer,
    )
    @action(detail=True, methods=["get"])
    def day(self, request, pk=None):
        photographer = self._photographer(pk)
        date = _parse_date(request.query_params.get("date"), "date")
        if date is None:
            raise ValidationError({"date": "This query parameter is required."})
        duration = _parse_int(request.query_params.get("duration_hours"), "duration_hours", 4)

        day = selectors.day_availability(photographer, date)
        payload = {
            **asdict(day),
            "available_start_times": selectors.suggested_start_times(
                photographer, date, duration_hours=duration or 4
            ),
        }
        return Response(DayDetailSerializer(payload).data)

    @extend_schema(summary="The photographer's weekly working pattern")
    @action(detail=True, methods=["get"])
    def rules(self, request, pk=None):
        photographer = self._photographer(pk)
        rows = AvailabilityRule.objects.filter(photographer=photographer).order_by(
            "weekday"
        )
        return Response(AvailabilityRuleSerializer(rows, many=True).data)
