"""
Platform Administration routes — mounted at /api/v1/admin/

Note the mount point: `/api/v1/admin/` is the product admin API. Django's own
admin lives at `/django-admin/` and is emergency ops only.
"""

from rest_framework.routers import DefaultRouter

from apps.administration.views import (
    AdminBookingViewSet,
    AdminDashboardViewSet,
    AdminProductViewSet,
    AdminTopUpViewSet,
    AdminUserViewSet,
    ApprovalViewSet,
    AuditLogViewSet,
    BroadcastViewSet,
    ModerationViewSet,
    PlatformSettingViewSet,
)

app_name = "administration"

router = DefaultRouter()
router.register("dashboard", AdminDashboardViewSet, basename="admin-dashboard")
router.register("approvals", ApprovalViewSet, basename="admin-approval")
router.register("flags", ModerationViewSet, basename="admin-flag")
router.register("users", AdminUserViewSet, basename="admin-user")
router.register("topups", AdminTopUpViewSet, basename="admin-topup")
router.register("products", AdminProductViewSet, basename="admin-product")
router.register("bookings", AdminBookingViewSet, basename="admin-booking")
router.register("audit", AuditLogViewSet, basename="admin-audit")
router.register("settings", PlatformSettingViewSet, basename="admin-setting")
router.register("broadcasts", BroadcastViewSet, basename="admin-broadcast")

urlpatterns = router.urls
