"""Digital Marketplace routes — mounted at /api/v1/marketplace/"""

from django.urls import path
from rest_framework.routers import DefaultRouter

from apps.marketplace.views import (
    CartViewSet,
    OrderViewSet,
    ProductViewSet,
    SellerProductViewSet,
    download_file,
)

app_name = "marketplace"

router = DefaultRouter()
router.register("products", ProductViewSet, basename="product")
router.register("cart", CartViewSet, basename="cart")
router.register("orders", OrderViewSet, basename="order")
router.register("seller/products", SellerProductViewSet, basename="seller-product")

urlpatterns = [
    # Declared before the router so the token is not shadowed by a lookup
    # pattern, and kept flat because a download manager follows this URL
    # outside the app's HTTP client.
    path("download/<str:token>/", download_file, name="download-file"),
    *router.urls,
]
