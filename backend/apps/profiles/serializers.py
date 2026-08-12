"""
Photographer serializers.

TWO SHAPES, DELIBERATELY
------------------------
`PhotographerListSerializer` is what a card needs — about 20 fields.
`PhotographerDetailSerializer` adds bio, services, portfolio and reviews.

Serving the detail shape on a 20-row list would send roughly 15× the bytes,
most of which the card never draws. On a 3G connection in Pakistan that is
the difference between a list that appears instantly and one that visibly
stalls.
"""

from decimal import Decimal

from rest_framework import serializers

from apps.catalog.models import Category
from apps.catalog.serializers import (
    CategoryMiniSerializer,
    ServiceSerializer,
    SpecializationSerializer,
)
from apps.profiles.models import (
    BuyerProfile,
    PhotographerProfile,
    TopUpRequest,
    Wallet,
    WalletTransaction,
)


def _absolute(request, file_field) -> str | None:
    if not file_field:
        return None
    url = file_field.url
    return request.build_absolute_uri(url) if request else url


class PhotographerListSerializer(serializers.ModelSerializer):
    """Card payload."""

    display_name = serializers.CharField(read_only=True)
    city = serializers.CharField(source="user.city", read_only=True)
    avatar_url = serializers.SerializerMethodField()
    cover_image_url = serializers.SerializerMethodField()
    categories = CategoryMiniSerializer(many=True, read_only=True)
    service_count = serializers.IntegerField(read_only=True, default=0)
    distance_km = serializers.FloatField(read_only=True, required=False, allow_null=True)
    is_wishlisted = serializers.SerializerMethodField()

    class Meta:
        model = PhotographerProfile
        fields = (
            "id", "display_name", "business_name", "tagline",
            "avatar_url", "cover_image_url", "city",
            "base_price", "avg_rating", "bayesian_rating", "reviews_count",
            "years_experience", "completed_bookings",
            "is_verified", "is_featured", "is_accepting_bookings",
            "categories", "service_count", "distance_km", "is_wishlisted",
        )

    def get_avatar_url(self, obj) -> str | None:
        return _absolute(self.context.get("request"), obj.user.avatar)

    def get_cover_image_url(self, obj) -> str | None:
        return _absolute(self.context.get("request"), obj.cover_image)

    def get_is_wishlisted(self, obj) -> bool:
        """
        Reads from a set the view prepared in one query.

        Checking the wishlist per row would fire one query per card. The view
        loads the caller's wishlisted ids once and puts them in context.
        """
        ids = self.context.get("wishlisted_ids")
        return obj.pk in ids if ids else False


class PhotographerReviewSerializer(serializers.Serializer):
    """Inline review summary for the detail screen."""

    id = serializers.IntegerField()
    rating = serializers.IntegerField()
    title = serializers.CharField()
    comment = serializers.CharField()
    created_at = serializers.DateTimeField()
    buyer_name = serializers.SerializerMethodField()
    buyer_avatar = serializers.SerializerMethodField()
    reply = serializers.SerializerMethodField()
    helpful_count = serializers.IntegerField()

    def get_buyer_name(self, obj) -> str:
        return obj.buyer.full_name

    def get_buyer_avatar(self, obj) -> str | None:
        return _absolute(self.context.get("request"), obj.buyer.avatar)

    def get_reply(self, obj) -> dict | None:
        reply = getattr(obj, "reply", None)
        if reply is None:
            return None
        return {"comment": reply.comment, "created_at": reply.created_at}


class PortfolioPreviewSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    caption = serializers.CharField()
    is_featured = serializers.BooleanField()
    image_url = serializers.SerializerMethodField()
    thumbnail_url = serializers.SerializerMethodField()

    def get_image_url(self, obj) -> str | None:
        return _absolute(self.context.get("request"), obj.image)

    def get_thumbnail_url(self, obj) -> str | None:
        return _absolute(self.context.get("request"), obj.thumbnail or obj.image)


