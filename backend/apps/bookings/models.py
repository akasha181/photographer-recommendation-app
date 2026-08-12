"""
Bookings — the platform's central transaction.

TWO DESIGN DECISIONS WORTH DEFENDING
------------------------------------
1. PRICE IS SNAPSHOTTED, NOT LOOKED UP.
   `unit_price`, `total_price` and `commission_amount` are copied onto the
   booking at creation. If the photographer raises their price next week, the
   buyer's existing booking, invoice and history must not silently change.
   A foreign key to Service alone would give exactly that bug.

2. STATUS HISTORY IS A SEPARATE TABLE.
   The `status` column tells you where a booking is now. It cannot tell you
   who rejected it, when, or why — and those are precisely the questions asked
   during a dispute. BookingStatusHistory is append-only and answers them.
"""

from decimal import Decimal

from django.db import models
from django.utils import timezone

from apps.bookings.constants import (
    BLOCKING_STATUSES,
    BookingStatus,
    CancellationReason,
    PaymentMethod,
    PaymentStatus,
)
from apps.core.models import BaseModel, TimeStampedModel, UUIDModel


class BookingQuerySet(models.QuerySet):
    def for_buyer(self, user):
        return self.filter(buyer=user)

    def for_photographer(self, user):
        return self.filter(photographer__user=user)

    def for_user(self, user):
        from apps.core.constants import UserRole

        if user.role == UserRole.PHOTOGRAPHER:
            return self.for_photographer(user)
        return self.for_buyer(user)

    def active(self):
        """Bookings that still occupy a calendar slot."""
        return self.filter(status__in=BLOCKING_STATUSES)

    def completed(self):
        return self.filter(status=BookingStatus.COMPLETED)

    def upcoming(self):
        return self.filter(
            status=BookingStatus.ACCEPTED, event_date__gte=timezone.localdate()
        )

    def with_details(self):
        """Every list endpoint must use this — it kills the N+1 query problem."""
        return self.select_related(
            "buyer", "photographer", "photographer__user", "service", "service__category"
        )


class Booking(UUIDModel, BaseModel):
    # ─── Parties ─────────────────────────────────────────────────────────────
    buyer = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, related_name="bookings_made"
    )
    photographer = models.ForeignKey(
        "profiles.PhotographerProfile", on_delete=models.PROTECT,
        related_name="bookings_received",
    )

    # PROTECT on both: a booking is a financial record. Deleting a user must
    # never cascade away the other party's history. Accounts are soft-deleted
    # and anonymised instead (see accounts/services.delete_account).

    # ─── What was booked ─────────────────────────────────────────────────────
    service = models.ForeignKey(
        "catalog.Service", on_delete=models.PROTECT, related_name="bookings"
    )
    package = models.ForeignKey(
        "catalog.ServicePackage", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="bookings",
    )
    category = models.ForeignKey(
        "catalog.Category", on_delete=models.PROTECT, related_name="bookings",
        help_text="Copied from the service so analytics survive service deletion.",
    )

    # ─── When & where ────────────────────────────────────────────────────────
    event_date = models.DateField(db_index=True)
    start_time = models.TimeField()
    end_time = models.TimeField(null=True, blank=True)
    duration_hours = models.PositiveSmallIntegerField(default=4)

    location_address = models.CharField(max_length=300)
    location_city = models.CharField(max_length=80, db_index=True)
    location_latitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True
    )
    location_longitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True
    )

    # ─── Price snapshot (immutable once created) ─────────────────────────────
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    quantity = models.PositiveSmallIntegerField(default=1)
    travel_fee = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0.00")
    )
    discount = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0.00")
    )
    total_price = models.DecimalField(max_digits=12, decimal_places=2, db_index=True)

    commission_percent = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("10.00")
    )
    commission_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    photographer_payout = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )

    # ─── State ───────────────────────────────────────────────────────────────
    status = models.CharField(
        max_length=16, choices=BookingStatus.choices,
        default=BookingStatus.PENDING, db_index=True,
    )

    # ─── Details ─────────────────────────────────────────────────────────────
    guest_count = models.PositiveIntegerField(null=True, blank=True)
    notes = models.TextField(blank=True, max_length=2000)
    special_requirements = models.TextField(blank=True, max_length=1000)

    # ─── Lifecycle timestamps (answer "how fast do they respond?") ───────────
    expires_at = models.DateTimeField(
        db_index=True, help_text="PENDING bookings auto-expire at this moment."
    )
    responded_at = models.DateTimeField(null=True, blank=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    rejected_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    rejection_reason = models.TextField(blank=True, max_length=500)
    cancellation_reason = models.CharField(
        max_length=32, choices=CancellationReason.choices, blank=True
    )
    cancellation_note = models.TextField(blank=True, max_length=500)
    cancelled_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="bookings_cancelled",
    )

    # ─── Flags ───────────────────────────────────────────────────────────────
    has_review = models.BooleanField(default=False, db_index=True)
    buyer_confirmed_completion = models.BooleanField(default=False)
    photographer_marked_complete = models.BooleanField(default=False)

    objects = BookingQuerySet.as_manager()

    class Meta:
        db_table = "bookings"
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["buyer", "status"], name="idx_booking_buyer_status"),
            models.Index(
                fields=["photographer", "status"], name="idx_booking_photog_status"
            ),
            models.Index(
                fields=["status", "expires_at"], name="idx_booking_expiry_sweep"
            ),
            models.Index(
                fields=["photographer", "event_date"], name="idx_booking_calendar"
            ),
            models.Index(fields=["-created_at"], name="idx_booking_recent"),
        ]
        constraints = [
            # THE double-booking guard. Even if the application logic is
            # bypassed — a race, a bad migration, a manual SQL insert — MySQL
            # itself refuses to create two live bookings for the same slot.
            models.UniqueConstraint(
                fields=["photographer", "event_date", "start_time"],
                condition=models.Q(status__in=["PENDING", "ACCEPTED"]),
                name="uniq_active_booking_slot",
            ),
            models.CheckConstraint(
                check=models.Q(total_price__gte=0), name="ck_booking_total_positive"
            ),
            models.CheckConstraint(
                check=models.Q(quantity__gt=0), name="ck_booking_quantity_positive"
            ),
        ]

    def __str__(self) -> str:
        return f"Booking #{self.pk} — {self.status}"

    # ─── Derived properties (no DB access) ───────────────────────────────────
    @property
    def reference(self) -> str:
        """Human-facing booking id shown in the app and on receipts."""
        return f"SNP-{self.pk:06d}"

    @property
    def is_active(self) -> bool:
        return self.status in BLOCKING_STATUSES

    @property
    def is_terminal(self) -> bool:
        from apps.bookings.constants import ALLOWED_TRANSITIONS

        return not ALLOWED_TRANSITIONS.get(self.status)

    @property
    def is_reviewable(self) -> bool:
        return self.status == BookingStatus.COMPLETED and not self.has_review

    @property
    def days_until_event(self) -> int:
        return (self.event_date - timezone.localdate()).days

    @property
    def response_time_hours(self) -> float | None:
        """Used to maintain PhotographerProfile.avg_response_time_hours."""
        if not self.responded_at:
            return None
        return round((self.responded_at - self.created_at).total_seconds() / 3600, 2)

    def calculate_totals(self) -> None:
        """Recompute money columns from their parts. Called before save."""
        subtotal = (self.unit_price * self.quantity) + self.travel_fee - self.discount
        self.total_price = max(subtotal, Decimal("0.00"))
        self.commission_amount = (
            self.total_price * self.commission_percent / Decimal("100")
        ).quantize(Decimal("0.01"))
        self.photographer_payout = self.total_price - self.commission_amount


