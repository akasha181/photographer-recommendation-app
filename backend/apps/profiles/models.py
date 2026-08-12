"""
Role-specific profiles and the wallet.

WHY PROFILES ARE SEPARATE TABLES
--------------------------------
A buyer needs `budget_range`; a photographer needs `portfolio_score`. Putting
both on `users` would give every row dozens of columns that are NULL for half
the population, and every query would read bytes it does not need. One table
per role keeps each row dense and lets each side evolve independently.

WHY METRICS ARE DENORMALISED ONTO PhotographerProfile
-----------------------------------------------------
`avg_rating`, `reviews_count`, `completed_bookings` and friends could all be
computed with aggregate queries. They are stored instead, because the search
screen ranks 200 photographers by rating on every keystroke — recomputing
AVG(rating) with a JOIN per row would turn a 20ms query into a 2s one.

The trade-off is that these columns can drift from the truth. That is managed:
they are updated inside the same transaction as the event that changes them
(see reviews/services.py), and a nightly Celery job recomputes them from
scratch as a self-healing backstop.
"""

from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.core.models import BaseModel, TimeStampedModel
from apps.core.utils import upload_to


class BuyerProfile(TimeStampedModel):
    user = models.OneToOneField(
        "accounts.User", on_delete=models.CASCADE, related_name="buyer_profile"
    )

    # ─── Preferences (feed the recommendation engine's cold-start path) ──────
    preferred_categories = models.ManyToManyField(
        "catalog.Category", blank=True, related_name="interested_buyers"
    )
    budget_min = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    budget_max = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )

    # ─── Lifetime counters ───────────────────────────────────────────────────
    total_bookings = models.PositiveIntegerField(default=0)
    completed_bookings = models.PositiveIntegerField(default=0)
    cancelled_bookings = models.PositiveIntegerField(default=0)
    total_spent = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal("0.00")
    )
    reviews_written = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "buyer_profiles"
        verbose_name = "Buyer profile"

    def __str__(self) -> str:
        return f"Buyer: {self.user.full_name}"

    @property
    def cancellation_rate(self) -> float:
        if not self.total_bookings:
            return 0.0
        return round(self.cancelled_bookings / self.total_bookings, 4)


