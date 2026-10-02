"""
Review endpoints — Module 9.

ROUTE SHAPE
-----------
    GET    /reviews/photographers/{id}/          public list  (+ ?rating=&sort=&photos=)
    GET    /reviews/photographers/{id}/summary/  histogram + sub-rating averages
    GET    /reviews/products/{id}/               public product list
    POST   /reviews/                             write one            (buyer)
    GET    /reviews/pending/                     what I can review    (buyer)
    GET    /reviews/mine/                        what I have written  (buyer)
    GET    /reviews/{id}/                        one review
    PATCH  /reviews/{id}/                        correct it, 24h window
    DELETE /reviews/{id}/                        withdraw it
    POST   /reviews/{id}/helpful/                toggle "was this helpful"
    POST   /reviews/{id}/flag/                   report to moderation
    POST   /reviews/{id}/reply/                  photographer's answer
    PATCH  /reviews/{id}/reply/                  edit it
    GET    /reviews/received/                    my inbox   (photographer)
    POST   /reviews/products/                    review a purchase   (buyer)

WHY THE PUBLIC LISTS ARE `AllowAny`
-----------------------------------
Reviews are the single strongest signal a buyer reads before signing up. Putting
them behind a login wall would mean the app's most persuasive screen is only
visible to people already persuaded.

WHY `helpful_ids` IS LOADED IN THE VIEW, NOT THE SERIALIZER
----------------------------------------------------------
`marked_helpful` is per-caller state on every card. Asking the serializer for it
would be one SELECT per row; loading the caller's voted ids for the page in one
query and passing them through context is the same answer for a fixed cost.
"""

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status as http
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from apps.core.mixins import (
    ActionPermissionsMixin,
    MessageResponseMixin,
    MultiSerializerMixin,
)
from apps.core.permissions import IsBuyer, IsPhotographer
from apps.reviews import selectors, services
from apps.reviews.models import ProductReview, Review, ReviewHelpful
from apps.reviews.serializers import (
    HelpfulResponseSerializer,
    OwnedReviewSerializer,
    PendingReviewsSerializer,
    ProductReviewCreateSerializer,
    ProductReviewSerializer,
    ReviewCreateSerializer,
    ReviewFlagSerializer,
    ReviewReplyWriteSerializer,
    ReviewSerializer,
    ReviewSummarySerializer,
    ReviewUpdateSerializer,
)


