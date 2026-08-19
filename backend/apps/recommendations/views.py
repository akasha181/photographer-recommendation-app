"""Recommendation endpoints."""

import logging

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.recommendations import engine
from apps.recommendations.serializers import RecommendationSerializer

logger = logging.getLogger("snapsphere")


@extend_schema(
    tags=["Recommendations"],
    summary="Ranked photographer recommendations with explanations",
    parameters=[
        OpenApiParameter("category", str, description="Category slug"),
        OpenApiParameter("city", str),
        OpenApiParameter("max_price", float, description="Budget ceiling in PKR"),
        OpenApiParameter("limit", int, description="Default 20, max 50"),
    ],
)
class RecommendationView(APIView):
    """
    The Home screen's primary feed.

    AllowAny: an anonymous browser gets popularity ranking, a signed-in buyer
    with history gets a personalised hybrid. Both are useful; requiring a
    login to see anything would gate the first screen of the app.
    """

    permission_classes = [AllowAny]
    throttle_scope = "search"

    def get(self, request):
        try:
            limit = min(int(request.query_params.get("limit", 50)), 200)
        except (TypeError, ValueError):
            limit = 50

        max_price = request.query_params.get("max_price")
        try:
            max_price = float(max_price) if max_price else None
        except (TypeError, ValueError):
            max_price = None

        result = engine.recommend(
            buyer=request.user,
            category=request.query_params.get("category"),
            city=request.query_params.get("city"),
            max_price=max_price,
            limit=limit,
        )

        context = {"request": request}
        if request.user.is_authenticated:
            from apps.wishlist.models import WishlistItem

            context["wishlisted_ids"] = set(
                WishlistItem.objects.filter(
                    user=request.user, photographer__isnull=False
                ).values_list("photographer_id", flat=True)
            )

        serializer = RecommendationSerializer(
            result["photographers"], many=True, context=context
        )

        self._log_impressions(request, result)

        return Response(
            {
                "message": "Recommendations retrieved",
                "data": serializer.data,
                "meta": {
                    "strategy": result["strategy"],
                    "personalised": result["personalised"],
                    "model_mode": result["model_mode"],
                    # Non-null when filters matched nobody and were widened.
                    # The UI shows this so the user is not misled into
                    # thinking these were exact matches.
                    "relaxed": result["relaxed"],
                    "count": len(serializer.data),
                },
            }
        )

    def _log_impressions(self, request, result) -> None:
        """
        Record what was shown, at what rank.

        This is the raw material for offline CTR and Precision@K evaluation.
        Skipped for anonymous users (nothing to attribute) and wrapped in a
        try/except, because analytics must never break the feed.
        """
        if not request.user.is_authenticated:
            return
        try:
            from apps.recommendations.models import RecommendationEvent

            RecommendationEvent.objects.bulk_create(
                [
                    RecommendationEvent(
                        buyer=request.user,
                        photographer=photographer,
                        position=index,
                        score=getattr(photographer, "score", 0.0),
                        content_score=getattr(photographer, "content_score", 0.0),
                        collab_score=getattr(photographer, "collab_score", 0.0),
                        business_score=getattr(photographer, "business_score", 0.0),
                        strategy=getattr(photographer, "strategy", "HYBRID"),
                        reason=getattr(photographer, "reason", "")[:200],
                        filters_applied={
                            k: v for k, v in request.query_params.items()
                        },
                    )
                    for index, photographer in enumerate(result["photographers"], start=1)
                ],
                batch_size=50,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not log recommendation impressions: %s", exc)


@extend_schema(
    tags=["Recommendations"],
    summary="Record that a recommendation was clicked",
)
class RecommendationClickView(APIView):
    """
    Closes the feedback loop.

    Without click data there is no way to measure whether recommendations are
    any good — CTR and Precision@K are computed from exactly these two events
    (impression and click).
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        photographer_id = request.data.get("photographer_id")
        if not photographer_id:
            from rest_framework.exceptions import ValidationError

            raise ValidationError({"photographer_id": ["This field is required."]})

        from django.utils import timezone

        from apps.recommendations.models import RecommendationEvent

        updated = (
            RecommendationEvent.objects.filter(
                buyer=request.user,
                photographer_id=photographer_id,
                was_clicked=False,
            )
            .order_by("-created_at")[:1]
            .values_list("pk", flat=True)
        )
        RecommendationEvent.objects.filter(pk__in=list(updated)).update(
            was_clicked=True, clicked_at=timezone.now()
        )
        return Response({"message": "Recorded", "data": None})


@extend_schema(tags=["Recommendations"], summary="Engine status and live model info")
class RecommendationStatusView(APIView):
    """
    Diagnostics for the admin dashboard and for the FYP demo.

    Makes the honest state of the ML visible rather than hidden: which model
    is live, what mode it is in, and what its measured metrics were.
    """

    permission_classes = [AllowAny]

    def get(self, request):
        import json
        from pathlib import Path

        from django.conf import settings

        ranker = engine._load_ranker()
        cf = engine._load_cf()

        metrics = {}
        metrics_path = Path(settings.ML_ARTIFACTS_DIR) / "metrics.json"
        if metrics_path.exists():
            try:
                metrics = json.loads(metrics_path.read_text())
            except (OSError, ValueError):
                metrics = {}

        return Response(
            {
                "message": "Engine status",
                "data": {
                    "ranker": {
                        "loaded": ranker is not None,
                        "mode": getattr(ranker, "mode", None),
                        "features": len(engine.FEATURE_ORDER),
                        "metrics": metrics.get("ranker", {}).get("metrics", {}),
                    },
                    "collaborative_filter": {
                        "loaded": cf is not None,
                        "photographers": len(cf["photographer_ids"]) if cf else 0,
                        "metrics": metrics.get("cf", {}).get("metrics", {}),
                    },
                    "sentiment": {
                        "metrics": metrics.get("sentiment", {}).get("metrics", {}),
                    },
                    "weights": {
                        "content": settings.REC_WEIGHT_CONTENT,
                        "collaborative": settings.REC_WEIGHT_COLLAB,
                        "business": settings.REC_WEIGHT_BUSINESS,
                    },
                    "exploration_slots": settings.REC_EXPLORATION_SLOTS,
                    "cache_ttl_seconds": settings.REC_CACHE_TTL_SECONDS,
                },
            }
        )