class PhotographerProfile(BaseModel):
    user = models.OneToOneField(
        "accounts.User", on_delete=models.CASCADE, related_name="photographer_profile"
    )

    # ─── Public identity ─────────────────────────────────────────────────────
    business_name = models.CharField(max_length=140, blank=True, db_index=True)
    tagline = models.CharField(max_length=180, blank=True)
    bio = models.TextField(blank=True, max_length=2000)
    cover_image = models.ImageField(
        upload_to=upload_to("covers"), null=True, blank=True
    )

    # ─── Professional details ────────────────────────────────────────────────
    years_experience = models.PositiveSmallIntegerField(
        default=0, validators=[MaxValueValidator(60)]
    )
    categories = models.ManyToManyField(
        "catalog.Category", related_name="photographers", blank=True
    )
    specializations = models.ManyToManyField(
        "catalog.Specialization", related_name="photographers", blank=True
    )
    equipment = models.TextField(blank=True, max_length=1000)
    languages = models.CharField(max_length=200, blank=True, default="English, Urdu")

    # ─── Pricing & reach ─────────────────────────────────────────────────────
    base_price = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00"), db_index=True,
        help_text="Starting price in PKR — the 'from Rs X' shown on listings.",
    )
    travel_available = models.BooleanField(default=True)
    service_radius_km = models.PositiveSmallIntegerField(default=50)

    # ─── Social ──────────────────────────────────────────────────────────────
    website = models.URLField(blank=True)
    instagram = models.CharField(max_length=100, blank=True)
    facebook = models.CharField(max_length=100, blank=True)

    # ─── Approval workflow (admin gate before appearing publicly) ────────────
    is_approved = models.BooleanField(default=False, db_index=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="approved_photographers",
    )
    rejection_reason = models.TextField(blank=True)
    submitted_for_approval_at = models.DateTimeField(null=True, blank=True)

    # ─── Identity verification ───────────────────────────────────────────────
    cnic_number = models.CharField(max_length=20, blank=True)
    cnic_image = models.ImageField(
        upload_to=upload_to("verification"), null=True, blank=True
    )
    is_verified = models.BooleanField(
        default=False, help_text="Blue-tick badge shown on the profile."
    )
    is_featured = models.BooleanField(default=False, db_index=True)

    # ─── Availability ────────────────────────────────────────────────────────
    is_accepting_bookings = models.BooleanField(default=True, db_index=True)
    last_active_at = models.DateTimeField(null=True, blank=True)

    # ═══════════════════════════════════════════════════════════════════════
    # DENORMALISED METRICS — maintained by services, healed nightly.
    # These columns map 1:1 onto the features in photographer_profiles.csv,
    # which is what makes the CSV directly loadable as seed data.
    # ═══════════════════════════════════════════════════════════════════════
    avg_rating = models.DecimalField(
        max_digits=3, decimal_places=2, default=Decimal("0.00"), db_index=True,
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("5"))],
    )
    bayesian_rating = models.DecimalField(
        max_digits=3, decimal_places=2, default=Decimal("0.00"), db_index=True,
        help_text="Rating smoothed toward the platform mean; used for ranking.",
    )
    reviews_count = models.PositiveIntegerField(default=0)

    total_bookings = models.PositiveIntegerField(default=0)
    completed_bookings = models.PositiveIntegerField(default=0)
    cancelled_bookings = models.PositiveIntegerField(default=0)
    success_rate = models.DecimalField(
        max_digits=4, decimal_places=3, default=Decimal("0.000"),
        help_text="completed / (completed + cancelled + rejected)",
    )

    avg_response_time_hours = models.DecimalField(
        max_digits=6, decimal_places=2, default=Decimal("24.00"),
        help_text="Hours to respond to a booking request. LOWER IS BETTER — "
                  "the ranking model inverts this before use.",
    )

    portfolio_score = models.PositiveIntegerField(
        default=0,
        help_text="Composite engagement score (0-999) from portfolio quality "
                  "and interaction volume.",
    )
    profile_views = models.PositiveIntegerField(default=0)
    search_appearances = models.PositiveIntegerField(default=0)

    total_earnings = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal("0.00")
    )

    class Meta:
        db_table = "photographer_profiles"
        verbose_name = "Photographer profile"
        indexes = [
            # Composite index matching the exact WHERE+ORDER BY of the main
            # discovery query: approved & accepting, ranked by smoothed rating.
            models.Index(
                fields=["is_approved", "is_accepting_bookings", "-bayesian_rating"],
                name="idx_photog_discovery",
            ),
            models.Index(fields=["base_price"], name="idx_photog_price"),
            models.Index(fields=["is_featured", "-bayesian_rating"], name="idx_photog_featured"),
            models.Index(fields=["-completed_bookings"], name="idx_photog_popularity"),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(avg_rating__gte=0) & models.Q(avg_rating__lte=5),
                name="ck_photog_rating_range",
            ),
            models.CheckConstraint(
                check=models.Q(base_price__gte=0), name="ck_photog_price_positive"
            ),
        ]

    def __str__(self) -> str:
        return self.business_name or f"Photographer: {self.user.full_name}"

    @property
    def display_name(self) -> str:
        return self.business_name or self.user.full_name

    @property
    def city(self) -> str:
        return self.user.city

    @property
    def is_publicly_visible(self) -> bool:
        """The single source of truth for 'should this appear in search'."""
        return (
            self.is_approved
            and not self.is_deleted
            and self.user.is_active
            and not self.user.is_blocked
        )

    def recompute_bayesian(self) -> Decimal:
        from django.conf import settings

        from apps.core.utils import bayesian_average

        value = bayesian_average(
            float(self.avg_rating),
            self.reviews_count,
            settings.BAYESIAN_PRIOR_COUNT,
            settings.BAYESIAN_PRIOR_RATING,
        )
        return Decimal(f"{value:.2f}")


