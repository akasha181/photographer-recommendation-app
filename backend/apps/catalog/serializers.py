"""Catalogue serializers — categories, specializations, services, packages."""

from rest_framework import serializers

from apps.catalog.models import Category, Service, ServicePackage, Specialization


class CategorySerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = (
            "id", "name", "slug", "description", "icon", "image_url",
            "photographer_count", "booking_count",
        )

    def get_image_url(self, obj) -> str | None:
        if not obj.image:
            return None
        request = self.context.get("request")
        return request.build_absolute_uri(obj.image.url) if request else obj.image.url


class CategoryMiniSerializer(serializers.ModelSerializer):
    """
    Lean version embedded inside photographer payloads.

    A photographer list of 20 rows embeds up to 20 category objects. Sending
    the description and counts there would roughly double the response size
    for data the card never renders.
    """

    class Meta:
        model = Category
        fields = ("id", "name", "slug", "icon")


class SpecializationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Specialization
        fields = ("id", "name", "slug")


class ServicePackageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ServicePackage
        fields = (
            "id", "name", "price", "description", "features",
            "duration_hours", "edited_photos_count", "is_popular",
        )


class ServiceSerializer(serializers.ModelSerializer):
    """Service as shown on a photographer's profile."""

    category = CategoryMiniSerializer(read_only=True)
    cover_image_url = serializers.SerializerMethodField()
    packages = ServicePackageSerializer(many=True, read_only=True)

    class Meta:
        model = Service
        fields = (
            "id", "title", "description", "price", "pricing_unit",
            "duration_hours", "edited_photos_count", "raw_photos_included",
            "delivery_days", "includes", "advance_payment_percent",
            "category", "cover_image_url", "packages", "booking_count",
        )

    def get_cover_image_url(self, obj) -> str | None:
        if not obj.cover_image:
            return None
        request = self.context.get("request")
        url = obj.cover_image.url
        return request.build_absolute_uri(url) if request else url


class ServiceMiniSerializer(serializers.ModelSerializer):
    """Just enough to show "from Rs X" on a card."""

    class Meta:
        model = Service
        fields = ("id", "title", "price", "duration_hours")


# ═══════════════════════════════════════════════════════════════════════════
# MODULE 5 — a photographer managing their own catalogue
# ═══════════════════════════════════════════════════════════════════════════
class OwnServiceSerializer(ServiceSerializer):
    """
    The owner's view of their own listing.

    Adds the two things only they need: whether it is live, and how many
    bookings it has — which is what makes "archive" versus "delete"
    understandable without reading the error message first.
    """

    can_delete = serializers.SerializerMethodField()

    class Meta(ServiceSerializer.Meta):
        fields = ServiceSerializer.Meta.fields + (
            "is_active", "display_order", "min_hours", "max_travel_km",
            "view_count", "can_delete",
        )

    def get_can_delete(self, obj) -> bool:
        """False once it has history — the UI then offers Archive instead."""
        return obj.booking_count == 0


class ServiceWriteSerializer(serializers.ModelSerializer):
    """
    What a photographer may set on a service.

    `photographer` is absent on purpose — it comes from the authenticated
    user, never the body, or one photographer could add listings to another's
    profile. `booking_count` and `view_count` are derived and equally absent.
    """

    category = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.filter(is_active=True)
    )

    class Meta:
        model = Service
        fields = (
            "title", "description", "category", "price", "pricing_unit",
            "min_hours", "duration_hours", "edited_photos_count",
            "raw_photos_included", "delivery_days", "includes",
            "advance_payment_percent", "max_travel_km", "display_order",
            "cover_image",
        )

    def validate_price(self, value):
        if value <= 0:
            raise serializers.ValidationError("Set a price above zero.")
        if value > 5_000_000:
            raise serializers.ValidationError(
                "That price looks like a typo. Contact support for enterprise packages."
            )
        return value

    def validate_title(self, value):
        value = value.strip()
        if len(value) < 5:
            raise serializers.ValidationError(
                "Give the service a descriptive title buyers will recognise."
            )
        return value

    def validate_includes(self, value):
        """`includes` is a JSON list of bullet points, not free text."""
        if not isinstance(value, list):
            raise serializers.ValidationError("Send a list of bullet points.")
        return [str(item).strip()[:120] for item in value if str(item).strip()][:12]

    def validate(self, attrs):
        minimum = attrs.get("min_hours", getattr(self.instance, "min_hours", 1))
        duration = attrs.get(
            "duration_hours", getattr(self.instance, "duration_hours", 1)
        )
        if minimum and duration and minimum > duration:
            raise serializers.ValidationError(
                {"min_hours": "The minimum cannot exceed the standard duration."}
            )
        return attrs


class ServicePackageWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = ServicePackage
        fields = (
            "name", "price", "description", "features",
            "duration_hours", "edited_photos_count", "is_popular",
            "display_order",
        )

    def validate_price(self, value):
        if value <= 0:
            raise serializers.ValidationError("Set a price above zero.")
        return value

    def validate_features(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError("Send a list of features.")
        return [str(item).strip()[:120] for item in value if str(item).strip()][:12]
