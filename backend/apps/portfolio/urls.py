"""Portfolio routes — mounted at /api/v1/portfolio/"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.portfolio.views import (
    MyAlbumsViewSet,
    MyPortfolioViewSet,
    PortfolioAlbumViewSet,
    PortfolioImageViewSet,
    PublicPhotographerPortfolioView,
)

app_name = "portfolio"

router = DefaultRouter()
router.register(r"albums", PortfolioAlbumViewSet, basename="album")
router.register(r"images", PortfolioImageViewSet, basename="image")

urlpatterns = [
    # Photographer's own portfolio management
    path("me/summary/", MyPortfolioViewSet.as_view({"get": "summary"}), name="my-portfolio-summary"),
    path("me/albums/create/", MyAlbumsViewSet.as_view({"post": "create"}), name="my-albums-create"),
    path("me/albums/<int:pk>/remove/", MyAlbumsViewSet.as_view({"delete": "destroy"}), name="my-albums-remove"),
    path("me/albums/<int:pk>/", MyAlbumsViewSet.as_view({"delete": "destroy", "patch": "partial_update"}), name="my-albums-detail"),
    path("me/albums/", MyAlbumsViewSet.as_view({"get": "list", "post": "create"}), name="my-albums"),
    path("me/<int:pk>/feature/", MyPortfolioViewSet.as_view({"post": "feature"}), name="my-portfolio-feature"),
    path("me/<int:pk>/", MyPortfolioViewSet.as_view({"delete": "destroy", "patch": "partial_update"}), name="my-portfolio-detail"),
    path("me/", MyPortfolioViewSet.as_view({"get": "list", "post": "create"}), name="my-portfolio"),

    # Public photographer portfolio
    path("<int:photographer_id>/images/", PublicPhotographerPortfolioView.as_view(), name="photographer-portfolio-images"),

    # Router fallbacks
    path("", include(router.urls)),
]