# ═══════════════════════════════════════════════════════════════════════════
# WALLET
# The proposal excludes an online payment gateway, so digital-product
# purchases run on an internal wallet: the buyer transfers money by bank/
# Easypaisa, uploads the receipt, an admin verifies it and credits the wallet.
# Purchases then debit the wallet instantly, which keeps downloads immediate
# while staying inside the declared scope.
# ═══════════════════════════════════════════════════════════════════════════
class Wallet(TimeStampedModel):
    user = models.OneToOneField(
        "accounts.User", on_delete=models.CASCADE, related_name="wallet"
    )
    balance = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal("0.00")
    )
    total_credited = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal("0.00")
    )
    total_debited = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal("0.00")
    )

    class Meta:
        db_table = "wallets"
        constraints = [
            models.CheckConstraint(
                check=models.Q(balance__gte=0), name="ck_wallet_no_overdraft"
            )
        ]

    def __str__(self) -> str:
        return f"Wallet({self.user.email}): Rs {self.balance}"


class WalletTransactionType(models.TextChoices):
    TOPUP = "TOPUP", "Top-up"
    PURCHASE = "PURCHASE", "Purchase"
    REFUND = "REFUND", "Refund"
    PAYOUT = "PAYOUT", "Payout to photographer"
    EARNING = "EARNING", "Sale earning"
    ADJUSTMENT = "ADJUSTMENT", "Admin adjustment"


class WalletTransaction(TimeStampedModel):
    """
    Append-only ledger.

    Every balance change writes a row recording the balance before and after.
    If the two ever disagree with the running total, the bug is provable
    rather than merely suspected — which is the whole point of a ledger.
    """

    wallet = models.ForeignKey(
        Wallet, on_delete=models.PROTECT, related_name="transactions"
    )
    txn_type = models.CharField(
        max_length=16, choices=WalletTransactionType.choices, db_index=True
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    balance_before = models.DecimalField(max_digits=14, decimal_places=2)
    balance_after = models.DecimalField(max_digits=14, decimal_places=2)

    reference = models.CharField(
        max_length=64, blank=True, db_index=True,
        help_text="Related order/booking identifier.",
    )
    description = models.CharField(max_length=255, blank=True)
    performed_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="wallet_actions",
    )

    class Meta:
        db_table = "wallet_transactions"
        indexes = [
            models.Index(fields=["wallet", "-created_at"], name="idx_wallet_txn_recent"),
        ]

    def __str__(self) -> str:
        return f"{self.txn_type} Rs {self.amount} ({self.wallet_id})"


class TopUpStatus(models.TextChoices):
    PENDING = "PENDING", "Pending verification"
    APPROVED = "APPROVED", "Approved"
    REJECTED = "REJECTED", "Rejected"


class TopUpRequest(TimeStampedModel):
    """A bank-transfer receipt awaiting admin verification."""

    user = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="topup_requests"
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    method = models.CharField(
        max_length=32,
        choices=[
            ("BANK", "Bank transfer"),
            ("EASYPAISA", "Easypaisa"),
            ("JAZZCASH", "JazzCash"),
        ],
        default="BANK",
    )
    transaction_reference = models.CharField(max_length=100)
    receipt_image = models.ImageField(upload_to=upload_to("receipts"))

    status = models.CharField(
        max_length=16, choices=TopUpStatus.choices,
        default=TopUpStatus.PENDING, db_index=True,
    )
    reviewed_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="reviewed_topups",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    admin_note = models.TextField(blank=True)

    class Meta:
        db_table = "topup_requests"
        indexes = [
            models.Index(fields=["status", "-created_at"], name="idx_topup_queue"),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(amount__gt=0), name="ck_topup_amount_positive"
            ),
            # The same bank reference must never be credited twice.
            models.UniqueConstraint(
                fields=["transaction_reference"],
                condition=models.Q(status="APPROVED"),
                name="uniq_approved_txn_reference",
            ),
        ]

    def __str__(self) -> str:
        return f"Top-up Rs {self.amount} by {self.user_id} [{self.status}]"
