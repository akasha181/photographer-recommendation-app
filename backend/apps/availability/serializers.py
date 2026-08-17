"""
Availability serializers.

These describe computed dataclasses (`DayAvailability`), not model rows, so
they are plain `Serializer`s rather than `ModelSerializer`s. Declaring them
explicitly still buys the Swagger documentation that drf-spectacular
generates from them.
"""

from rest_framework import serializers

from apps.availability.models import BlackoutDate


class DayAvailabilitySerializer(serializers.Serializer):
    """One day in the booking calendar."""

    date = serializers.DateField(read_only=True)
    is_available = serializers.BooleanField(read_only=True)
    reason = serializers.CharField(
        read_only=True,
        help_text="PAST | TOO_SOON | WEEKLY_OFF | BLACKOUT | FULLY_BOOKED | "
                  "NOT_ACCEPTING — empty when the date is available.",
    )
    message = serializers.CharField(read_only=True)
    booked_times = serializers.ListField(child=serializers.CharField(), read_only=True)
    remaining_slots = serializers.IntegerField(read_only=True)
    start_time = serializers.TimeField(read_only=True, format="%H:%M", allow_null=True)
    end_time = serializers.TimeField(read_only=True, format="%H:%M", allow_null=True)


class AvailabilityCalendarSerializer(serializers.Serializer):
    """The payload the booking screen's date picker consumes."""

    photographer_id = serializers.IntegerField(read_only=True)
    start_date = serializers.DateField(read_only=True)
    end_date = serializers.DateField(read_only=True)
    earliest_bookable_date = serializers.DateField(read_only=True)
    is_accepting_bookings = serializers.BooleanField(read_only=True)
    days = DayAvailabilitySerializer(many=True, read_only=True)


class DayDetailSerializer(DayAvailabilitySerializer):
    """A single date plus the start times the form may offer for it."""

    available_start_times = serializers.ListField(
        child=serializers.CharField(), read_only=True
    )


class AvailabilityRuleSerializer(serializers.Serializer):
    """The photographer's weekly working pattern, for the profile screen."""

    weekday = serializers.IntegerField(read_only=True)
    weekday_label = serializers.CharField(source="get_weekday_display", read_only=True)
    is_available = serializers.BooleanField(read_only=True)
    start_time = serializers.TimeField(read_only=True, format="%H:%M")
    end_time = serializers.TimeField(read_only=True, format="%H:%M")
    max_bookings = serializers.IntegerField(read_only=True)


# ═══════════════════════════════════════════════════════════════════════════
# MODULE 5 — the photographer editing their own calendar
# ═══════════════════════════════════════════════════════════════════════════
class WeeklyRuleWriteSerializer(serializers.Serializer):
    weekday = serializers.IntegerField(min_value=0, max_value=6)
    is_available = serializers.BooleanField(default=True)
    start_time = serializers.TimeField(required=False)
    end_time = serializers.TimeField(required=False)
    max_bookings = serializers.IntegerField(
        required=False, min_value=1, max_value=10, default=1,
        help_text="How many separate shoots you will take on this weekday.",
    )


class WeeklyScheduleWriteSerializer(serializers.Serializer):
    """
    The whole week in one request.

    The screen is a single form with seven rows, so it saves as one unit —
    seven separate PATCHes would leave a half-applied week if the connection
    dropped partway, and the calendar would then mix the old pattern with the
    new one.
    """

    rules = WeeklyRuleWriteSerializer(many=True)

    def validate_rules(self, value):
        if not value:
            raise serializers.ValidationError("Send at least one weekday.")
        seen = [rule["weekday"] for rule in value]
        if len(seen) != len(set(seen)):
            raise serializers.ValidationError("Each weekday may appear only once.")
        return value


class BlackoutSerializer(serializers.ModelSerializer):
    days = serializers.SerializerMethodField()

    class Meta:
        model = BlackoutDate
        fields = (
            "id", "start_date", "end_date", "days", "reason",
            "is_full_day", "start_time", "end_time", "created_at",
        )

    def get_days(self, obj) -> int:
        return (obj.end_date - obj.start_date).days + 1


class BlackoutWriteSerializer(serializers.Serializer):
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    reason = serializers.CharField(
        max_length=200, required=False, allow_blank=True, default=""
    )
    is_full_day = serializers.BooleanField(default=True)
    start_time = serializers.TimeField(required=False, allow_null=True)
    end_time = serializers.TimeField(required=False, allow_null=True)


class BlackoutResultSerializer(serializers.Serializer):
    """
    The created block, plus what it collides with.

    Blocking a range does NOT cancel bookings inside it — a commitment already
    made stays made. Reporting the count lets the photographer cancel those
    deliberately, with a reason the buyer sees, instead of discovering the
    clash on the day.
    """

    blackout = BlackoutSerializer(read_only=True)
    conflicting_bookings = serializers.IntegerField(read_only=True)


class MyCalendarSerializer(serializers.Serializer):
    """Everything the photographer's calendar screen renders, in one response."""

    is_accepting_bookings = serializers.BooleanField(read_only=True)
    rules = AvailabilityRuleSerializer(many=True, read_only=True)
    blackouts = BlackoutSerializer(many=True, read_only=True)
