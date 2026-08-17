"""
Portfolio serializers.

THREE IMAGE URLS, NOT ONE
-------------------------
`thumbnail_url` (~20 KB) is what a grid of 30 loads; `image_url` is the
medium rendition for a card; `image_large_url` is fetched only when someone
taps to view full screen. Serving one size everywhere is the single biggest
cause of slow portfolio screens on 3G, which is why upload generates all
three.
"""

from rest_framework import serializers

from apps.catalog.serializers import CategoryMiniSerializer
from apps.portfolio.models import PortfolioAlbum, PortfolioImage, PortfolioVideo


def _absolute(request, file_field) -> str | None:
    if not file_field:
        return None
    return request.build_absolute_uri(file_field.url) if request else file_field.url


class PortfolioImageSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()
    thumbnail_url = serializers.SerializerMethodField()
    image_large_url = serializers.SerializerMethodField()
    category = CategoryMiniSerializer(read_only=True)
    album_title = serializers.CharField(
        source="album.title", read_only=True, default=None
    )
    aspect_ratio = serializers.FloatField(read_only=True)
    is_liked = serializers.SerializerMethodField()

    class Meta:
        model = PortfolioImage
        fields = (
            "id", "caption", "alt_text", "image_url", "thumbnail_url",
            "image_large_url", "width", "height", "aspect_ratio",
            "is_featured", "display_order", "album", "album_title",
            "category", "like_count", "view_count", "is_liked", "created_at",
        )

    def get_image_url(self, obj) -> str | None:
        return _absolute(self.context.get("request"), obj.image)

    def get_thumbnail_url(self, obj) -> str | None:
        # Falls back to the medium rendition for rows uploaded before the
        # three-size pipeline existed.
        return _absolute(self.context.get("request"), obj.thumbnail or obj.image)

    def get_image_large_url(self, obj) -> str | None:
        return _absolute(self.context.get("request"), obj.image_large or obj.image)

    def get_is_liked(self, obj) -> bool:
        """Reads a set the view loaded in one query, not one query per image."""
        return obj.pk in (self.context.get("liked_ids") or set())


class PortfolioImageWriteSerializer(serializers.Serializer):
    """
    Upload input.

    `photographer` is absent — it comes from the authenticated user, never the
    body, or one photographer could upload into another's portfolio.
    """

    image = serializers.ImageField()
    caption = serializers.CharField(
        max_length=200, required=False, allow_blank=True, default=""
    )
    alt_text = serializers.CharField(
        max_length=200, required=False, allow_blank=True, default=""
    )
    album = serializers.IntegerField(required=False, allow_null=True)
    is_featured = serializers.BooleanField(required=False, default=False)


class PortfolioImageUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = PortfolioImage
        fields = ("caption", "alt_text", "album", "category", "display_order")


class ReorderSerializer(serializers.Serializer):
    """Drag-and-drop order, applied in one request."""

    image_ids = serializers.ListField(child=serializers.IntegerField(), max_length=200)


class PortfolioAlbumSerializer(serializers.ModelSerializer):
    cover_image_url = serializers.SerializerMethodField()
    category = CategoryMiniSerializer(read_only=True)

    class Meta:
        model = PortfolioAlbum
        fields = (
            "id", "title", "description", "cover_image_url", "category",
            "shoot_date", "location", "client_name", "is_public",
            "is_featured", "display_order", "image_count", "view_count",
            "created_at",
        )

    def get_cover_image_url(self, obj) -> str | None:
        return _absolute(self.context.get("request"), obj.cover_image)


class PortfolioAlbumWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = PortfolioAlbum
        fields = (
            "title", "description", "cover_image", "category",
            "shoot_date", "location", "client_name", "is_public",
            "is_featured", "display_order",
        )

    def validate_title(self, value):
        value = value.strip()
        if len(value) < 3:
            raise serializers.ValidationError("Give the album a title.")
        return value

    def validate_client_name(self, value):
        """Shown publicly, so it is only ever set with consent."""
        return (value or "").strip()[:120]


class PortfolioVideoSerializer(serializers.ModelSerializer):
    poster_url = serializers.SerializerMethodField()
    video_url = serializers.SerializerMethodField()

    class Meta:
        model = PortfolioVideo
        fields = (
            "id", "title", "description", "provider", "external_url",
            "video_url", "poster_url", "duration_seconds", "is_featured",
            "display_order", "view_count", "created_at",
        )

    def get_poster_url(self, obj) -> str | None:
        return _absolute(self.context.get("request"), obj.poster_image)

    def get_video_url(self, obj) -> str | None:
        return _absolute(self.context.get("request"), obj.video_file)


class PortfolioSummarySerializer(serializers.Serializer):
    images = serializers.IntegerField(read_only=True)
    featured = serializers.IntegerField(read_only=True)
    albums = serializers.IntegerField(read_only=True)
    videos = serializers.IntegerField(read_only=True)