class PhotographerDetailSerializer(PhotographerListSerializer):
    """Everything the profile screen renders, in one response."""

    services = ServiceSerializer(many=True, read_only=True)
    specializations = SpecializationSerializer(many=True, read_only=True)
    portfolio = serializers.SerializerMethodField()
    recent_reviews = serializers.SerializerMethodField()
    rating_breakdown = serializers.SerializerMethodField()
    response_time_label = serializers.SerializerMethodField()

    class Meta(PhotographerListSerializer.Meta):
        fields = PhotographerListSerializer.Meta.fields + (
            "bio", "equipment", "languages", "travel_available",
            "service_radius_km", "website", "instagram", "facebook",
            "success_rate", "avg_response_time_hours", "response_time_label",
            "portfolio_score", "profile_views", "total_bookings",
            "services", "specializations", "portfolio", "recent_reviews",
            "rating_breakdown",
        )

    def get_portfolio(self, obj) -> list:
        images = getattr(obj, "preview_images", [])
        return PortfolioPreviewSerializer(images, many=True, context=self.context).data

    def get_recent_reviews(self, obj) -> list:
        reviews = getattr(obj, "recent_reviews", [])
        return PhotographerReviewSerializer(reviews, many=True, context=self.context).data

    def get_rating_breakdown(self, obj) -> dict:
        """
        Star histogram — one aggregate query, not five.

        A 4.6 average built from mostly 5s with two 1s tells a very different
        story from a 4.6 built entirely from 4s and 5s, and buyers read that
        distribution before they read the number.
        """
        from django.db.models import Count

        from apps.reviews.models import Review

        rows = (
            Review.objects.visible()
            .filter(photographer=obj)
            .values("rating")
            .annotate(count=Count("id"))
        )
        breakdown = {str(star): 0 for star in range(1, 6)}
        for row in rows:
            breakdown[str(row["rating"])] = row["count"]
        return breakdown

    def get_response_time_label(self, obj) -> str:
        """Hours are engineering data; buyers want "replies within an hour"."""
        hours = float(obj.avg_response_time_hours or 0)
        if hours <= 1:
            return "Replies within an hour"
        if hours <= 6:
            return f"Replies in ~{int(hours)} hours"
        if hours <= 24:
            return "Replies within a day"
        if hours <= 48:
            return "Replies within 2 days"
        return "Replies in a few days"


class BuyerProfileSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(source="user.full_name", read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)
    city = serializers.CharField(source="user.city", read_only=True)
    preferred_categories = CategoryMiniSerializer(many=True, read_only=True)
    wallet_balance = serializers.SerializerMethodField()

    class Meta:
        model = BuyerProfile
        fields = (
            "id", "full_name", "email", "city",
            "preferred_categories", "budget_min", "budget_max",
            "total_bookings", "completed_bookings", "cancelled_bookings",
            "total_spent", "reviews_written", "wallet_balance",
        )
        read_only_fields = (
            "total_bookings", "completed_bookings", "cancelled_bookings",
            "total_spent", "reviews_written",
        )

    def get_wallet_balance(self, obj) -> str:
        from apps.profiles.selectors import wallet_balance

        # Read from the database, not `user.wallet` — see the selector for why
        # the cached relation can be stale.
        return str(wallet_balance(obj.user))


# ═══════════════════════════════════════════════════════════════════════════
# MODULE 4 — the buyer's own account
# ═══════════════════════════════════════════════════════════════════════════
class BuyerProfileUpdateSerializer(serializers.ModelSerializer):
    """
    The writable half of a buyer profile.

    Counters (`total_bookings`, `total_spent`, …) are absent on purpose: they
    are derived from bookings and orders, and a client that could set them
    could rewrite its own spending history.
    """

    preferred_categories = serializers.PrimaryKeyRelatedField(
        many=True, required=False, queryset=Category.objects.filter(is_active=True)
    )

    class Meta:
        model = BuyerProfile
        fields = ("preferred_categories", "budget_min", "budget_max")

    def validate(self, attrs):
        low = attrs.get("budget_min", getattr(self.instance, "budget_min", None))
        high = attrs.get("budget_max", getattr(self.instance, "budget_max", None))
        if low is not None and high is not None and low > high:
            raise serializers.ValidationError(
                {"budget_max": "Maximum budget cannot be below the minimum."}
            )
        return attrs


