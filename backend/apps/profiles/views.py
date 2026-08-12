"""Photographer discovery, plus the caller's own profile and wallet."""

from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status as http
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet, ReadOnlyModelViewSet

from apps.core.mixins import MessageResponseMixin, MultiSerializerMixin
from apps.profiles import selectors, services
from apps.profiles.filters import PhotographerFilterSet
from apps.profiles.models import BuyerProfile, TopUpRequest, Wallet, WalletTransaction
from apps.profiles.serializers import (
    BuyerProfileSerializer,
    BuyerProfileUpdateSerializer,
    PhotographerDetailSerializer,
    PhotographerListSerializer,
    PhotographerSelfSerializer,
    PhotographerSelfUpdateSerializer,
    TopUpRequestSerializer,
    WalletSerializer,
    WalletTransactionSerializer,
)


@extend_schema(tags=["Profiles"])
class PhotographerViewSet(
    MessageResponseMixin, MultiSerializerMixin, ReadOnlyModelViewSet
):
    """
    Browse, search and filter photographers.

    Public by design: discovery is the top of the funnel, and forcing a login
    before a buyer can see who is on the platform is the fastest way to lose
    them. Personalised fields (`is_wishlisted`) simply stay false for
    anonymous callers.
    """

    permission_classes = [AllowAny]
    serializer_class = PhotographerListSerializer
    serializer_classes = {
        "retrieve": PhotographerDetailSerializer,
        "featured": PhotographerListSerializer,
        "trending": PhotographerListSerializer,
    }
    filter_backends = [DjangoFilterBackend]
    filterset_class = PhotographerFilterSet
    throttle_scope = "search"
    success_messages = {
        "list": "Photographers retrieved",
        "retrieve": "Photographer profile retrieved",
        "featured": "Featured photographers retrieved",
        "trending": "Trending photographers retrieved",
    }

    def get_queryset(self):
        return selectors.photographers_for_list().order_by(
            "-is_featured", "-bayesian_rating", "-completed_bookings"
        )

    def get_serializer_context(self):
        """
        Load the caller's wishlist once, not once per row.

        Without this, `is_wishlisted` on a 20-row page fires 20 queries. With
        it, one — and anonymous callers cost nothing at all.
        """
        context = super().get_serializer_context()
        user = self.request.user
        if user.is_authenticated:
            from apps.wishlist.models import WishlistItem

            context["wishlisted_ids"] = set(
                WishlistItem.objects.filter(
                    user=user, photographer__isnull=False
                ).values_list("photographer_id", flat=True)
            )
        return context

    # ─── List, with the distance filter layered on ───────────────────────────
    @extend_schema(
        parameters=[
            OpenApiParameter("q", str, description="Free-text search"),
            OpenApiParameter("category", str, description="Category slug"),
            OpenApiParameter("city", str),
            OpenApiParameter("min_price", float),
            OpenApiParameter("max_price", float),
            OpenApiParameter("min_rating", float),
            OpenApiParameter("min_experience", int),
            OpenApiParameter("available_on", str, description="YYYY-MM-DD"),
            OpenApiParameter("lat", float, description="Caller latitude"),
            OpenApiParameter("lng", float, description="Caller longitude"),
            OpenApiParameter("radius_km", float, description="Requires lat and lng"),
            OpenApiParameter(
                "ordering", str,
                description="rating | price | experience | popularity | reviews | newest "
                            "(prefix with '-' to reverse)",
            ),
        ]
    )
    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())

        lat, lng, radius = self._geo_params(request)
        if lat is not None and lng is not None and radius:
            queryset = selectors.filter_by_radius(queryset, lat, lng, radius)

        page = self.paginate_queryset(queryset)
        rows = page if page is not None else list(queryset)

        if lat is not None and lng is not None:
            rows = selectors.annotate_distance(rows, lat, lng)
            # Sort by proximity only when the caller did not ask for another
            # order — an explicit ?ordering= must always win.
            if not request.query_params.get("ordering"):
                rows.sort(key=lambda p: (p.distance_km is None, p.distance_km or 0))

        serializer = self.get_serializer(rows, many=True)
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)

    @staticmethod
    def _geo_params(request):
        def as_float(key):
            raw = request.query_params.get(key)
            try:
                return float(raw) if raw not in (None, "") else None
            except (TypeError, ValueError):
                return None

        return as_float("lat"), as_float("lng"), as_float("radius_km")

    # ─── Detail ──────────────────────────────────────────────────────────────
    def retrieve(self, request, *args, **kwargs):
        photographer = selectors.photographer_detail(kwargs["pk"])
        if photographer is None:
            from rest_framework.exceptions import NotFound

            raise NotFound("This photographer is not available.")

        # Fire-and-forget view counter. F() avoids a read-modify-write race
        # when several buyers open the same profile at once.
        from django.db.models import F

        from apps.profiles.models import PhotographerProfile

        PhotographerProfile.objects.filter(pk=photographer.pk).update(
            profile_views=F("profile_views") + 1
        )
        self._log_interaction(request, photographer)

        serializer = self.get_serializer(photographer)
        return Response(serializer.data)

    def _log_interaction(self, request, photographer) -> None:
        """
        Record the view as implicit feedback for collaborative filtering.

        Wrapped in a broad try/except deliberately: analytics must never be
        able to break the screen a user is trying to look at.
        """
        if not request.user.is_authenticated or request.user.role != "BUYER":
            return
        try:
            from apps.recommendations.models import BuyerInteraction, BuyerInteractionType

            BuyerInteraction.objects.create(
                buyer=request.user,
                photographer=photographer,
                interaction_type=BuyerInteractionType.VIEW,
                category=photographer.categories.first(),
            )
        except Exception:  # noqa: BLE001
            pass

    # ─── Curated collections ─────────────────────────────────────────────────
    @extend_schema(summary="Editorially featured photographers")
    @action(detail=False, methods=["get"], pagination_class=None)
    def featured(self, request):
        rows = selectors.featured_photographers(limit=10)
        return Response(self.get_serializer(rows, many=True).data)

    @extend_schema(summary="Trending photographers, optionally near a city")
    @action(detail=False, methods=["get"], pagination_class=None)
    def trending(self, request):
        city = request.query_params.get("city") or (
            request.user.city if request.user.is_authenticated else None
        )
        rows = selectors.trending_photographers(city=city, limit=10)
        return Response(self.get_serializer(rows, many=True).data)

    @extend_schema(summary="Filter values available to the search UI")
    @action(detail=False, methods=["get"], permission_classes=[AllowAny])
    def filters(self, request):
        """
        Powers the filter sheet: real cities and the true price range.

        Hard-coding a "Rs 0 – 200,000" slider would be wrong the moment a
        photographer prices outside it. These bounds come from the data.
        """
        from django.db.models import Count, Max, Min

        from apps.catalog.selectors import get_active_categories

        base = selectors.visible_photographers()
        price = base.aggregate(min=Min("base_price"), max=Max("base_price"))
        cities = (
            base.values("user__city")
            .annotate(count=Count("id"))
            .filter(count__gt=0)
            .order_by("-count")
        )

        return Response(
            {
                "categories": [
                    {"slug": c.slug, "name": c.name, "count": c.photographer_count}
                    for c in get_active_categories()
                ],
                "cities": [
                    {"name": row["user__city"], "count": row["count"]}
                    for row in cities
                    if row["user__city"]
                ],
                "price_range": {
                    "min": float(price["min"] or 0),
                    "max": float(price["max"] or 0),
                },
                "sort_options": [
                    {"value": "-rating", "label": "Highest rated"},
                    {"value": "price", "label": "Price: low to high"},
                    {"value": "-price", "label": "Price: high to low"},
                    {"value": "-experience", "label": "Most experienced"},
                    {"value": "-popularity", "label": "Most booked"},
                    {"value": "-newest", "label": "Newest"},
                ],
            }
        )


