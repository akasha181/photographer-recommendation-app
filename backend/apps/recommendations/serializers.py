"""Recommendation serializers."""

from rest_framework import serializers

from apps.profiles.serializers import PhotographerListSerializer


class RecommendationSerializer(PhotographerListSerializer):
    """
    A photographer plus why they were recommended.

    `reason` is not decoration — see engine._reason(). A score with no
    explanation is a score users will not act on.
    """

    score = serializers.FloatField(read_only=True)
    reason = serializers.CharField(read_only=True)
    strategy = serializers.CharField(read_only=True)

    # Component scores, useful for the evaluation dashboard and for debugging
    # why a particular photographer ranked where they did.
    content_score = serializers.FloatField(read_only=True)
    collab_score = serializers.FloatField(read_only=True)
    business_score = serializers.FloatField(read_only=True)

    class Meta(PhotographerListSerializer.Meta):
        fields = PhotographerListSerializer.Meta.fields + (
            "score", "reason", "strategy",
            "content_score", "collab_score", "business_score",
        )
