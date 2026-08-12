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
