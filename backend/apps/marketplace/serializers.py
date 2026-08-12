"""
Marketplace serializers.

WHAT IS DELIBERATELY ABSENT
---------------------------
No field below exposes `ProductFile.file`. The manifest
(`ProductFileSerializer`) carries names and sizes so a buyer can see what they
are paying for, and nothing else — the bytes are reachable only through a
redeemed download token. A serializer that helpfully added a `url` here would
silently undo `core/storage.py`.

Checkout takes no amount either. The total is computed from the cart on the
server; a client that can name its own total buys a Rs 12,000 preset pack for
one rupee.
"""

from rest_framework import serializers

from apps.catalog.serializers import CategoryMiniSerializer
from apps.marketplace.models import (
    CartItem,
    DigitalProduct,
    Order,
    OrderItem,
    ProductFile,
)


def _absolute(request, file_field) -> str | None:
    if not file_field:
        return None
    return request.build_absolute_uri(file_field.url) if request else file_field.url


class SellerMiniSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    display_name = serializers.CharField()
    avatar_url = serializers.SerializerMethodField()
    is_verified = serializers.BooleanField()

    def get_avatar_url(self, obj) -> str | None:
        return _absolute(self.context.get("request"), obj.user.avatar)


class ProductFileSerializer(serializers.ModelSerializer):
    """The manifest — names and sizes only. No URL, by design."""

    class Meta:
        model = ProductFile
        fields = ("id", "name", "file_size_mb", "display_order")


class ProductListSerializer(serializers.ModelSerializer):
    """Grid card payload."""

    seller = SellerMiniSerializer(read_only=True)
    category = CategoryMiniSerializer(read_only=True)
    thumbnail_url = serializers.SerializerMethodField()
    discount_percent = serializers.IntegerField(read_only=True)
    type_label = serializers.CharField(source="get_product_type_display", read_only=True)
    is_owned = serializers.SerializerMethodField()
    is_wishlisted = serializers.SerializerMethodField()
    in_cart = serializers.SerializerMethodField()

    class Meta:
        model = DigitalProduct
        fields = (
            "id", "uuid", "slug", "title", "product_type", "type_label",
            "license_type", "price", "compare_at_price", "discount_percent",
            "thumbnail_url", "file_count", "total_size_mb",
            "sales_count", "avg_rating", "reviews_count",
            "seller", "category", "is_featured",
            "is_owned", "is_wishlisted", "in_cart",
        )

    def get_thumbnail_url(self, obj) -> str | None:
        return _absolute(self.context.get("request"), obj.thumbnail)

    # These three read from sets the view loaded in one query each, rather than
    # firing a query per card. A 20-row grid would otherwise cost 60 extra.
    def get_is_owned(self, obj) -> bool:
        return obj.pk in (self.context.get("owned_ids") or set())

    def get_is_wishlisted(self, obj) -> bool:
        return obj.pk in (self.context.get("wishlisted_ids") or set())

    def get_in_cart(self, obj) -> bool:
        return obj.pk in (self.context.get("cart_ids") or set())


class ProductDetailSerializer(ProductListSerializer):
    files = ProductFileSerializer(many=True, read_only=True)
    preview_image_urls = serializers.SerializerMethodField()

    class Meta(ProductListSerializer.Meta):
        fields = ProductListSerializer.Meta.fields + (
            "description", "compatible_with", "tags",
            "preview_images", "preview_image_urls", "preview_video_url",
            "files", "view_count", "wishlist_count", "published_at",
        )

    def get_preview_image_urls(self, obj) -> list[str]:
        """
        `preview_images` is a JSON list of storage paths, not URLs.

        Resolving them here means the app renders them directly instead of
        every client reimplementing the same string concatenation.
        """
        from django.conf import settings

        request = self.context.get("request")
        urls = []
        for path in obj.preview_images or []:
            if str(path).startswith("http"):
                urls.append(str(path))
                continue
            relative = f"{settings.MEDIA_URL}{str(path).lstrip('/')}"
            urls.append(request.build_absolute_uri(relative) if request else relative)
        return urls


