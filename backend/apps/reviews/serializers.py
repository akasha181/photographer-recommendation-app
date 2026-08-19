"""
Review serializers.

WHY THE WRITE SERIALIZER TAKES `booking`, NOT `photographer`
-----------------------------------------------------------
The client never names who is being reviewed. It names the booking, and the
photographer is derived from it server-side. Accepting `photographer` would
mean trusting the client to pair a booking with the right profile, which is
exactly the mass-assignment hole `fields = "__all__"` opens elsewhere.

WHY VALIDATION IS DUPLICATED IN THE SERVICE
-------------------------------------------
This layer exists to produce a friendly, field-attributed error before any
write happens. `services.create_review` re-checks the same rules inside the
transaction because two concurrent submits both pass validation here. Neither
layer is redundant: this one is for humans, that one is for races.
"""

from rest_framework import serializers

from apps.reviews.models import ProductReview, Review, ReviewImage, ReviewReply


def _absolute(request, filefield) -> str | None:
    """Storage paths are relative; the app needs a URL it can fetch."""
    if not filefield:
        return None
    try:
        url = filefield.url
    except (ValueError, NotImplementedError):
        return None
    return request.build_absolute_uri(url) if request else url


# ═══════════════════════════════════════════════════════════════════════════
# READ
# ═══════════════════════════════════════════════════════════════════════════
class ReviewImageSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()
    thumbnail_url = serializers.SerializerMethodField()

    class Meta:
        model = ReviewImage
        fields = ("id", "caption", "image_url", "thumbnail_url")

    def get_image_url(self, obj) -> str | None:
        return _absolute(self.context.get("request"), obj.image)

    def get_thumbnail_url(self, obj) -> str | None:
        return _absolute(self.context.get("request"), obj.thumbnail or obj.image)


class ReviewReplySerializer(serializers.ModelSerializer):
    photographer_name = serializers.SerializerMethodField()

    class Meta:
        model = ReviewReply
        fields = (
            "id", "comment", "is_edited", "photographer_name",
            "created_at", "updated_at",
        )

    def get_photographer_name(self, obj) -> str:
        return obj.photographer.display_name


class ReviewSerializer(serializers.ModelSerializer):
    """
    One review card.

    `sentiment` is deliberately absent from the public shape — see
    `selectors.sentiment_breakdown`. `OwnedReviewSerializer` adds it for the
    photographer who received it.
    """

    buyer_name = serializers.SerializerMethodField()
    buyer_avatar = serializers.SerializerMethodField()
    photographer_id = serializers.IntegerField(read_only=True)
    photographer_name = serializers.SerializerMethodField()
    service_name = serializers.SerializerMethodField()
    images = ReviewImageSerializer(many=True, read_only=True)
    reply = ReviewReplySerializer(read_only=True)
    sub_ratings = serializers.SerializerMethodField()
    marked_helpful = serializers.SerializerMethodField()
    can_edit = serializers.SerializerMethodField()

    class Meta:
        model = Review
        fields = (
            "id", "rating", "title", "comment",
            "buyer_name", "buyer_avatar",
            "photographer_id", "photographer_name", "service_name",
            "sub_ratings", "images", "reply",
            "helpful_count", "marked_helpful", "can_edit",
            "is_hidden", "hidden_reason", "created_at",
        )

    def get_buyer_name(self, obj) -> str:
        return obj.buyer.full_name

    def get_buyer_avatar(self, obj) -> str | None:
        return _absolute(self.context.get("request"), obj.buyer.avatar)

    def get_photographer_name(self, obj) -> str:
        return obj.photographer.display_name

    def get_service_name(self, obj) -> str:
        """
        What was actually shot.

        A five-star review reads very differently under "Wedding — full day"
        than under "Studio portrait, 1 hour", and the booking already carries
        the snapshot.
        """
        return obj.booking.service.title if obj.booking_id else ""

    def get_sub_ratings(self, obj) -> dict:
        return {
            "quality": obj.rating_quality,
            "professionalism": obj.rating_professionalism,
            "communication": obj.rating_communication,
            "value": obj.rating_value,
            "punctuality": obj.rating_punctuality,
        }

    def get_marked_helpful(self, obj) -> bool:
        """
        Whether the caller already voted.

        Reads a set of ids the view loads in ONE query (see
        `ReviewViewSet.get_serializer_context`). Querying per row would be an
        extra SELECT for every card on the screen.
        """
        voted = self.context.get("helpful_ids")
        return obj.pk in voted if voted else False

    def get_can_edit(self, obj) -> bool:
        """
        Server-computed, like `available_actions` on a booking.

        The edit window and the "no reply yet" rule live in `services.py`;
        re-deriving them in TypeScript guarantees the app eventually offers an
        Edit button that always errors.
        """
        from datetime import timedelta

        from django.utils import timezone

        from apps.reviews.services import EDIT_WINDOW_HOURS

        request = self.context.get("request")
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated or obj.buyer_id != user.id:
            return False
        if hasattr(obj, "reply"):
            return False
        return timezone.now() <= obj.created_at + timedelta(hours=EDIT_WINDOW_HOURS)