# ═══════════════════════════════════════════════════════════════════════════
# MODULE 4 — THE CALLER'S OWN PROFILE
#
# Account fields (name, phone, city, avatar) already live at /auth/me/. This
# viewset owns the ROLE-SPECIFIC half: a buyer's preferences and budget, or a
# photographer's public listing. Duplicating the account fields here would
# give two endpoints that can disagree about the same row.
# ═══════════════════════════════════════════════════════════════════════════
@extend_schema(tags=["Profiles"])
class MyProfileViewSet(MessageResponseMixin, MultiSerializerMixin, GenericViewSet):
    """The signed-in user's own profile, whichever role they hold."""

    permission_classes = [IsAuthenticated]
    serializer_class = BuyerProfileSerializer
    pagination_class = None
    # This viewset is polymorphic — it serves a buyer profile or a
    # photographer one depending on the caller. The buyer shape is the
    # default, so it is what the schema documents.
    queryset = BuyerProfile.objects.none()
    success_messages = {
        "list": "Profile retrieved",
        "update_profile": "Profile updated",
    }

    def _is_photographer(self) -> bool:
        return getattr(self.request.user, "photographer_profile", None) is not None

    @extend_schema(summary="The caller's role-specific profile")
    def list(self, request):
        context = {"request": request}
        if self._is_photographer():
            profile = selectors.photographer_self(request.user)
            return Response(PhotographerSelfSerializer(profile, context=context).data)

        from apps.profiles.models import BuyerProfile

        profile, _ = BuyerProfile.objects.get_or_create(user=request.user)
        return Response(BuyerProfileSerializer(profile, context=context).data)

    @extend_schema(
        summary="Update the caller's profile",
        request=PhotographerSelfUpdateSerializer,
    )
    @action(detail=False, methods=["patch"], url_path="update")
    def update_profile(self, request):
        context = {"request": request}

        if self._is_photographer():
            profile = request.user.photographer_profile
            serializer = PhotographerSelfUpdateSerializer(
                profile, data=request.data, partial=True, context=context
            )
            serializer.is_valid(raise_exception=True)
            updated = services.update_photographer_profile(
                profile, **serializer.validated_data
            )
            fresh = selectors.photographer_self(request.user) or updated
            return Response(PhotographerSelfSerializer(fresh, context=context).data)

        serializer = BuyerProfileUpdateSerializer(
            data=request.data, partial=True, context=context
        )
        serializer.is_valid(raise_exception=True)
        profile = services.update_buyer_profile(
            request.user, **serializer.validated_data
        )
        return Response(BuyerProfileSerializer(profile, context=context).data)