class WalletTransactionSerializer(serializers.ModelSerializer):
    """One line of the ledger."""

    type_label = serializers.CharField(source="get_txn_type_display", read_only=True)
    direction = serializers.SerializerMethodField()

    class Meta:
        model = WalletTransaction
        fields = (
            "id", "txn_type", "type_label", "direction", "amount",
            "balance_before", "balance_after", "reference", "description",
            "created_at",
        )

    def get_direction(self, obj) -> str:
        """
        "in" or "out", so the app colours the row without knowing what an
        EARNING is versus a PURCHASE.
        """
        return "out" if obj.balance_after < obj.balance_before else "in"


class WalletSerializer(serializers.ModelSerializer):
    recent_transactions = serializers.SerializerMethodField()
    pending_topups = serializers.SerializerMethodField()

    class Meta:
        model = Wallet
        fields = (
            "balance", "total_credited", "total_debited",
            "recent_transactions", "pending_topups",
        )

    def get_recent_transactions(self, obj) -> list:
        rows = self.context.get("recent_transactions", [])
        return WalletTransactionSerializer(rows, many=True).data

    def get_pending_topups(self, obj) -> int:
        return self.context.get("pending_topups", 0)


class TopUpRequestSerializer(serializers.ModelSerializer):
    """A bank receipt awaiting admin verification."""

    status_label = serializers.CharField(source="get_status_display", read_only=True)
    receipt_url = serializers.SerializerMethodField()

    class Meta:
        model = TopUpRequest
        fields = (
            "id", "amount", "method", "transaction_reference",
            "receipt_image", "receipt_url", "status", "status_label",
            "admin_note", "reviewed_at", "created_at",
        )
        read_only_fields = ("status", "admin_note", "reviewed_at")
        extra_kwargs = {"receipt_image": {"write_only": True, "required": True}}

    def get_receipt_url(self, obj) -> str | None:
        return _absolute(self.context.get("request"), obj.receipt_image)

    def validate_amount(self, value):
        if value < Decimal("100"):
            raise serializers.ValidationError("The minimum top-up is Rs 100.")
        if value > Decimal("500000"):
            raise serializers.ValidationError(
                "For amounts above Rs 500,000 please contact support."
            )
        return value

    def validate_transaction_reference(self, value):
        value = value.strip()
        if len(value) < 4:
            raise serializers.ValidationError(
                "Enter the reference number printed on your transfer receipt."
            )
        return value


# ═══════════════════════════════════════════════════════════════════════════
# The photographer's own profile
# ═══════════════════════════════════════════════════════════════════════════
class PhotographerSelfSerializer(PhotographerDetailSerializer):
    """
    What a photographer sees on their own Profile tab.

    Extends the public detail shape with the two things only they may see:
    lifetime earnings, and whether the admin has approved them yet.
    """

    total_earnings = serializers.DecimalField(
        max_digits=14, decimal_places=2, read_only=True
    )
    wallet_balance = serializers.SerializerMethodField()

    class Meta(PhotographerDetailSerializer.Meta):
        fields = PhotographerDetailSerializer.Meta.fields + (
            "is_approved", "submitted_for_approval_at", "rejection_reason",
            "total_earnings", "wallet_balance",
        )

    def get_wallet_balance(self, obj) -> str:
        from apps.profiles.selectors import wallet_balance

        # Read from the database, not `user.wallet` — see the selector for why
        # the cached relation can be stale.
        return str(wallet_balance(obj.user))


class PhotographerSelfUpdateSerializer(serializers.ModelSerializer):
    """
    Writable subset.

    `is_approved`, `is_verified`, `is_featured` and every denormalised metric
    are deliberately absent — including them would let a photographer approve
    and feature themselves by adding one line to the request body.

    `is_accepting_bookings` is here because Module 7 reads it on every booking
    attempt: a photographer with no way to pause is one who has to decline by
    hand, and declines count against their success rate.
    """

    class Meta:
        model = PhotographerProfile
        fields = (
            "business_name", "tagline", "bio", "years_experience",
            "base_price", "travel_available", "service_radius_km",
            "equipment", "languages", "website", "instagram", "facebook",
            "is_accepting_bookings",
        )

    def validate_base_price(self, value):
        if value < 0:
            raise serializers.ValidationError("Price cannot be negative.")
        return value

    def validate_bio(self, value):
        value = (value or "").strip()
        if value and len(value) < 50:
            raise serializers.ValidationError(
                "A bio needs at least 50 characters to be useful to buyers."
            )
        return value
