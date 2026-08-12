"""
Wishlist serializers.

Each row reuses the card serializer its target already has — the saved
photographers list is drawn by the same component as Explore, and the saved
products list by the same component as the Shop grid. Inventing a third,
flatter shape here would mean those components need a second code path for
data they already know how to render.
"""

from rest_framework import serializers

from apps.marketplace.serializers import ProductListSerializer
from apps.profiles.serializers import PhotographerListSerializer
from apps.wishlist.models import WishlistItem


class SavedPhotographerSerializer(serializers.ModelSerializer):
    photographer = PhotographerListSerializer(read_only=True)

    class Meta:
        model = WishlistItem
        fields = ("id", "photographer", "note", "created_at")


class SavedProductSerializer(serializers.ModelSerializer):
    product = ProductListSerializer(read_only=True)

    class Meta:
        model = WishlistItem
        fields = ("id", "product", "note", "created_at")


class WishlistSerializer(serializers.Serializer):
    """Both lists in one response — the Saved screen renders both tabs."""

    photographers = SavedPhotographerSerializer(many=True, read_only=True)
    products = SavedProductSerializer(many=True, read_only=True)
    counts = serializers.DictField(read_only=True)


class ToggleSerializer(serializers.Serializer):
    """
    Exactly one target, matching `ck_wishlist_exactly_one_target` in the
    database. Validating it here means the constraint is a backstop rather
    than the error the user sees.
    """

    photographer = serializers.IntegerField(required=False)
    product = serializers.IntegerField(required=False)

    def validate(self, attrs):
        has_photographer = attrs.get("photographer") is not None
        has_product = attrs.get("product") is not None
        if has_photographer == has_product:
            raise serializers.ValidationError(
                "Send exactly one of `photographer` or `product`."
            )
        return attrs


class ToggleResultSerializer(serializers.Serializer):
    is_saved = serializers.BooleanField(read_only=True)
    counts = serializers.DictField(read_only=True)