@extend_schema(tags=["Profiles"])
class WalletViewSet(MessageResponseMixin, MultiSerializerMixin, GenericViewSet):
    """
    Balance, ledger and top-up requests.

    The proposal excludes a payment gateway, so money enters the platform
    exactly one way: the user transfers it, uploads the receipt, and an admin
    verifies it. Nothing here credits a balance — see
    `profiles.services.approve_topup`, which is the only path that does.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = WalletSerializer
    serializer_classes = {
        "transactions": WalletTransactionSerializer,
        "topups": TopUpRequestSerializer,
        "request_topup": TopUpRequestSerializer,
    }
    pagination_class = None
    parser_classes = [MultiPartParser, FormParser]
    queryset = Wallet.objects.none()  # schema inference only
    success_messages = {
        "list": "Wallet retrieved",
        "transactions": "Transactions retrieved",
        "topups": "Top-up requests retrieved",
        "request_topup": "Top-up submitted — an admin will verify your receipt",
    }

    def _wallet(self) -> Wallet:
        wallet, _ = Wallet.objects.get_or_create(user=self.request.user)
        return wallet

    @extend_schema(summary="Balance plus the last few ledger rows")
    def list(self, request):
        wallet = self._wallet()
        recent = WalletTransaction.objects.filter(wallet=wallet).order_by(
            "-created_at"
        )[:10]
        pending = TopUpRequest.objects.filter(
            user=request.user, status="PENDING"
        ).count()
        return Response(
            WalletSerializer(
                wallet,
                context={
                    "request": request,
                    "recent_transactions": list(recent),
                    "pending_topups": pending,
                },
            ).data
        )

    @extend_schema(
        summary="The full ledger", responses=WalletTransactionSerializer(many=True)
    )
    @action(detail=False, methods=["get"], pagination_class=None)
    def transactions(self, request):
        rows = WalletTransaction.objects.filter(wallet=self._wallet()).order_by(
            "-created_at"
        )[:100]
        return Response(WalletTransactionSerializer(rows, many=True).data)

    @extend_schema(summary="Past and pending top-up requests")
    @action(detail=False, methods=["get"])
    def topups(self, request):
        rows = TopUpRequest.objects.filter(user=request.user).order_by("-created_at")
        return Response(
            TopUpRequestSerializer(
                rows, many=True, context={"request": request}
            ).data
        )

    @extend_schema(
        summary="Submit a transfer receipt for verification",
        request=TopUpRequestSerializer,
        responses={201: TopUpRequestSerializer},
    )
    @action(detail=False, methods=["post"], url_path="topups/request")
    def request_topup(self, request):
        serializer = TopUpRequestSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        topup = services.request_topup(request.user, **serializer.validated_data)
        return Response(
            TopUpRequestSerializer(topup, context={"request": request}).data,
            status=http.HTTP_201_CREATED,
        )
