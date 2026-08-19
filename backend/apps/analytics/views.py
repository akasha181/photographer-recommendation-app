"""
Analytics endpoints — Module 15.

Scoped to the authenticated photographer. There is no "analytics for
photographer X" route by design: engagement and revenue figures are
competitively sensitive, and the only person entitled to them is their owner.
"""

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from apps.analytics import selectors
from apps.analytics.models import DailyPhotographerStat
from apps.analytics.serializers import (
    DashboardSerializer,
    FunnelSerializer,
    RevenuePointSerializer,
)
from apps.core.mixins import MessageResponseMixin, MultiSerializerMixin
from apps.core.permissions import IsPhotographer


@extend_schema(tags=["Analytics"])
class MyAnalyticsViewSet(MessageResponseMixin, MultiSerializerMixin, GenericViewSet):
    """The photographer's own performance."""

    permission_classes = [IsAuthenticated, IsPhotographer]
    serializer_class = DashboardSerializer
    pagination_class = None
    queryset = DailyPhotographerStat.objects.none()  # schema inference only
    success_messages = {
        "list": "Dashboard retrieved",
        "revenue": "Revenue retrieved",
        "funnel": "Funnel retrieved",
    }

    def _profile(self):
        profile = getattr(self.request.user, "photographer_profile", None)
        if profile is None:
            raise NotFound("Only photographer accounts have analytics.")
        return profile

    @staticmethod
    def _window(request, key: str, default: int, maximum: int) -> int:
        """Clamped — an unbounded window is a cheap way to make us do work."""
        try:
            value = int(request.query_params.get(key, default))
        except (TypeError, ValueError):
            return default
        return max(1, min(value, maximum))

    @extend_schema(
        summary="Everything the Dashboard screen renders, in one response",
        parameters=[
            OpenApiParameter("days", int, description="Trend window, 1-90 (default 30)"),
            OpenApiParameter("months", int, description="Revenue window, 1-24 (default 6)"),
        ],
        responses=DashboardSerializer,
    )
    def list(self, request):
        data = selectors.dashboard(
            self._profile(),
            days=self._window(request, "days", 30, 90),
            months=self._window(request, "months", 6, 24),
        )
        return Response(
            DashboardSerializer(data, context=self.get_serializer_context()).data
        )

    @extend_schema(
        summary="Monthly earnings series",
        parameters=[OpenApiParameter("months", int)],
        responses=RevenuePointSerializer(many=True),
    )
    @action(detail=False, methods=["get"])
    def revenue(self, request):
        rows = selectors.revenue_series(
            self._profile(), months=self._window(request, "months", 12, 24)
        )
        return Response(RevenuePointSerializer(rows, many=True).data)

    @extend_schema(
        summary="Discovery funnel",
        parameters=[OpenApiParameter("days", int)],
        responses=FunnelSerializer,
    )
    @action(detail=False, methods=["get"])
    def funnel(self, request):
        data = selectors.funnel(
            self._profile(), days=self._window(request, "days", 30, 90)
        )
        return Response(FunnelSerializer(data).data)
