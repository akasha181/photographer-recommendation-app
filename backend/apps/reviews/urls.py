"""
Reviews & Ratings routes — mounted at /api/v1/reviews/

One viewset, because every route here is a view of the same resource. The
router emits its dynamic list routes (`photographers/…`, `pending/`, `mine/`)
BEFORE the detail route, which is what stops `/reviews/pending/` resolving as
`retrieve(pk="pending")`.
"""

from rest_framework.routers import DefaultRouter

from apps.reviews.views import ReviewViewSet

app_name = "reviews"

router = DefaultRouter()
router.register("", ReviewViewSet, basename="review")

urlpatterns = router.urls