# ═══════════════════════════════════════════════════════════════════════════
# CART
# ═══════════════════════════════════════════════════════════════════════════
class CartItemSerializer(serializers.ModelSerializer):
    product = ProductListSerializer(read_only=True)
    #: Set by `selectors.cart_summary` — why this line cannot be checked out.
    is_available = serializers.BooleanField(read_only=True, default=True)
    is_owned = serializers.BooleanField(read_only=True, default=False)

    class Meta:
        model = CartItem
        fields = ("id", "product", "is_available", "is_owned", "created_at")


class CartSerializer(serializers.Serializer):
    items = CartItemSerializer(many=True, read_only=True)
    count = serializers.IntegerField(read_only=True)
    subtotal = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    total = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    unavailable_count = serializers.IntegerField(read_only=True)
    wallet_balance = serializers.DecimalField(
        max_digits=14, decimal_places=2, read_only=True
    )
    can_checkout = serializers.SerializerMethodField()
    shortfall = serializers.SerializerMethodField()

    def get_can_checkout(self, obj) -> bool:
        return bool(
            obj["count"] > 0
            and obj["unavailable_count"] == 0
            and obj["wallet_balance"] >= obj["total"]
        )

    def get_shortfall(self, obj) -> str:
        """How much more the buyer needs — the number the top-up screen wants."""
        gap = obj["total"] - obj["wallet_balance"]
        return str(gap if gap > 0 else 0)


class AddToCartSerializer(serializers.Serializer):
    product = serializers.PrimaryKeyRelatedField(
        queryset=DigitalProduct.objects.filter(is_published=True, is_approved=True)
    )


# ═══════════════════════════════════════════════════════════════════════════
# ORDERS
# ═══════════════════════════════════════════════════════════════════════════
class OrderItemSerializer(serializers.ModelSerializer):
    product_slug = serializers.CharField(source="product.slug", read_only=True)
    thumbnail_url = serializers.SerializerMethodField()
    seller_name = serializers.CharField(source="seller.display_name", read_only=True)
    downloads_remaining = serializers.IntegerField(read_only=True)
    files = serializers.SerializerMethodField()

    class Meta:
        model = OrderItem
        fields = (
            "id", "product", "product_slug", "product_title", "thumbnail_url",
            "seller_name", "price", "download_count", "max_downloads",
            "downloads_remaining", "has_review", "files", "created_at",
        )

    def get_thumbnail_url(self, obj) -> str | None:
        return _absolute(self.context.get("request"), obj.product.thumbnail)

    def get_files(self, obj) -> list:
        return ProductFileSerializer(obj.product.files.all(), many=True).data


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    item_count = serializers.SerializerMethodField()
    status_label = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Order
        fields = (
            "id", "uuid", "order_number", "status", "status_label",
            "subtotal", "discount", "total", "payment_method",
            "paid_at", "created_at", "items", "item_count",
        )

    def get_item_count(self, obj) -> int:
        return obj.items.count()


class CheckoutSerializer(serializers.Serializer):
    """
    Intentionally empty of money.

    The cart is the source of truth for what is being bought and what it costs.
    An `Idempotency-Key` header — not a body field — makes the retry safe.
    """


class DownloadRequestSerializer(serializers.Serializer):
    file = serializers.IntegerField(
        required=False,
        help_text="ProductFile id. Omit to get the first file in the product.",
    )


class DownloadTokenSerializer(serializers.Serializer):
    download_url = serializers.CharField(read_only=True)
    expires_at = serializers.DateTimeField(read_only=True)
    file_name = serializers.CharField(read_only=True)
    downloads_remaining = serializers.IntegerField(read_only=True)


class SellerProductSerializer(ProductListSerializer):
    """
    A seller's own listing.

    Adds the two moderation flags, which the seller list needs because it
    includes unpublished drafts. They stay off `ProductListSerializer` so the
    public grid does not carry two booleans that are true by definition of
    being visible there at all.
    """

    class Meta(ProductListSerializer.Meta):
        fields = ProductListSerializer.Meta.fields + (
            "is_published", "is_approved", "published_at", "view_count",
            "wishlist_count", "total_revenue",
        )


class SellerSummarySerializer(serializers.Serializer):
    products_total = serializers.IntegerField(read_only=True)
    products_live = serializers.IntegerField(read_only=True)
    sales_count = serializers.IntegerField(read_only=True)
    gross_revenue = serializers.DecimalField(
        max_digits=14, decimal_places=2, read_only=True
    )
    net_earnings = serializers.DecimalField(
        max_digits=14, decimal_places=2, read_only=True
    )
