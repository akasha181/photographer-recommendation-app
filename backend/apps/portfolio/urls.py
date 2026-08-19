"""Portfolio Media routes — mounted at /api/v1/portfolio/"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.portfolio.views import PortfolioAlbumViewSet, PortfolioImageViewSet

app_name = "portfolio"

router = DefaultRouter()
router.register(r'albums', PortfolioAlbumViewSet, basename='album')
router.register(r'images', PortfolioImageViewSet, basename='image')

urlpatterns = [
    path('', include(router.urls)),
]
