"""
Availability serializers.

These describe computed dataclasses (`DayAvailability`), not model rows, so
they are plain `Serializer`s rather than `ModelSerializer`s. Declaring them
explicitly still buys the Swagger documentation that drf-spectacular
generates from them.
"""

from rest_framework import serializers


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
