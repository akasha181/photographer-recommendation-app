"""Recommendation routes — mounted at /api/v1/recommendations/"""

from django.urls import path

from apps.recommendations.views import (
    RecommendationClickView,
    RecommendationStatusView,
    RecommendationView,
)

app_name = "recommendations"

urlpatterns = [
    path("", RecommendationView.as_view(), name="recommendations"),
    path("click/", RecommendationClickView.as_view(), name="recommendation-click"),
    path("status/", RecommendationStatusView.as_view(), name="recommendation-status"),
]