@extend_schema(tags=["Reviews"])
class ReviewViewSet(
    MessageResponseMixin,
    MultiSerializerMixin,
    ActionPermissionsMixin,
    GenericViewSet,
):
    permission_classes = [IsAuthenticated]
    serializer_class = ReviewSerializer
    serializer_classes = {
        "create": ReviewCreateSerializer,
        "partial_update": ReviewUpdateSerializer,
        "reply": ReviewReplyWriteSerializer,
        "update_reply": ReviewReplyWriteSerializer,
        "flag": ReviewFlagSerializer,
        "create_product_review": ProductReviewCreateSerializer,
    }
    action_permissions = {
        "for_photographer": [AllowAny],
        "photographer_summary": [AllowAny],
        "for_product": [AllowAny],
        "product_summary": [AllowAny],
        # A review opened from a shared link is public for the same reason the
        # list is: it is the screen that persuades people to sign up.
        "retrieve": [AllowAny],
        "create": [IsAuthenticated, IsBuyer],
        "create_product_review": [IsAuthenticated, IsBuyer],
        "pending": [IsAuthenticated, IsBuyer],
        "mine": [IsAuthenticated, IsBuyer],
        "received": [IsAuthenticated, IsPhotographer],
    }
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    # Schema inference only — every action scopes its own queryset. Without
    # this drf-spectacular warns and degrades the path parameter to a string.
    queryset = Review.objects.none()
    success_messages = {
        "create": "Thanks — your review is live",
        "partial_update": "Review updated",
        "destroy": "Review withdrawn",
        "reply": "Reply posted",
        "update_reply": "Reply updated",
        "flag": "Reported — our team will take a look",
        "helpful": "Thanks for the feedback",
        "create_product_review": "Thanks — your review is live",
    }

    # ─── Context ─────────────────────────────────────────────────────────────
    def get_serializer_context(self):
        context = super().get_serializer_context()
        context.setdefault("helpful_ids", getattr(self, "_helpful_ids", None))
        return context

    def _with_helpful(self, rows):
        """
        Load which of these reviews the caller already found helpful.

        One query for the whole page. Skipped entirely for anonymous callers,
        who have no votes to load.
        """
        user = self.request.user
        if user.is_authenticated and rows:
            self._helpful_ids = set(
                ReviewHelpful.objects.filter(
                    user=user, review_id__in=[r.pk for r in rows]
                ).values_list("review_id", flat=True)
            )
        else:
            self._helpful_ids = set()
        return rows

    def _paginated(self, queryset, serializer_class=None):
        serializer_class = serializer_class or ReviewSerializer
        page = self.paginate_queryset(queryset)
        rows = self._with_helpful(list(page if page is not None else queryset))
        data = serializer_class(
            rows, many=True, context=self.get_serializer_context()
        ).data
        if page is not None:
            return self.get_paginated_response(data)
        return Response(data)

    def _review(self, pk) -> Review:
        review = selectors.get_review(pk)
        if review is None:
            raise NotFound("Review not found.")
        return review

    def _own_review(self, pk) -> Review:
        """The caller's own review, or a 404 — never a 403 naming someone else's."""
        review = self._review(pk)
        if review.buyer_id != self.request.user.id:
            raise NotFound("Review not found.")
        return review

    def _profile(self):
        profile = getattr(self.request.user, "photographer_profile", None)
        if profile is None:
            raise NotFound("Only photographer accounts receive reviews.")
        return profile

    # ═══════════════════════════════════════════════════════════════════════
    # PUBLIC READS
    # ═══════════════════════════════════════════════════════════════════════
    @extend_schema(
        summary="Reviews for one photographer",
        parameters=[
            OpenApiParameter("rating", int, description="Only this star rating"),
            OpenApiParameter(
                "sort", str,
                description="recent | oldest | helpful | highest | lowest",
            ),
            OpenApiParameter(
                "photos", bool, description="Only reviews that carry photos"
            ),
        ],
        responses=ReviewSerializer(many=True),
    )
    @action(
        detail=False, methods=["get"],
        url_path=r"photographers/(?P<photographer_id>\d+)",
    )
    def for_photographer(self, request, photographer_id=None):
        rating = request.query_params.get("rating")
        queryset = selectors.photographer_reviews(
            int(photographer_id),
            rating=int(rating) if rating and rating.isdigit() else None,
            with_photos=request.query_params.get("photos") in ("1", "true", "True"),
            sort=request.query_params.get("sort", "recent"),
        )
        return self._paginated(queryset)

    @extend_schema(
        summary="Star histogram, sub-rating averages and recommend rate",
        responses=ReviewSummarySerializer,
    )
    @action(
        detail=False, methods=["get"],
        url_path=r"photographers/(?P<photographer_id>\d+)/summary",
    )
    def photographer_summary(self, request, photographer_id=None):
        return Response(selectors.review_summary(int(photographer_id)))

    @extend_schema(
        summary="Reviews for one marketplace product",
        responses=ProductReviewSerializer(many=True),
    )
    @action(
        detail=False, methods=["get"], url_path=r"products/(?P<product_id>\d+)"
    )
    def for_product(self, request, product_id=None):
        queryset = selectors.product_reviews(
            int(product_id), sort=request.query_params.get("sort", "recent")
        )
        page = self.paginate_queryset(queryset)
        rows = list(page if page is not None else queryset)
        data = ProductReviewSerializer(
            rows, many=True, context=self.get_serializer_context()
        ).data
        return (
            self.get_paginated_response(data) if page is not None else Response(data)
        )

    @extend_schema(summary="Rating summary for one product")
    @action(
        detail=False, methods=["get"],
        url_path=r"products/(?P<product_id>\d+)/summary",
    )
    def product_summary(self, request, product_id=None):
        return Response(selectors.product_review_summary(int(product_id)))

    @extend_schema(summary="One review", responses=ReviewSerializer)
    def retrieve(self, request, pk=None):
        review = self._review(pk)
        self._with_helpful([review])
        return Response(
            ReviewSerializer(review, context=self.get_serializer_context()).data
        )

    # ═══════════════════════════════════════════════════════════════════════
    # BUYER WRITES
    # ═══════════════════════════════════════════════════════════════════════
    @extend_schema(
        summary="Review a completed booking",
        request=ReviewCreateSerializer,
        responses={201: ReviewSerializer},
    )
    def create(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        booking = data.pop("booking", None)
        photographer = data.pop("photographer_id", None)

        review = services.create_review(
            booking, request.user, photographer=photographer, **data
        )
        return Response(
            ReviewSerializer(review, context=self.get_serializer_context()).data,
            status=http.HTTP_201_CREATED,
        )

    @extend_schema(
        summary="Correct your review — 24h, and only before a reply exists",
        request=ReviewUpdateSerializer,
        responses=ReviewSerializer,
    )
    def partial_update(self, request, pk=None):
        review = self._own_review(pk)
        serializer = self.get_serializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        updated = services.update_review(review, **serializer.validated_data)
        return Response(
            ReviewSerializer(updated, context=self.get_serializer_context()).data
        )

    @extend_schema(summary="Withdraw your review", responses={204: None})
    def destroy(self, request, pk=None):
        services.delete_review(self._own_review(pk))
        return Response(status=http.HTTP_204_NO_CONTENT)

    @extend_schema(
        summary="What you can review right now", responses=PendingReviewsSerializer
    )
    @action(detail=False, methods=["get"])
    def pending(self, request):
        return Response(
            PendingReviewsSerializer(
                selectors.pending_for_user(request.user),
                context=self.get_serializer_context(),
            ).data
        )

    @extend_schema(summary="Reviews you have written", responses=ReviewSerializer(many=True))
    @action(detail=False, methods=["get"])
    def mine(self, request):
        return self._paginated(selectors.reviews_written_by(request.user))

    # ═══════════════════════════════════════════════════════════════════════
    # ENGAGEMENT & MODERATION
    # ═══════════════════════════════════════════════════════════════════════
    @extend_schema(
        summary='Toggle "was this helpful"', request=None,
        responses=HelpfulResponseSerializer,
    )
    @action(detail=True, methods=["post"])
    def helpful(self, request, pk=None):
        marked, count = services.toggle_helpful(self._review(pk), request.user)
        return Response({"marked_helpful": marked, "helpful_count": count})

    @extend_schema(
        summary="Report a review to moderation", request=ReviewFlagSerializer
    )
    @action(detail=True, methods=["post"])
    def flag(self, request, pk=None):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        flag = services.flag_review(
            self._review(pk),
            request.user,
            reason=serializer.validated_data["reason"],
            detail=serializer.validated_data.get("detail", ""),
        )
        return Response({"flag_id": flag.pk, "status": flag.status})

    # ═══════════════════════════════════════════════════════════════════════
    # PHOTOGRAPHER SIDE
    # ═══════════════════════════════════════════════════════════════════════
    @extend_schema(
        summary="Reviews you have received",
        parameters=[
            OpenApiParameter(
                "unanswered", bool, description="Only ones you have not replied to"
            )
        ],
        responses=OwnedReviewSerializer(many=True),
    )
    @action(detail=False, methods=["get"])
    def received(self, request):
        queryset = selectors.reviews_received_by(
            self._profile(),
            unanswered_only=request.query_params.get("unanswered")
            in ("1", "true", "True"),
        )
        return self._paginated(queryset, OwnedReviewSerializer)

    @extend_schema(
        summary="Reply publicly to a review you received",
        request=ReviewReplyWriteSerializer,
        responses={201: ReviewSerializer},
    )
    @action(detail=True, methods=["post", "patch"])
    def reply(self, request, pk=None):
        review = self._review(pk)
        profile = self._profile()
        if review.photographer_id != profile.pk:
            raise PermissionDenied("You can only reply to your own reviews.")

        serializer = ReviewReplyWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        comment = serializer.validated_data["comment"]

        if request.method == "PATCH":
            existing = getattr(review, "reply", None)
            if existing is None:
                raise NotFound("You have not replied to this review yet.")
            services.update_reply(existing, comment)
            created = False
        else:
            services.reply_to_review(review, profile, comment)
            created = True

        review.refresh_from_db()
        return Response(
            OwnedReviewSerializer(review, context=self.get_serializer_context()).data,
            status=http.HTTP_201_CREATED if created else http.HTTP_200_OK,
        )

    # ═══════════════════════════════════════════════════════════════════════
    # PRODUCT REVIEWS
    # ═══════════════════════════════════════════════════════════════════════
    @extend_schema(
        summary="Review a product you bought",
        request=ProductReviewCreateSerializer,
        responses={201: ProductReviewSerializer},
    )
    @action(detail=False, methods=["post"], url_path="products")
    def create_product_review(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        order_item = data.pop("order_item")

        review = services.create_product_review(order_item, request.user, **data)
        return Response(
            ProductReviewSerializer(
                review, context=self.get_serializer_context()
            ).data,
            status=http.HTTP_201_CREATED,
        )

    @extend_schema(
        summary="Product reviews you have written",
        responses=ProductReviewSerializer(many=True),
    )
    @action(detail=False, methods=["get"], url_path="products/mine")
    def my_product_reviews(self, request):
        queryset = selectors.product_reviews_written_by(request.user)
        page = self.paginate_queryset(queryset)
        rows = list(page if page is not None else queryset)
        data = ProductReviewSerializer(
            rows, many=True, context=self.get_serializer_context()
        ).data
        return (
            self.get_paginated_response(data) if page is not None else Response(data)
        )

    @extend_schema(summary="Withdraw a product review", responses={204: None})
    @action(
        detail=False, methods=["delete"],
        url_path=r"products/(?P<review_id>\d+)/remove",
    )
    def delete_product_review(self, request, review_id=None):
        review = ProductReview.objects.filter(
            pk=int(review_id), buyer=request.user, is_deleted=False
        ).first()
        if review is None:
            raise NotFound("Review not found.")
        services.delete_product_review(review)
        return Response(status=http.HTTP_204_NO_CONTENT)
