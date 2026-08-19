"""
Availability endpoints — the calendar behind the booking form.

Public, like photographer discovery: a buyer decides whether to book by
looking at which dates are free, and forcing a login before they can see that
loses them at exactly the wrong moment. Nothing here exposes anything the
photographer's own profile page does not already show.
"""

from dataclasses import asdict
from datetime import datetime

from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status as http
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from apps.availability import selectors, services
from apps.availability.models import AvailabilityRule, BlackoutDate
from apps.availability.serializers import (
    AvailabilityCalendarSerializer,
    AvailabilityRuleSerializer,
    BlackoutResultSerializer,
    BlackoutSerializer,
    BlackoutWriteSerializer,
    DayDetailSerializer,
    MyCalendarSerializer,
    WeeklyScheduleWriteSerializer,
)
from apps.core.mixins import MessageResponseMixin, MultiSerializerMixin
from apps.core.permissions import IsPhotographer


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


# ═══════════════════════════════════════════════════════════════════════════
# MODULE 5 — MANAGING YOUR OWN CALENDAR
# ═══════════════════════════════════════════════════════════════════════════
@extend_schema(tags=["Availability"])
class MyAvailabilityViewSet(MessageResponseMixin, MultiSerializerMixin, GenericViewSet):
    """
    The photographer's own calendar.

    Everything is scoped to `request.user.photographer_profile`. Narrowing the
    calendar never cancels an existing booking — see `services.py` for why.
    """

    permission_classes = [IsAuthenticated, IsPhotographer]
    serializer_class = AvailabilityRuleSerializer
    serializer_classes = {
        "set_schedule": WeeklyScheduleWriteSerializer,
        "add_blackout": BlackoutWriteSerializer,
    }
    pagination_class = None
    queryset = AvailabilityRule.objects.none()  # schema inference only
    success_messages = {
        "list": "Your calendar retrieved",
        "set_schedule": "Weekly schedule saved",
        "blackouts": "Blocked periods retrieved",
        "add_blackout": "Dates blocked",
        "remove_blackout": "Block removed",
    }

    def _profile(self):
        profile = getattr(self.request.user, "photographer_profile", None)
        if profile is None:
            raise NotFound("Only photographer accounts have a calendar.")
        return profile

    @extend_schema(
        summary="Weekly pattern plus blocked periods",
        responses=MyCalendarSerializer,
    )
    def list(self, request):
        profile = self._profile()
        rules = AvailabilityRule.objects.filter(photographer=profile).order_by("weekday")
        blackouts = BlackoutDate.objects.filter(
            photographer=profile, end_date__gte=timezone.localdate()
        ).order_by("start_date")

        return Response(
            MyCalendarSerializer(
                {
                    "is_accepting_bookings": profile.is_accepting_bookings,
                    "rules": rules,
                    "blackouts": blackouts,
                }
            ).data
        )

    @extend_schema(
        summary="Save the whole week at once",
        request=WeeklyScheduleWriteSerializer,
        responses=AvailabilityRuleSerializer(many=True),
    )
    @action(detail=False, methods=["put"], url_path="schedule")
    def set_schedule(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        rules = services.set_weekly_rules(
            self._profile(), serializer.validated_data["rules"]
        )
        return Response(AvailabilityRuleSerializer(rules, many=True).data)

    @extend_schema(summary="Upcoming blocked periods", responses=BlackoutSerializer(many=True))
    @action(detail=False, methods=["get"])
    def blackouts(self, request):
        rows = BlackoutDate.objects.filter(
            photographer=self._profile(), end_date__gte=timezone.localdate()
        ).order_by("start_date")
        return Response(BlackoutSerializer(rows, many=True).data)

    @extend_schema(
        summary="Block a date range — reports clashes, cancels nothing",
        request=BlackoutWriteSerializer,
        responses={201: BlackoutResultSerializer},
    )
    @action(detail=False, methods=["post"], url_path="blackouts/add")
    def add_blackout(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        blackout, clashes = services.add_blackout(
            self._profile(), **serializer.validated_data
        )
        return Response(
            BlackoutResultSerializer(
                {"blackout": blackout, "conflicting_bookings": clashes}
            ).data,
            status=http.HTTP_201_CREATED,
        )

    @extend_schema(summary="Unblock a period", responses={204: None})
    @action(
        detail=False, methods=["delete"], url_path=r"blackouts/(?P<blackout_id>\d+)"
    )
    def remove_blackout(self, request, blackout_id=None):
        services.remove_blackout(self._profile(), int(blackout_id))
        return Response(status=http.HTTP_204_NO_CONTENT)
