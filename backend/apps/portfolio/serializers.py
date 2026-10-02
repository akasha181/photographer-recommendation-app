"""Serializers for the portfolio app."""

from rest_framework import serializers

from apps.catalog.serializers import CategoryMiniSerializer
from apps.portfolio.models import PortfolioAlbum, PortfolioImage


def _absolute(request, filefield) -> str | None:
    if not filefield:
        return None
    try:
        url = filefield.url
    except (ValueError, NotImplementedError):
        return None
    return request.build_absolute_uri(url) if request else url


class PortfolioAlbumSerializer(serializers.ModelSerializer):
    category = CategoryMiniSerializer(read_only=True)
    cover_image_url = serializers.SerializerMethodField()

    class Meta:
        model = PortfolioAlbum
        fields = [
            'id',
            'title',
            'description',
            'cover_image',
            'cover_image_url',
            'shoot_date',
            'location',
            'client_name',
            'is_public',
            'is_featured',
            'image_count',
            'view_count',
            'category',
            'created_at',
        ]
        read_only_fields = ['id', 'image_count', 'view_count', 'created_at']

    def get_cover_image_url(self, obj) -> str | None:
        return _absolute(self.context.get('request'), obj.cover_image)


class PortfolioImageSerializer(serializers.ModelSerializer):
    category = CategoryMiniSerializer(read_only=True)
    image_url = serializers.SerializerMethodField()
    thumbnail_url = serializers.SerializerMethodField()
    image_large_url = serializers.SerializerMethodField()
    album_title = serializers.SerializerMethodField()
    aspect_ratio = serializers.SerializerMethodField()
    is_liked = serializers.SerializerMethodField()

    class Meta:
        model = PortfolioImage
        fields = [
            'id',
            'caption',
            'alt_text',
            'image',
            'image_url',
            'thumbnail',
            'thumbnail_url',
            'image_large',
            'image_large_url',
            'width',
            'height',
            'aspect_ratio',
            'is_featured',
            'view_count',
            'like_count',
            'is_liked',
            'album',
            'album_id',
            'album_title',
            'category',
            'created_at',
        ]
        read_only_fields = [
            'id', 'width', 'height', 'aspect_ratio', 'view_count',
            'like_count', 'is_liked', 'created_at',
        ]

    def get_image_url(self, obj) -> str | None:
        return _absolute(self.context.get('request'), obj.image)

    def get_thumbnail_url(self, obj) -> str | None:
        return _absolute(self.context.get('request'), obj.thumbnail or obj.image)

    def get_image_large_url(self, obj) -> str | None:
        return _absolute(self.context.get('request'), obj.image_large or obj.image)

    def get_album_title(self, obj) -> str | None:
        return obj.album.title if obj.album else None

    def get_aspect_ratio(self, obj) -> float:
        if obj.width and obj.height:
            return round(obj.width / obj.height, 2)
        return 1.0

    def get_is_liked(self, obj) -> bool:
        return False
