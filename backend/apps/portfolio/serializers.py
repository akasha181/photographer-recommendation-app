"""Serializers for the portfolio app."""

from rest_framework import serializers

from apps.catalog.serializers import CategoryMiniSerializer
from apps.portfolio.models import PortfolioAlbum, PortfolioImage


class PortfolioAlbumSerializer(serializers.ModelSerializer):
    category = CategoryMiniSerializer(read_only=True)

    class Meta:
        model = PortfolioAlbum
        fields = [
            'id',
            'title',
            'description',
            'cover_image',
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
        read_only_fields = fields


class PortfolioImageSerializer(serializers.ModelSerializer):
    category = CategoryMiniSerializer(read_only=True)

    class Meta:
        model = PortfolioImage
        fields = [
            'id',
            'caption',
            'alt_text',
            'image',
            'thumbnail',
            'image_large',
            'width',
            'height',
            'is_featured',
            'view_count',
            'like_count',
            'album_id',
            'category',
            'created_at',
        ]
        read_only_fields = fields
