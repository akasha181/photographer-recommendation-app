"""Portfolio routes — mounted at /api/v1/portfolio/"""

from rest_framework.routers import DefaultRouter

from apps.portfolio.views import MyPortfolioViewSet, PhotographerPortfolioViewSet

app_name = "portfolio"

router = DefaultRouter()
router.register("me", MyPortfolioViewSet, basename="my-portfolio")
router.register(
    "photographers", PhotographerPortfolioViewSet, basename="portfolio"
)

urlpatterns = router.urls
