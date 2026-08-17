"""
Analytics serializers.

Every rate is sent pre-computed and every gap pre-filled. A chart that has to
divide on the client is a chart that will show NaN when a denominator is zero,
and one that has to fill its own gaps will draw December next to March with no
visible break.
"""

from rest_framework import serializers


class OverviewSerializer(serializers.Serializer):
    pending_requests = serializers.IntegerField(read_only=True)
    upcoming_shoots = serializers.IntegerField(read_only=True)
    completed_shoots = serializers.IntegerField(read_only=True)
    bookings_this_month = serializers.IntegerField(read_only=True)
    earnings_this_month = serializers.DecimalField(
        max_digits=14, decimal_places=2, read_only=True
    )
    lifetime_earnings = serializers.DecimalField(
        max_digits=14, decimal_places=2, read_only=True
    )
    avg_rating = serializers.DecimalField(max_digits=3, decimal_places=2, read_only=True)
    reviews_count = serializers.IntegerField(read_only=True)
    success_rate = serializers.DecimalField(
        max_digits=4, decimal_places=3, read_only=True
    )
    response_time_hours = serializers.DecimalField(
        max_digits=6, decimal_places=2, read_only=True
    )
    profile_views = serializers.IntegerField(read_only=True)
    is_accepting_bookings = serializers.BooleanField(read_only=True)


class RevenuePointSerializer(serializers.Serializer):
    year = serializers.IntegerField(read_only=True)
    month = serializers.IntegerField(read_only=True)
    label = serializers.CharField(read_only=True)
    bookings_completed = serializers.IntegerField(read_only=True)
    gross_revenue = serializers.DecimalField(
        max_digits=14, decimal_places=2, read_only=True
    )
    net_earnings = serializers.DecimalField(
        max_digits=14, decimal_places=2, read_only=True
    )
    growth_percent = serializers.FloatField(read_only=True)


class DailyPointSerializer(serializers.Serializer):
    date = serializers.DateField(read_only=True)
    profile_views = serializers.IntegerField(read_only=True)
    bookings_created = serializers.IntegerField(read_only=True)
    bookings_completed = serializers.IntegerField(read_only=True)
    revenue = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)


class FunnelSerializer(serializers.Serializer):
    """
    Seen → clicked → enquired → booked.

    Where it narrows is the actionable part: plenty of views and no bookings
    is a pricing or portfolio problem; no views is a visibility problem.
    """

    days = serializers.IntegerField(read_only=True)
    impressions = serializers.IntegerField(read_only=True)
    profile_views = serializers.IntegerField(read_only=True)
    clicks = serializers.IntegerField(read_only=True)
    inquiries = serializers.IntegerField(read_only=True)
    bookings = serializers.IntegerField(read_only=True)
    completed = serializers.IntegerField(read_only=True)
    view_to_booking_rate = serializers.FloatField(read_only=True)


class TopServiceSerializer(serializers.Serializer):
    service_id = serializers.IntegerField(read_only=True)
    title = serializers.CharField(read_only=True)
    bookings = serializers.IntegerField(read_only=True)
    completed = serializers.IntegerField(read_only=True)
    revenue = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)


class CategorySplitSerializer(serializers.Serializer):
    category = serializers.CharField(read_only=True)
    bookings = serializers.IntegerField(read_only=True)
    revenue = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)


class DashboardSerializer(serializers.Serializer):
    """One response for the whole screen — the app should not fire six requests."""

    overview = OverviewSerializer(read_only=True)
    revenue_series = RevenuePointSerializer(many=True, read_only=True)
    daily_series = DailyPointSerializer(many=True, read_only=True)
    funnel = FunnelSerializer(read_only=True)
    top_services = TopServiceSerializer(many=True, read_only=True)
    category_split = CategorySplitSerializer(many=True, read_only=True)
    upcoming = serializers.SerializerMethodField()

    def get_upcoming(self, obj) -> list:
        from apps.bookings.serializers import BookingListSerializer

        return BookingListSerializer(
            obj["upcoming"], many=True, context=self.context
        ).data