class BookingStatusHistory(TimeStampedModel):
    """
    Append-only audit trail of every state change.

    Never updated, never deleted. During a dispute this table is the evidence.
    """

    booking = models.ForeignKey(
        Booking, on_delete=models.CASCADE, related_name="status_history"
    )
    from_status = models.CharField(max_length=16, choices=BookingStatus.choices, blank=True)
    to_status = models.CharField(max_length=16, choices=BookingStatus.choices)
    changed_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="booking_status_changes",
        help_text="NULL means the change was made by the system (expiry job).",
    )
    actor_role = models.CharField(max_length=20, blank=True)
    note = models.TextField(blank=True, max_length=500)

    class Meta:
        db_table = "booking_status_history"
        ordering = ("created_at",)
        verbose_name_plural = "Booking status history"
        indexes = [
            models.Index(fields=["booking", "created_at"], name="idx_bsh_timeline"),
        ]

    def __str__(self) -> str:
        return f"#{self.booking_id}: {self.from_status or '∅'} → {self.to_status}"


class BookingPayment(TimeStampedModel):
    """
    Offline payment record.

    The proposal scopes payments to cash/bank transfer, so this table does not
    move money — it records what the parties say happened and lets an admin
    verify it. When a real gateway is added later, it plugs in here without
    changing the booking model.
    """

    booking = models.OneToOneField(
        Booking, on_delete=models.CASCADE, related_name="payment"
    )
    method = models.CharField(
        max_length=20, choices=PaymentMethod.choices, default=PaymentMethod.CASH
    )
    status = models.CharField(
        max_length=20, choices=PaymentStatus.choices,
        default=PaymentStatus.UNPAID, db_index=True,
    )

    advance_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    paid_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )

    transaction_reference = models.CharField(max_length=100, blank=True)
    receipt_image = models.ImageField(
        upload_to="booking_receipts/%Y/%m/", null=True, blank=True
    )

    is_verified = models.BooleanField(default=False)
    verified_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="verified_payments",
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    note = models.TextField(blank=True, max_length=500)

    class Meta:
        db_table = "booking_payments"

    def __str__(self) -> str:
        return f"Payment for #{self.booking_id} — {self.status}"

    @property
    def outstanding(self) -> Decimal:
        return max(self.booking.total_price - self.paid_amount, Decimal("0.00"))
