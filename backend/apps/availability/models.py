"""
Availability calendar.

THE MODELLING PROBLEM
---------------------
"When is this photographer free?" cannot be answered by storing free days,
because that would mean inserting 365 rows per photographer per year — 73,000
rows for 200 photographers, almost all of them saying "yes, available".

Instead we store the *rules* and the *exceptions*:

  AvailabilityRule  — the weekly pattern ("I work Mon-Sat, 9am-6pm")
  BlackoutDate      — specific dates that override the pattern ("away 12-15 Aug")
  TimeSlot          — optional fine-grained slots for photographers who want
                      to sell half-day windows rather than whole days

Availability is then computed: a date is bookable if the weekday rule allows
it, no blackout covers it, and no ACCEPTED booking already occupies it.
"""

from django.db import models

from apps.core.models import TimeStampedModel


class Weekday(models.IntegerChoices):
    MONDAY = 0, "Monday"
    TUESDAY = 1, "Tuesday"
    WEDNESDAY = 2, "Wednesday"
    THURSDAY = 3, "Thursday"
    FRIDAY = 4, "Friday"
    SATURDAY = 5, "Saturday"
    SUNDAY = 6, "Sunday"


class AvailabilityRule(TimeStampedModel):
    """The recurring weekly working pattern."""

    photographer = models.ForeignKey(
        "profiles.PhotographerProfile", on_delete=models.CASCADE,
        related_name="availability_rules",
    )
    weekday = models.PositiveSmallIntegerField(choices=Weekday.choices)
    is_available = models.BooleanField(default=True)
    start_time = models.TimeField(default="09:00")
    end_time = models.TimeField(default="18:00")
    max_bookings = models.PositiveSmallIntegerField(
        default=1, help_text="How many separate shoots can be taken this weekday."
    )

    class Meta:
        db_table = "availability_rules"
        ordering = ("weekday",)
        constraints = [
            models.UniqueConstraint(
                fields=["photographer", "weekday"], name="uniq_rule_per_weekday"
            ),
            models.CheckConstraint(
                check=models.Q(end_time__gt=models.F("start_time")),
                name="ck_rule_end_after_start",
            ),
        ]

    def __str__(self) -> str:
        state = "available" if self.is_available else "off"
        return f"{self.get_weekday_display()}: {state}"


class BlackoutDate(TimeStampedModel):
    """A specific date range the photographer cannot work — beats the rule."""

    photographer = models.ForeignKey(
        "profiles.PhotographerProfile", on_delete=models.CASCADE,
        related_name="blackout_dates",
    )
    start_date = models.DateField(db_index=True)
    end_date = models.DateField(db_index=True)
    reason = models.CharField(max_length=200, blank=True)
    is_full_day = models.BooleanField(default=True)
    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)

    class Meta:
        db_table = "blackout_dates"
        indexes = [
            models.Index(
                fields=["photographer", "start_date", "end_date"],
                name="idx_blackout_lookup",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(end_date__gte=models.F("start_date")),
                name="ck_blackout_end_after_start",
            ),
        ]

    def __str__(self) -> str:
        return f"Blackout {self.start_date} → {self.end_date}"

    def covers(self, date) -> bool:
        return self.start_date <= date <= self.end_date


class TimeSlot(TimeStampedModel):
    """
    An explicit bookable window on a specific date.

    Optional: most photographers sell whole days and never create these. They
    exist for studios that sell "10:00-13:00" and "14:00-17:00" separately.
    """

    photographer = models.ForeignKey(
        "profiles.PhotographerProfile", on_delete=models.CASCADE,
        related_name="time_slots",
    )
    date = models.DateField(db_index=True)
    start_time = models.TimeField()
    end_time = models.TimeField()

    is_booked = models.BooleanField(default=False, db_index=True)
    booking = models.OneToOneField(
        "bookings.Booking", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="reserved_slot",
    )
    price_override = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        help_text="Peak-season pricing for this specific slot.",
    )

    class Meta:
        db_table = "time_slots"
        ordering = ("date", "start_time")
        constraints = [
            models.UniqueConstraint(
                fields=["photographer", "date", "start_time"],
                name="uniq_slot_per_photog_datetime",
            ),
            models.CheckConstraint(
                check=models.Q(end_time__gt=models.F("start_time")),
                name="ck_slot_end_after_start",
            ),
        ]
        indexes = [
            models.Index(
                fields=["photographer", "date", "is_booked"],
                name="idx_slot_availability",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.date} {self.start_time}-{self.end_time}"