class OwnedReviewSerializer(ReviewSerializer):
    """The photographer's own view — adds what the model inferred."""

    class Meta(ReviewSerializer.Meta):
        fields = ReviewSerializer.Meta.fields + ("sentiment", "sentiment_score")


class ReviewSummarySerializer(serializers.Serializer):
    """Shape of `selectors.review_summary()`, for the schema."""

    average_rating = serializers.FloatField()
    total_reviews = serializers.IntegerField()
    with_comment = serializers.IntegerField()
    with_photos = serializers.IntegerField()
    recommend_percent = serializers.FloatField()
    breakdown = serializers.DictField(child=serializers.IntegerField())
    sub_ratings = serializers.DictField(allow_null=True)
    sentiment = serializers.DictField(child=serializers.IntegerField())


# ═══════════════════════════════════════════════════════════════════════════
# WRITE
# ═══════════════════════════════════════════════════════════════════════════
class ReviewCreateSerializer(serializers.Serializer):
    booking = serializers.IntegerField()
    rating = serializers.IntegerField(min_value=1, max_value=5)
    title = serializers.CharField(max_length=140, required=False, allow_blank=True)
    comment = serializers.CharField(max_length=3000, required=False, allow_blank=True)

    rating_quality = serializers.IntegerField(
        min_value=1, max_value=5, required=False, allow_null=True
    )
    rating_professionalism = serializers.IntegerField(
        min_value=1, max_value=5, required=False, allow_null=True
    )
    rating_communication = serializers.IntegerField(
        min_value=1, max_value=5, required=False, allow_null=True
    )
    rating_value = serializers.IntegerField(
        min_value=1, max_value=5, required=False, allow_null=True
    )
    rating_punctuality = serializers.IntegerField(
        min_value=1, max_value=5, required=False, allow_null=True
    )

    images = serializers.ListField(
        child=serializers.ImageField(), required=False, allow_empty=True,
        max_length=5,
    )

    def validate_booking(self, value: int):
        """
        Resolve the booking and check eligibility while the field name is still
        attached, so the app can highlight the right thing.
        """
        from apps.bookings.constants import BookingStatus
        from apps.bookings.models import Booking

        user = self.context["request"].user
        booking = (
            Booking.objects.filter(pk=value, buyer=user)
            .select_related("photographer", "photographer__user", "service")
            .first()
        )
        # Same 404-shaped answer whether the booking does not exist or belongs
        # to somebody else: the difference would let a caller enumerate other
        # people's booking ids.
        if booking is None:
            raise serializers.ValidationError("Booking not found.")
        if booking.status != BookingStatus.COMPLETED:
            raise serializers.ValidationError(
                "You can review a shoot once it is marked completed."
            )
        if Review.all_objects.filter(booking=booking).exists():
            raise serializers.ValidationError("You have already reviewed this booking.")
        return booking

    def validate(self, attrs):
        """
        A 1- or 2-star rating must say why.

        Not paternalism: a bare 1★ moves the photographer's average with no
        information attached, and it is the one case where the platform has to
        be able to answer "on what grounds?" if the review is disputed.
        """
        if attrs["rating"] <= 2 and not (attrs.get("comment") or "").strip():
            raise serializers.ValidationError(
                {"comment": "Please tell us what went wrong so we can look into it."}
            )
        return attrs


class ReviewUpdateSerializer(serializers.Serializer):
    rating = serializers.IntegerField(min_value=1, max_value=5, required=False)
    title = serializers.CharField(max_length=140, required=False, allow_blank=True)
    comment = serializers.CharField(max_length=3000, required=False, allow_blank=True)
    rating_quality = serializers.IntegerField(
        min_value=1, max_value=5, required=False, allow_null=True
    )
    rating_professionalism = serializers.IntegerField(
        min_value=1, max_value=5, required=False, allow_null=True
    )
    rating_communication = serializers.IntegerField(
        min_value=1, max_value=5, required=False, allow_null=True
    )
    rating_value = serializers.IntegerField(
        min_value=1, max_value=5, required=False, allow_null=True
    )
    rating_punctuality = serializers.IntegerField(
        min_value=1, max_value=5, required=False, allow_null=True
    )
    images = serializers.ListField(
        child=serializers.ImageField(), required=False, max_length=5
    )


