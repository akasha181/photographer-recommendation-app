"""Write-side business logic for profiles and the wallet."""

import logging
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.core.exceptions import BusinessRuleViolation, InsufficientBalance
from apps.profiles.models import (
    BuyerProfile,
    PhotographerProfile,
    TopUpRequest,
    TopUpStatus,
    Wallet,
    WalletTransaction,
    WalletTransactionType,
)

logger = logging.getLogger("snapsphere")


# ═══════════════════════════════════════════════════════════════════════════
# PROFILE CREATION
# ═══════════════════════════════════════════════════════════════════════════
def create_buyer_profile(user) -> BuyerProfile:
    profile, _ = BuyerProfile.objects.get_or_create(user=user)
    Wallet.objects.get_or_create(user=user)
    _ensure_notification_preference(user)
    return profile


def create_photographer_profile(user) -> PhotographerProfile:
    profile, _ = PhotographerProfile.objects.get_or_create(
        user=user, defaults={"business_name": user.full_name}
    )
    Wallet.objects.get_or_create(user=user)
    _ensure_notification_preference(user)
    _seed_default_availability(profile)
    return profile


def _ensure_notification_preference(user) -> None:
    from apps.notifications.models import NotificationPreference

    NotificationPreference.objects.get_or_create(user=user)


def _seed_default_availability(profile: PhotographerProfile) -> None:
    """
    Give new photographers a sensible Mon-Sat 9-6 calendar.

    Without this a brand-new photographer appears fully unavailable and can
    never receive a first booking — a silent dead end immediately after signup.
    """
    from apps.availability.models import AvailabilityRule

    if AvailabilityRule.objects.filter(photographer=profile).exists():
        return

    AvailabilityRule.objects.bulk_create(
        [
            AvailabilityRule(
                photographer=profile,
                weekday=day,
                is_available=day != 6,  # Sunday off by default
            )
            for day in range(7)
        ]
    )


# ═══════════════════════════════════════════════════════════════════════════
# APPROVAL
# ═══════════════════════════════════════════════════════════════════════════
@transaction.atomic
def submit_for_approval(profile: PhotographerProfile):
    """
    A photographer applies to be listed publicly.

    The completeness check runs here rather than in the admin queue so
    reviewers only ever see applications worth reviewing.
    """
    from apps.administration.models import ApprovalRequest, ApprovalStatus

    if profile.is_approved:
        raise BusinessRuleViolation("Your profile is already approved.")

    missing = []
    if not profile.bio or len(profile.bio) < 50:
        missing.append("a bio of at least 50 characters")
    if not profile.categories.exists():
        missing.append("at least one category")
    if not profile.services.filter(is_active=True).exists():
        missing.append("at least one active service")
    if profile.portfolio_images.count() < 5:
        missing.append("at least 5 portfolio images")
    if not profile.user.city:
        missing.append("your city")

    if missing:
        raise BusinessRuleViolation(
            "Your profile is incomplete. Please add " + ", ".join(missing) + "."
        )

    if ApprovalRequest.objects.filter(
        photographer=profile, status=ApprovalStatus.PENDING
    ).exists():
        raise BusinessRuleViolation("Your application is already under review.")

    request_obj = ApprovalRequest.objects.create(
        photographer=profile,
        submitted_data={
            "business_name": profile.business_name,
            "bio": profile.bio[:500],
            "years_experience": profile.years_experience,
            "categories": list(profile.categories.values_list("name", flat=True)),
            "service_count": profile.services.filter(is_active=True).count(),
            "portfolio_count": profile.portfolio_images.count(),
            "base_price": str(profile.base_price),
        },
    )
    profile.submitted_for_approval_at = timezone.now()
    profile.save(update_fields=["submitted_for_approval_at", "updated_at"])

    logger.info(
        "Photographer submitted for approval", extra={"photographer_id": profile.pk}
    )
    return request_obj


# ═══════════════════════════════════════════════════════════════════════════
# WALLET
# ═══════════════════════════════════════════════════════════════════════════
@transaction.atomic
def credit_wallet(user, amount: Decimal, *, txn_type: str, reference: str = "",
                  description: str = "", performed_by=None) -> Wallet:
    """
    Add money to a wallet and write a ledger row.

    select_for_update locks the wallet row for the rest of the transaction.
    Two concurrent credits would otherwise both read the same starting balance
    and one would silently overwrite the other.
    """
    if amount <= 0:
        raise BusinessRuleViolation("Credit amount must be greater than zero.")

    wallet = Wallet.objects.select_for_update().get(user=user)
    before = wallet.balance
    wallet.balance = before + amount
    wallet.total_credited += amount
    wallet.save(update_fields=["balance", "total_credited", "updated_at"])

    WalletTransaction.objects.create(
        wallet=wallet,
        txn_type=txn_type,
        amount=amount,
        balance_before=before,
        balance_after=wallet.balance,
        reference=reference,
        description=description,
        performed_by=performed_by,
    )
    logger.info("Wallet credited", extra={"user_id": user.id, "amount": str(amount)})
    return wallet


