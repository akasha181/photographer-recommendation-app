"""Profile routes — mounted at /api/v1/profiles/"""

from rest_framework.routers import DefaultRouter

from apps.profiles.views import MyProfileViewSet, PhotographerViewSet, WalletViewSet

app_name = "profiles"

router = DefaultRouter()
router.register("photographers", PhotographerViewSet, basename="photographer")

# `me/wallet` is registered BEFORE `me` so the router matches the longer
# prefix first — otherwise `me/wallet/` resolves as the `me` viewset with a
# lookup value of "wallet".
router.register("me/wallet", WalletViewSet, basename="wallet")
router.register("me", MyProfileViewSet, basename="my-profile")

urlpatterns = router.urls
