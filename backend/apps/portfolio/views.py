"""Portfolio endpoints — albums, images, videos."""

from drf_spectacular.utils import extend_schema
from rest_framework import status as http
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ReadOnlyModelViewSet

from apps.portfolio.models import PortfolioAlbum, PortfolioImage
from apps.portfolio.serializers import PortfolioAlbumSerializer, PortfolioImageSerializer


class StandardPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


@extend_schema(tags=["Portfolio"])
class PortfolioAlbumViewSet(ReadOnlyModelViewSet):
    """Photographer's portfolio albums."""

    serializer_class = PortfolioAlbumSerializer
    pagination_class = StandardPagination
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return PortfolioAlbum.objects.filter(
            photographer__user=self.request.user
        ).select_related(
            'photographer', 'category'
        ).order_by('-created_at')


@extend_schema(tags=["Portfolio"])
class PortfolioImageViewSet(ReadOnlyModelViewSet):
    """Photographer's portfolio images."""

    serializer_class = PortfolioImageSerializer
    pagination_class = StandardPagination
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = PortfolioImage.objects.filter(
            photographer__user=self.request.user
        ).select_related(
            'photographer', 'album', 'category'
        ).order_by('-created_at')

        album_id = self.request.query_params.get('album_id')
        if album_id:
            qs = qs.filter(album_id=album_id)

        return qs
