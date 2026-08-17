"""
Portfolio endpoints — Module 6.

Two audiences, two viewsets. `PhotographerPortfolioViewSet` is what a buyer
browses on a profile; `MyPortfolioViewSet` is the owner's editor, scoped to
`request.user.photographer_profile` so an id in the URL can only ever address
their own row.
"""

import logging

from django.db.models import F
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status as http
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from apps.core.mixins import MessageResponseMixin, MultiSerializerMixin
from apps.core.pagination import StandardPagination
from apps.core.permissions import IsPhotographer
from apps.portfolio import selectors, services
from apps.portfolio.models import PortfolioAlbum, PortfolioImage
from apps.portfolio.serializers import (
    PortfolioAlbumSerializer,
    PortfolioAlbumWriteSerializer,
    PortfolioImageSerializer,
    PortfolioImageUpdateSerializer,
    PortfolioImageWriteSerializer,
    PortfolioSummarySerializer,
    PortfolioVideoSerializer,
    ReorderSerializer,
)

logger = logging.getLogger("snapsphere")


def _liked_ids(user, images) -> set[int]:
    """One query for the whole page instead of one per image."""
    if not user or not user.is_authenticated:
        return set()
    from apps.portfolio.models import PortfolioImageLike

    return set(
        PortfolioImageLike.objects.filter(
            user=user, image__in=[i.pk for i in images]
        ).values_list("image_id", flat=True)
    )


@extend_schema(tags=["Portfolio"])
class PhotographerPortfolioViewSet(MessageResponseMixin, GenericViewSet):
    """A photographer's public work, as a buyer sees it."""

    permission_classes = [AllowAny]
    serializer_class = PortfolioImageSerializer
    pagination_class = StandardPagination
    queryset = PortfolioImage.objects.none()  # schema inference only
    success_messages = {
        "images": "Portfolio retrieved",
        "albums": "Albums retrieved",
        "videos": "Videos retrieved",
    }

    def _photographer(self, pk):
        from apps.profiles.selectors import visible_photographers

        photographer = visible_photographers().filter(pk=pk).first()
        if photographer is None:
            raise NotFound("This photographer is not available.")
        return photographer

    @extend_schema(
        summary="Public portfolio images",
        parameters=[OpenApiParameter("featured", bool)],
        responses=PortfolioImageSerializer(many=True),
    )
    @action(detail=True, methods=["get"])
    def images(self, request, pk=None):
        rows = selectors.public_images(self._photographer(pk))
        if request.query_params.get("featured") in ("true", "1"):
            rows = rows.filter(is_featured=True)

        page = self.paginate_queryset(rows)
        context = {**self.get_serializer_context(), "liked_ids": _liked_ids(request.user, page)}
        return self.get_paginated_response(
            PortfolioImageSerializer(page, many=True, context=context).data
        )

    @extend_schema(summary="Public albums", responses=PortfolioAlbumSerializer(many=True))
    @action(detail=True, methods=["get"], pagination_class=None)
    def albums(self, request, pk=None):
        rows = selectors.own_albums(self._photographer(pk)).filter(is_public=True)
        return Response(
            PortfolioAlbumSerializer(
                rows, many=True, context=self.get_serializer_context()
            ).data
        )

    @extend_schema(summary="Showreels and video work", responses=PortfolioVideoSerializer(many=True))
    @action(detail=True, methods=["get"], pagination_class=None)
    def videos(self, request, pk=None):
        rows = selectors.public_videos(self._photographer(pk))
        return Response(
            PortfolioVideoSerializer(
                rows, many=True, context=self.get_serializer_context()
            ).data
        )

    @extend_schema(summary="Like or unlike an image")
    @action(
        detail=False, methods=["post"], url_path=r"images/(?P<image_id>\d+)/like",
        permission_classes=[IsAuthenticated],
    )
    def like(self, request, image_id=None):
        image = PortfolioImage.objects.filter(
            pk=int(image_id), is_deleted=False
        ).first()
        if image is None:
            raise NotFound("Image not found.")
        liked = services.toggle_like(request.user, image)
        image.refresh_from_db()
        return Response({"is_liked": liked, "like_count": image.like_count})