@transaction.atomic
def debit_wallet(user, amount: Decimal, *, txn_type: str, reference: str = "",
                 description: str = "") -> Wallet:
    """Deduct money, refusing to go negative."""
    if amount <= 0:
        raise BusinessRuleViolation("Debit amount must be greater than zero.")

    wallet = Wallet.objects.select_for_update().get(user=user)
    if wallet.balance < amount:
        raise InsufficientBalance(
            f"Your balance is Rs {wallet.balance} but this costs Rs {amount}. "
            f"Please top up Rs {amount - wallet.balance} more."
        )

    before = wallet.balance
    wallet.balance = before - amount
    wallet.total_debited += amount
    wallet.save(update_fields=["balance", "total_debited", "updated_at"])

    WalletTransaction.objects.create(
        wallet=wallet,
        txn_type=txn_type,
        amount=amount,
        balance_before=before,
        balance_after=wallet.balance,
        reference=reference,
        description=description,
    )
    return wallet


@transaction.atomic
def request_topup(user, *, amount: Decimal, method: str, transaction_reference: str,
                  receipt_image) -> TopUpRequest:
    """
    Submit a bank/Easypaisa receipt for verification.

    Nothing is credited here. The money is real only once an admin has looked
    at the receipt — the whole point of the manual gate is that the platform
    never takes a claimed transfer on trust. `approve_topup` does the crediting.
    """
    Wallet.objects.get_or_create(user=user)

    reference = transaction_reference.strip()
    if TopUpRequest.objects.filter(
        transaction_reference__iexact=reference, status=TopUpStatus.APPROVED
    ).exists():
        raise BusinessRuleViolation(
            "That transaction reference has already been credited."
        )
    if TopUpRequest.objects.filter(
        user=user, transaction_reference__iexact=reference, status=TopUpStatus.PENDING
    ).exists():
        raise BusinessRuleViolation(
            "You have already submitted that reference. It is awaiting review."
        )

    topup = TopUpRequest.objects.create(
        user=user,
        amount=amount,
        method=method,
        transaction_reference=reference,
        receipt_image=receipt_image,
    )
    logger.info(
        "Top-up requested", extra={"user_id": user.id, "amount": str(amount)}
    )
    return topup


@transaction.atomic
def update_buyer_profile(user, **data) -> BuyerProfile:
    """Preferences only — every counter on this table is derived."""
    profile, _ = BuyerProfile.objects.get_or_create(user=user)
    categories = data.pop("preferred_categories", None)

    for field, value in data.items():
        setattr(profile, field, value)
    profile.save()

    if categories is not None:
        profile.preferred_categories.set(categories)
    return profile


@transaction.atomic
def update_photographer_profile(profile: PhotographerProfile, **data) -> PhotographerProfile:
    """
    Self-service edits to a photographer's public listing.

    Approval state and every denormalised metric are filtered out by the
    serializer, not here — but the guard below matters regardless of what the
    serializer allowed: a photographer must not be able to un-pause bookings
    while suspended, because the booking service would then accept requests
    that the platform has decided should not reach them.
    """
    if data.get("is_accepting_bookings") and not profile.is_publicly_visible:
        raise BusinessRuleViolation(
            "Your account is not active, so bookings cannot be enabled."
        )

    for field, value in data.items():
        setattr(profile, field, value)
    profile.save()
    return profile


@transaction.atomic
def approve_topup(topup: TopUpRequest, admin_user) -> TopUpRequest:
    """Admin verifies a bank receipt and credits the wallet."""
    if topup.status != TopUpStatus.PENDING:
        raise BusinessRuleViolation(
            f"This top-up has already been {topup.get_status_display().lower()}."
        )

    topup.status = TopUpStatus.APPROVED
    topup.reviewed_by = admin_user
    topup.reviewed_at = timezone.now()
    topup.save(update_fields=["status", "reviewed_by", "reviewed_at", "updated_at"])

    credit_wallet(
        topup.user,
        topup.amount,
        txn_type=WalletTransactionType.TOPUP,
        reference=topup.transaction_reference,
        description=f"Top-up via {topup.get_method_display()}",
        performed_by=admin_user,
    )
    return topup


