"""Portfolio endpoints — albums, images, videos."""

from drf_spectacular.utils import extend_schema
from rest_framework import status as http
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import GenericViewSet, ModelViewSet, ReadOnlyModelViewSet

from apps.portfolio.models import PortfolioAlbum, PortfolioImage
from apps.portfolio.serializers import PortfolioAlbumSerializer, PortfolioImageSerializer
from apps.profiles.models import PhotographerProfile


def _get_photographer_profile(user):
    profile = getattr(user, "photographer_profile", None)
    if profile is None:
        raise NotFound("Only photographer accounts have a portfolio.")
    return profile


@extend_schema(tags=["Portfolio"])
class MyPortfolioViewSet(GenericViewSet):
    """Endpoints for photographer's own portfolio management."""

    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    serializer_class = PortfolioImageSerializer

    def get_queryset(self):
        profile = _get_photographer_profile(self.request.user)
        return PortfolioImage.objects.filter(photographer=profile).select_related(
            "photographer", "album", "category"
        ).order_by("-is_featured", "display_order", "-created_at")

    @extend_schema(summary="List all images in my portfolio")
    def list(self, request):
        qs = self.get_queryset()
        serializer = self.get_serializer(qs, many=True)
        return Response({"message": "Portfolio images retrieved", "data": serializer.data})

    @extend_schema(summary="Upload a new portfolio image")
    def create(self, request):
        profile = _get_photographer_profile(request.user)
        image_file = request.FILES.get("image") or request.data.get("image")
        if not image_file:
            raise ValidationError({"image": "An image file is required."})

        caption = request.data.get("caption", "")
        album_id = request.data.get("album")
        album = None
        if album_id:
            album = PortfolioAlbum.objects.filter(id=album_id, photographer=profile).first()

        portfolio_image = PortfolioImage.objects.create(
            photographer=profile,
            album=album,
            image=image_file,
            caption=caption,
            width=800,
            height=600,
        )

        serializer = self.get_serializer(portfolio_image)
        return Response(
            {"message": "Image uploaded successfully", "data": serializer.data},
            status=http.HTTP_201_CREATED,
        )

    @extend_schema(summary="Delete a portfolio image")
    def destroy(self, request, pk=None):
        profile = _get_photographer_profile(request.user)
        image = PortfolioImage.objects.filter(pk=pk, photographer=profile).first()
        if not image:
            raise NotFound("Image not found.")
        image.delete()
        return Response({"message": "Image deleted", "data": None}, status=http.HTTP_200_OK)

    @extend_schema(summary="Update image details (caption, album)")
    def partial_update(self, request, pk=None):
        profile = _get_photographer_profile(request.user)
        image = PortfolioImage.objects.filter(pk=pk, photographer=profile).first()
        if not image:
            raise NotFound("Image not found.")
        caption = request.data.get("caption")
        if caption is not None:
            image.caption = caption
        album_id = request.data.get("album")
        if album_id is not None:
            if album_id in (0, "0", None, ""):
                image.album = None
            else:
                image.album = PortfolioAlbum.objects.filter(id=album_id, photographer=profile).first()
        image.save()
        serializer = self.get_serializer(image)
        return Response({"message": "Image updated", "data": serializer.data})

    @extend_schema(summary="Toggle featured state of an image")
    @action(detail=True, methods=["post"])
    def feature(self, request, pk=None):
        profile = _get_photographer_profile(request.user)
        image = PortfolioImage.objects.filter(pk=pk, photographer=profile).first()
        if not image:
            raise NotFound("Image not found.")
        image.is_featured = not image.is_featured
        image.save(update_fields=["is_featured"])
        serializer = self.get_serializer(image)
        return Response(
            {"message": "Feature state updated", "data": serializer.data}
        )

    @extend_schema(summary="Portfolio summary counts")
    @action(detail=False, methods=["get"])
    def summary(self, request):
        profile = _get_photographer_profile(request.user)
        total_images = profile.portfolio_images.count()
        featured = profile.portfolio_images.filter(is_featured=True).count()
        albums = profile.albums.count()
        return Response(
            {
                "message": "Portfolio summary retrieved",
                "data": {
                    "total_images": total_images,
                    "featured": featured,
                    "albums": albums,
                    "videos": 0,
                },
            }
        )


@extend_schema(tags=["Portfolio"])
class MyAlbumsViewSet(GenericViewSet):
    """Manage photographer's albums."""

    permission_classes = [IsAuthenticated]
    serializer_class = PortfolioAlbumSerializer

    def get_queryset(self):
        profile = _get_photographer_profile(self.request.user)
        return PortfolioAlbum.objects.filter(photographer=profile).order_by("-created_at")

    def list(self, request):
        qs = self.get_queryset()
        serializer = self.get_serializer(qs, many=True)
        return Response({"message": "Albums retrieved", "data": serializer.data})

    def create(self, request):
        profile = _get_photographer_profile(request.user)
        title = request.data.get("title", "").strip()
        if not title:
            raise ValidationError({"title": "Album title is required."})

        album = PortfolioAlbum.objects.create(
            photographer=profile,
            title=title,
            description=request.data.get("description", ""),
            location=request.data.get("location", ""),
        )
        serializer = self.get_serializer(album)
        return Response(
            {"message": "Album created", "data": serializer.data},
            status=http.HTTP_201_CREATED,
        )

    def destroy(self, request, pk=None):
        profile = _get_photographer_profile(request.user)
        album = PortfolioAlbum.objects.filter(pk=pk, photographer=profile).first()
        if not album:
            raise NotFound("Album not found.")
        album.delete()
        return Response({"message": "Album deleted", "data": None})

    def partial_update(self, request, pk=None):
        profile = _get_photographer_profile(request.user)
        album = PortfolioAlbum.objects.filter(pk=pk, photographer=profile).first()
        if not album:
            raise NotFound("Album not found.")
        title = request.data.get("title")
        if title:
            album.title = title.strip()
        if "description" in request.data:
            album.description = request.data["description"]
        if "location" in request.data:
            album.location = request.data["location"]
        album.save()
        serializer = self.get_serializer(album)
        return Response({"message": "Album updated", "data": serializer.data})


@extend_schema(tags=["Portfolio"])
class PublicPhotographerPortfolioView(APIView):
    """Public portfolio images for a specific photographer."""

    permission_classes = [AllowAny]

    def get(self, request, photographer_id):
        profile = PhotographerProfile.objects.filter(pk=photographer_id).first()
        if not profile:
            raise NotFound("Photographer not found.")

        images = PortfolioImage.objects.filter(photographer=profile).select_related(
            "photographer", "album", "category"
        ).order_by("-is_featured", "display_order", "-created_at")

        serializer = PortfolioImageSerializer(images, many=True, context={"request": request})
        return Response({"message": "Portfolio images retrieved", "data": serializer.data})


# Backward compatibility views
@extend_schema(tags=["Portfolio"])
class PortfolioAlbumViewSet(ReadOnlyModelViewSet):
    serializer_class = PortfolioAlbumSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return PortfolioAlbum.objects.filter(
            photographer__user=self.request.user
        ).order_by('-created_at')


@extend_schema(tags=["Portfolio"])
class PortfolioImageViewSet(ReadOnlyModelViewSet):
    serializer_class = PortfolioImageSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return PortfolioImage.objects.filter(
            photographer__user=self.request.user
        ).order_by('-created_at')