@extend_schema(tags=["Portfolio"])
class MyPortfolioViewSet(MessageResponseMixin, MultiSerializerMixin, GenericViewSet):
    """The photographer's own portfolio editor."""

    permission_classes = [IsAuthenticated, IsPhotographer]
    serializer_class = PortfolioImageSerializer
    serializer_classes = {
        "create": PortfolioImageWriteSerializer,
        "partial_update": PortfolioImageUpdateSerializer,
        "reorder": ReorderSerializer,
        "create_album": PortfolioAlbumWriteSerializer,
        "update_album": PortfolioAlbumWriteSerializer,
    }
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    pagination_class = None
    queryset = PortfolioImage.objects.none()  # schema inference only
    success_messages = {
        "list": "Your portfolio retrieved",
        "create": "Image uploaded",
        "partial_update": "Image updated",
        "destroy": "Image removed",
        "feature": "Updated",
        "reorder": "Order saved",
        "summary": "Portfolio summary retrieved",
        "albums": "Your albums retrieved",
        "create_album": "Album created",
        "update_album": "Album updated",
        "delete_album": "Album deleted",
    }

    def _profile(self):
        profile = getattr(self.request.user, "photographer_profile", None)
        if profile is None:
            raise NotFound("Only photographer accounts have a portfolio.")
        return profile

    def _image(self, pk) -> PortfolioImage:
        image = selectors.get_own_image(self._profile(), int(pk))
        if image is None:
            raise NotFound("Image not found.")
        return image

    def _album(self, pk) -> PortfolioAlbum:
        album = selectors.get_own_album(self._profile(), int(pk))
        if album is None:
            raise NotFound("Album not found.")
        return album

    # ─── Images ──────────────────────────────────────────────────────────────
    @extend_schema(
        summary="Your images, drafts included",
        responses=PortfolioImageSerializer(many=True),
    )
    def list(self, request):
        rows = list(selectors.own_images(self._profile()))
        context = {**self.get_serializer_context(), "liked_ids": _liked_ids(request.user, rows)}
        return Response(PortfolioImageSerializer(rows, many=True, context=context).data)

    @extend_schema(
        summary="Upload an image — EXIF stripped, three sizes generated",
        request=PortfolioImageWriteSerializer,
        responses={201: PortfolioImageSerializer},
    )
    def create(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        album = None
        if data.get("album"):
            album = self._album(data["album"])

        image = services.upload_image(
            self._profile(),
            image=data["image"],
            caption=data.get("caption", ""),
            alt_text=data.get("alt_text", ""),
            album=album,
            is_featured=data.get("is_featured", False),
        )
        return Response(
            PortfolioImageSerializer(
                image, context=self.get_serializer_context()
            ).data,
            status=http.HTTP_201_CREATED,
        )

    @extend_schema(
        summary="Edit caption, album or order",
        request=PortfolioImageUpdateSerializer,
        responses=PortfolioImageSerializer,
    )
    def partial_update(self, request, pk=None):
        image = self._image(pk)
        serializer = self.get_serializer(image, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        updated = services.update_image(image, **serializer.validated_data)
        return Response(
            PortfolioImageSerializer(
                updated, context=self.get_serializer_context()
            ).data
        )

    @extend_schema(summary="Remove an image", responses={204: None})
    def destroy(self, request, pk=None):
        services.delete_image(self._image(pk))
        return Response(status=http.HTTP_204_NO_CONTENT)

    @extend_schema(summary="Feature or unfeature — capped at 12")
    @action(detail=True, methods=["post"])
    def feature(self, request, pk=None):
        image = services.toggle_featured(self._image(pk))
        return Response(
            PortfolioImageSerializer(
                image, context=self.get_serializer_context()
            ).data
        )

    @extend_schema(
        summary="Apply a drag-and-drop order",
        request=ReorderSerializer,
        responses=PortfolioImageSerializer(many=True),
    )
    @action(detail=False, methods=["post"])
    def reorder(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.reorder_images(self._profile(), serializer.validated_data["image_ids"])
        rows = list(selectors.own_images(self._profile()))
        return Response(
            PortfolioImageSerializer(
                rows, many=True, context=self.get_serializer_context()
            ).data
        )

    @extend_schema(summary="Counts for the tab header", responses=PortfolioSummarySerializer)
    @action(detail=False, methods=["get"])
    def summary(self, request):
        return Response(
            PortfolioSummarySerializer(
                selectors.portfolio_summary(self._profile())
            ).data
        )

    # ─── Albums ──────────────────────────────────────────────────────────────
    @extend_schema(summary="Your albums", responses=PortfolioAlbumSerializer(many=True))
    @action(detail=False, methods=["get"])
    def albums(self, request):
        rows = selectors.own_albums(self._profile())
        return Response(
            PortfolioAlbumSerializer(
                rows, many=True, context=self.get_serializer_context()
            ).data
        )

    @extend_schema(
        summary="Create an album",
        request=PortfolioAlbumWriteSerializer,
        responses={201: PortfolioAlbumSerializer},
    )
    @action(detail=False, methods=["post"], url_path="albums/create")
    def create_album(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        album = services.create_album(self._profile(), **serializer.validated_data)
        return Response(
            PortfolioAlbumSerializer(
                album, context=self.get_serializer_context()
            ).data,
            status=http.HTTP_201_CREATED,
        )

    @extend_schema(
        summary="Edit an album",
        request=PortfolioAlbumWriteSerializer,
        responses=PortfolioAlbumSerializer,
    )
    @action(detail=False, methods=["patch"], url_path=r"albums/(?P<album_id>\d+)")
    def update_album(self, request, album_id=None):
        album = self._album(album_id)
        serializer = self.get_serializer(album, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        updated = services.update_album(album, **serializer.validated_data)
        return Response(
            PortfolioAlbumSerializer(
                updated, context=self.get_serializer_context()
            ).data
        )

    @extend_schema(
        summary="Delete an album — its images survive as loose uploads",
        responses={204: None},
    )
    @action(
        detail=False, methods=["delete"], url_path=r"albums/(?P<album_id>\d+)/remove"
    )
    def delete_album(self, request, album_id=None):
        services.delete_album(self._album(album_id))
        return Response(status=http.HTTP_204_NO_CONTENT)