@transaction.atomic
def reject_topup(topup: TopUpRequest, admin_user, note: str) -> TopUpRequest:
    if topup.status != TopUpStatus.PENDING:
        raise BusinessRuleViolation("This top-up has already been reviewed.")

    topup.status = TopUpStatus.REJECTED
    topup.reviewed_by = admin_user
    topup.reviewed_at = timezone.now()
    topup.admin_note = note
    topup.save(
        update_fields=[
            "status", "reviewed_by", "reviewed_at", "admin_note", "updated_at",
        ]
    )
    return topup


# ═══════════════════════════════════════════════════════════════════════════
# METRIC MAINTENANCE
# The denormalised columns on PhotographerProfile are updated here, inside the
# same transaction as the event that changed them. The nightly Celery job
# calls the same functions as a self-healing pass.
# ═══════════════════════════════════════════════════════════════════════════
def refresh_photographer_rating(profile: PhotographerProfile) -> PhotographerProfile:
    from django.db.models import Avg, Count

    from apps.reviews.models import Review

    agg = Review.objects.visible().filter(photographer=profile).aggregate(
        avg=Avg("rating"), count=Count("id")
    )
    profile.avg_rating = Decimal(f"{agg['avg'] or 0:.2f}")
    profile.reviews_count = agg["count"] or 0
    profile.bayesian_rating = profile.recompute_bayesian()
    profile.save(
        update_fields=["avg_rating", "reviews_count", "bayesian_rating", "updated_at"]
    )
    return profile


def refresh_buyer_booking_metrics(user):
    """
    Recompute the counters on a buyer's profile.

    `total_spent` counts COMPLETED bookings only. Counting accepted-but-not-yet
    -delivered work as money spent would overstate every buyer's history and
    then have to be walked back on every cancellation.
    """
    from django.db.models import Count, Q, Sum

    from apps.bookings.constants import BookingStatus
    from apps.bookings.models import Booking

    profile = BuyerProfile.objects.filter(user=user).first()
    if profile is None:
        return None

    agg = Booking.objects.filter(buyer=user).aggregate(
        total=Count("id"),
        completed=Count("id", filter=Q(status=BookingStatus.COMPLETED)),
        cancelled=Count("id", filter=Q(status=BookingStatus.CANCELLED)),
        spent=Sum("total_price", filter=Q(status=BookingStatus.COMPLETED)),
    )

    profile.total_bookings = agg["total"] or 0
    profile.completed_bookings = agg["completed"] or 0
    profile.cancelled_bookings = agg["cancelled"] or 0
    profile.total_spent = agg["spent"] or Decimal("0.00")
    profile.save(
        update_fields=[
            "total_bookings", "completed_bookings", "cancelled_bookings",
            "total_spent", "updated_at",
        ]
    )
    return profile


def refresh_photographer_booking_metrics(profile: PhotographerProfile):
    from django.db.models import Avg, Count, ExpressionWrapper, F, Q, fields

    from apps.bookings.constants import BookingStatus
    from apps.bookings.models import Booking

    agg = Booking.objects.filter(photographer=profile).aggregate(
        total=Count("id"),
        completed=Count("id", filter=Q(status=BookingStatus.COMPLETED)),
        cancelled=Count("id", filter=Q(status=BookingStatus.CANCELLED)),
        rejected=Count("id", filter=Q(status=BookingStatus.REJECTED)),
    )
    completed = agg["completed"] or 0
    finished = completed + (agg["cancelled"] or 0) + (agg["rejected"] or 0)

    profile.total_bookings = agg["total"] or 0
    profile.completed_bookings = completed
    profile.cancelled_bookings = agg["cancelled"] or 0
    profile.success_rate = (
        Decimal(f"{completed / finished:.3f}") if finished else Decimal("0.000")
    )

    responded = Booking.objects.filter(photographer=profile, responded_at__isnull=False)
    if responded.exists():
        delta = ExpressionWrapper(
            F("responded_at") - F("created_at"), output_field=fields.DurationField()
        )
        avg_delta = responded.annotate(d=delta).aggregate(avg=Avg("d"))["avg"]
        if avg_delta:
            hours = avg_delta.total_seconds() / 3600
            # Clamp BOTH ends. The column is DECIMAL(6,2), so anything outside
            # 0..9999.99 raises a DataError that aborts the whole transaction.
            # A negative duration means responded_at precedes created_at —
            # impossible in normal operation, but reachable via bulk-imported
            # or back-dated rows, and it must not be allowed to crash a
            # routine metrics refresh.
            hours = max(0.0, min(hours, 999.0))
            profile.avg_response_time_hours = Decimal(f"{hours:.2f}")

    profile.save(
        update_fields=[
            "total_bookings", "completed_bookings", "cancelled_bookings",
            "success_rate", "avg_response_time_hours", "updated_at",
        ]
    )
    return profile