class ReviewReplyWriteSerializer(serializers.Serializer):
    comment = serializers.CharField(max_length=2000)

    def validate_comment(self, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) < 2:
            raise serializers.ValidationError("Write a reply before posting it.")
        return cleaned


class ReviewFlagSerializer(serializers.Serializer):
    reason = serializers.ChoiceField(
        choices=[
            "INAPPROPRIATE", "COPYRIGHT", "SPAM", "FAKE",
            "HARASSMENT", "OFF_PLATFORM", "OTHER",
        ]
    )
    detail = serializers.CharField(max_length=1000, required=False, allow_blank=True)


class HelpfulResponseSerializer(serializers.Serializer):
    marked_helpful = serializers.BooleanField()
    helpful_count = serializers.IntegerField()


# ═══════════════════════════════════════════════════════════════════════════
# PRODUCT REVIEWS
# ═══════════════════════════════════════════════════════════════════════════
class ProductReviewSerializer(serializers.ModelSerializer):
    buyer_name = serializers.SerializerMethodField()
    buyer_avatar = serializers.SerializerMethodField()
    product_title = serializers.SerializerMethodField()
    product_slug = serializers.SerializerMethodField()

    class Meta:
        model = ProductReview
        fields = (
            "id", "rating", "title", "comment", "helpful_count",
            "buyer_name", "buyer_avatar", "product_title", "product_slug",
            "created_at",
        )

    def get_buyer_name(self, obj) -> str:
        return obj.buyer.full_name

    def get_buyer_avatar(self, obj) -> str | None:
        return _absolute(self.context.get("request"), obj.buyer.avatar)

    def get_product_title(self, obj) -> str:
        return obj.product.title

    def get_product_slug(self, obj) -> str:
        return obj.product.slug


class ProductReviewCreateSerializer(serializers.Serializer):
    order_item = serializers.IntegerField()
    rating = serializers.IntegerField(min_value=1, max_value=5)
    title = serializers.CharField(max_length=140, required=False, allow_blank=True)
    comment = serializers.CharField(max_length=2000, required=False, allow_blank=True)

    def validate_order_item(self, value: int):
        from apps.marketplace.models import OrderItem, OrderStatus

        user = self.context["request"].user
        item = (
            OrderItem.objects.filter(pk=value, order__buyer=user)
            .select_related("order", "product", "product__seller", "product__seller__user")
            .first()
        )
        if item is None:
            raise serializers.ValidationError("Purchase not found.")
        if item.order.status != OrderStatus.PAID:
            raise serializers.ValidationError("This order has not been paid for.")
        if ProductReview.all_objects.filter(order_item=item).exists():
            raise serializers.ValidationError("You have already reviewed this product.")
        return item


# ═══════════════════════════════════════════════════════════════════════════
# "WHAT CAN I REVIEW?"
# ═══════════════════════════════════════════════════════════════════════════
class PendingBookingReviewSerializer(serializers.Serializer):
    """A completed shoot still awaiting its review."""

    booking_id = serializers.IntegerField(source="id")
    photographer_id = serializers.IntegerField()
    photographer_name = serializers.SerializerMethodField()
    photographer_avatar = serializers.SerializerMethodField()
    service_name = serializers.SerializerMethodField()
    event_date = serializers.DateField()

    def get_photographer_name(self, obj) -> str:
        return obj.photographer.display_name

    def get_photographer_avatar(self, obj) -> str | None:
        return _absolute(self.context.get("request"), obj.photographer.user.avatar)

    def get_service_name(self, obj) -> str:
        return obj.service.title


class PendingProductReviewSerializer(serializers.Serializer):
    order_item_id = serializers.IntegerField(source="id")
    product_title = serializers.SerializerMethodField()
    product_slug = serializers.SerializerMethodField()
    thumbnail_url = serializers.SerializerMethodField()
    purchased_at = serializers.DateTimeField(source="created_at")

    def get_product_title(self, obj) -> str:
        return obj.product.title

    def get_product_slug(self, obj) -> str:
        return obj.product.slug

    def get_thumbnail_url(self, obj) -> str | None:
        return _absolute(self.context.get("request"), obj.product.thumbnail)


class PendingReviewsSerializer(serializers.Serializer):
    bookings = PendingBookingReviewSerializer(many=True)
    order_items = PendingProductReviewSerializer(many=True)
