"""Wishlist routes — mounted at /api/v1/wishlist/"""

from rest_framework.routers import DefaultRouter

from apps.wishlist.views import WishlistViewSet

app_name = "wishlist"

router = DefaultRouter()
router.register("", WishlistViewSet, basename="wishlist")

urlpatterns = router.urls
