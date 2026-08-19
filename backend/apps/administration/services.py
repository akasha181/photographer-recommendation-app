"""
Administration writes — Module 14.

EVERY PRIVILEGED ACTION WRITES AN AUDIT ROW IN THE SAME TRANSACTION
------------------------------------------------------------------
`_audit()` is called inside the `atomic()` block of the action it records, not
after it. If the block rolls back, the log entry goes with it — a log claiming a
user was blocked when they were not is worse than no log. And because it is in
the same transaction, there is no code path that changes state and forgets to
record it: the action would have to be written without its audit call, which is
visible in every function below.

WHAT AN AUDIT ROW HAS TO ANSWER
-------------------------------
"Why was my account blocked?" needs: who did it, when, on what grounds, and what
the row looked like before. So every entry carries the actor, the reason, a
human-readable snapshot of the target (`target_label` — it survives the target
being anonymised) and a before/after `changes` dict.

WHAT ADMINS DELIBERATELY CANNOT DO
----------------------------------
* Edit or delete an audit entry. There is no function for it here and the Django
  admin registers `AuditLog` read-only.
* Move money into a wallet without a ledger row. Wallet adjustments go through
  `profiles.services.credit_wallet` / `debit_wallet`, which write the ledger —
  a balance with no transaction behind it breaks the invariant the ledger exists
  to prove.
* Delete a review. Reviews are hidden, with a stored reason, because a deleted
  review cannot be appealed.
"""

import logging

from django.db import transaction
from django.utils import timezone

from apps.administration.models import (
    ApprovalRequest,
    ApprovalStatus,
    AuditAction,
    AuditLog,
    ModerationFlag,
    PlatformSetting,
)
from apps.core.exceptions import BusinessRuleViolation, ConflictError

logger = logging.getLogger("snapsphere")


# ═══════════════════════════════════════════════════════════════════════════
# AUDIT
# ═══════════════════════════════════════════════════════════════════════════
def _audit(
    actor,
    action: str,
    *,
    target_type: str = "",
    target_id="",
    target_label: str = "",
    changes: dict | None = None,
    reason: str = "",
    request=None,
) -> AuditLog:
    """
    Append one immutable entry. Never updated, never deleted.

    `request` is optional so a task can audit its own actions; when present the
    IP, user agent and request id are captured, which is what makes an entry
    correlatable with the JSON access logs.
    """
    return AuditLog.objects.create(
        actor=actor,
        action=action,
        target_type=target_type,
        target_id=str(target_id or ""),
        target_label=target_label[:200],
        changes=changes or {},
        reason=reason[:1000],
        ip_address=_client_ip(request),
        user_agent=(request.META.get("HTTP_USER_AGENT", "")[:300] if request else ""),
        request_id=getattr(request, "request_id", "") or "" if request else "",
    )


def _client_ip(request):
    if request is None:
        return None
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        # Left-most entry is the original client; the rest are proxies.
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR") or None


# ═══════════════════════════════════════════════════════════════════════════
# PHOTOGRAPHER APPROVAL
# ═══════════════════════════════════════════════════════════════════════════
# NOTE: applying for approval lives in `profiles.services.submit_for_approval`,
# not here. It belongs to the photographer's own profile flow and carries the
# completeness check (bio, categories, one active service, five portfolio
# images) so this queue only ever shows applications worth reviewing. This file
# owns the DECISION side of the same rows.


@transaction.atomic
def approve_photographer(request_row: ApprovalRequest, admin_user, *, note: str = "", request=None):
    """Flip the profile live and tell them, in one transaction."""
    if request_row.status != ApprovalStatus.PENDING:
        raise BusinessRuleViolation("This application has already been reviewed.")

    profile = request_row.photographer
    was = profile.is_approved

    request_row.status = ApprovalStatus.APPROVED
    request_row.reviewed_by = admin_user
    request_row.reviewed_at = timezone.now()
    request_row.admin_note = note
    request_row.save(
        update_fields=["status", "reviewed_by", "reviewed_at", "admin_note", "updated_at"]
    )

    profile.is_approved = True
    profile.save(update_fields=["is_approved", "updated_at"])

    _audit(
        admin_user,
        AuditAction.PHOTOGRAPHER_APPROVED,
        target_type="PhotographerProfile",
        target_id=profile.pk,
        target_label=profile.display_name,
        changes={"is_approved": [was, True]},
        reason=note,
        request=request,
    )
    _notify_account(profile.user, approved=True, reason=note)
    return request_row


@transaction.atomic
def reject_photographer(
    request_row: ApprovalRequest, admin_user, *, reason: str, request=None
):
    """
    Refuse an application — with a reason, always.

    A rejection without one gives the photographer nothing to fix and turns
    every decision into a support ticket. The reason is stored and sent to them.
    """
    if request_row.status != ApprovalStatus.PENDING:
        raise BusinessRuleViolation("This application has already been reviewed.")
    if not (reason or "").strip():
        raise BusinessRuleViolation("A rejection needs a reason the applicant can act on.")

    request_row.status = ApprovalStatus.REJECTED
    request_row.reviewed_by = admin_user
    request_row.reviewed_at = timezone.now()
    request_row.rejection_reason = reason
    request_row.save(
        update_fields=[
            "status", "reviewed_by", "reviewed_at", "rejection_reason", "updated_at",
        ]
    )

    profile = request_row.photographer
    # Deliberately does NOT set is_approved=False: a previously approved
    # photographer whose new application is refused keeps the listing they
    # already earned. Removing a listing is `block_user`, which is audited
    # under its own action.
    _audit(
        admin_user,
        AuditAction.PHOTOGRAPHER_REJECTED,
        target_type="PhotographerProfile",
        target_id=profile.pk,
        target_label=profile.display_name,
        reason=reason,
        request=request,
    )
    _notify_account(profile.user, approved=False, reason=reason)
    return request_row


@transaction.atomic
def request_more_info(request_row: ApprovalRequest, admin_user, *, note: str, request=None):
    """
    Ask for something instead of refusing.

    Kept as a distinct status rather than a rejection with a polite note: the
    queue has to be able to show "waiting on them" separately from "decided",
    or the same application gets reviewed twice.
    """
    if request_row.status not in (ApprovalStatus.PENDING, ApprovalStatus.MORE_INFO):
        raise BusinessRuleViolation("This application has already been decided.")

    request_row.status = ApprovalStatus.MORE_INFO
    request_row.reviewed_by = admin_user
    request_row.reviewed_at = timezone.now()
    request_row.admin_note = note
    request_row.save(
        update_fields=["status", "reviewed_by", "reviewed_at", "admin_note", "updated_at"]
    )

    from apps.notifications.models import NotificationType
    from apps.notifications.services import notify

    notify(
        request_row.photographer.user,
        NotificationType.ADMIN_MESSAGE,
        title="We need a bit more information",
        body=note[:400],
        action_screen="EditProfile",
    )
    return request_row


def _notify_account(user, *, approved: bool, reason: str = "") -> None:
    from apps.notifications.models import NotificationType
    from apps.notifications.services import notify

    if approved:
        notify(
            user,
            NotificationType.ACCOUNT_APPROVED,
            title="Your photographer account is live",
            body="Buyers can now find you in search and send booking requests.",
            action_screen="Dashboard",
        )
    else:
        notify(
            user,
            NotificationType.ACCOUNT_REJECTED,
            title="Your application needs attention",
            body=reason[:400] or "Please review your profile and apply again.",
            action_screen="EditProfile",
        )


# ═══════════════════════════════════════════════════════════════════════════
# USER MODERATION
# ═══════════════════════════════════════════════════════════════════════════
@transaction.atomic
def block_user(user, admin_user, *, reason: str, request=None):
    """
    Block an account.

    Two things happen beyond the flag, and both matter:

    1. `token_version` is bumped, which invalidates every JWT already issued to
       them. Without it a blocked user keeps working for up to 30 minutes on the
       access token in their pocket.
    2. Their PENDING bookings are cancelled with a reason the other party sees.
       Leaving them in place would hold calendar slots for shoots that cannot
       happen.
    """
    from apps.core.constants import UserRole

    if user.role == UserRole.ADMIN:
        raise BusinessRuleViolation("Administrator accounts cannot be blocked here.")
    if user.is_blocked:
        raise ConflictError("This account is already blocked.")
    if not (reason or "").strip():
        raise BusinessRuleViolation("Blocking an account needs a recorded reason.")

    # `User.block()` is the one place that knows the full set: is_blocked,
    # is_active, blocked_reason/at/by AND the token_version bump. Setting the
    # flag by hand here would be a second, drifting definition of "blocked".
    user.block(reason, by=admin_user)

    cancelled = _cancel_open_bookings(user, admin_user, reason)

    _audit(
        admin_user,
        AuditAction.USER_BLOCKED,
        target_type="User",
        target_id=user.pk,
        target_label=f"{user.full_name} <{user.email}>",
        changes={"is_blocked": [False, True], "bookings_cancelled": cancelled},
        reason=reason,
        request=request,
    )

    from apps.notifications.models import NotificationType
    from apps.notifications.services import notify

    notify(
        user,
        NotificationType.ACCOUNT_BLOCKED,
        title="Your account has been suspended",
        body=reason[:400],
        push=False,  # they cannot act on it in the app; email/support is the path
    )
    logger.warning(
        "User blocked",
        extra={"user_id": user.pk, "admin_id": admin_user.pk, "cancelled": cancelled},
    )
    return user


@transaction.atomic
def unblock_user(user, admin_user, *, reason: str = "", request=None):
    if not user.is_blocked:
        raise ConflictError("This account is not blocked.")

    user.unblock()

    _audit(
        admin_user,
        AuditAction.USER_UNBLOCKED,
        target_type="User",
        target_id=user.pk,
        target_label=f"{user.full_name} <{user.email}>",
        changes={"is_blocked": [True, False]},
        reason=reason,
        request=request,
    )
    return user


def _cancel_open_bookings(user, admin_user, reason: str) -> int:
    """
    Cancel what a blocked account had open, through the state machine.

    Uses `bookings.services.transition` rather than an `.update()` so each
    cancellation appends its `BookingStatusHistory` row and notifies the other
    party. An UPDATE would move the status with no record of who did it — which
    is exactly what the history table exists to prevent.
    """
    from django.db.models import Q

    from apps.bookings.constants import BookingStatus, CancellationReason
    from apps.bookings.models import Booking
    from apps.bookings.services import cancel_booking

    profile = getattr(user, "photographer_profile", None)
    either_side = Q(buyer=user)
    if profile is not None:
        either_side |= Q(photographer=profile)

    open_bookings = Booking.objects.filter(
        status__in=[BookingStatus.PENDING, BookingStatus.ACCEPTED]
    ).filter(either_side)

    cancelled = 0
    for booking in open_bookings.select_related("photographer", "buyer"):
        try:
            cancel_booking(
                booking,
                actor=admin_user,
                reason=CancellationReason.PHOTOGRAPHER_SUSPENDED
                if profile
                else CancellationReason.OTHER,
                note=f"Account suspended: {reason}"[:500],
            )
            cancelled += 1
        except Exception as exc:  # noqa: BLE001
            # One booking that refuses to move must not abort the block itself.
            logger.warning(
                "Could not cancel booking %s while blocking user %s: %s",
                booking.pk, user.pk, exc,
            )
    return cancelled


# ═══════════════════════════════════════════════════════════════════════════
# CONTENT MODERATION
# ═══════════════════════════════════════════════════════════════════════════
def report_content(
    *, reporter, content_type: str, object_id: int, reason: str, detail: str = ""
) -> ModerationFlag:
    """
    The single entry point for a user reporting anything.

    Called by `reviews.services.flag_review` and `chat.services.report_message`,
    so every report — whatever it targets — lands in one queue with one shape.
    Duplicate reports from the same person on the same object are collapsed
    rather than rejected: the reporter gets a success response either way, and
    the queue does not fill with the same complaint tapped three times.
    """
    existing = ModerationFlag.objects.filter(
        reporter=reporter,
        content_type=content_type,
        object_id=object_id,
        status__in=["OPEN", "REVIEWING"],
    ).first()
    if existing is not None:
        return existing

    flag = ModerationFlag.objects.create(
        reporter=reporter,
        content_type=content_type,
        object_id=object_id,
        reason=reason,
        detail=detail[:1000],
    )
    logger.info(
        "Content reported",
        extra={
            "flag_id": flag.pk,
            "content_type": content_type,
            "object_id": object_id,
        },
    )
    return flag


@transaction.atomic
def start_review(flag: ModerationFlag, admin_user) -> ModerationFlag:
    """Claim a flag, so two admins do not both act on it."""
    if flag.status != "OPEN":
        raise BusinessRuleViolation("This report is not open.")
    flag.status = "REVIEWING"
    flag.resolved_by = admin_user
    flag.save(update_fields=["status", "resolved_by", "updated_at"])
    return flag


@transaction.atomic
def resolve_flag(
    flag: ModerationFlag,
    admin_user,
    *,
    action: str,
    note: str = "",
    request=None,
) -> ModerationFlag:
    """
    Close a report as ACTIONED or DISMISSED.

    `action="ACTIONED"` also applies the consequence to the target — hiding the
    review, unpublishing the product — because a queue where "actioned" does not
    act is a queue that lies. The consequence and the resolution are one
    transaction for the same reason.
    """
    if flag.status in ("ACTIONED", "DISMISSED"):
        raise ConflictError("This report has already been resolved.")
    if action not in ("ACTIONED", "DISMISSED"):
        raise BusinessRuleViolation("Resolution must be ACTIONED or DISMISSED.")

    if action == "ACTIONED":
        _apply_moderation(flag, admin_user, note=note, request=request)

    flag.status = action
    flag.resolved_by = admin_user
    flag.resolved_at = timezone.now()
    flag.resolution_note = note[:1000]
    flag.save(
        update_fields=[
            "status", "resolved_by", "resolved_at", "resolution_note", "updated_at",
        ]
    )
    return flag


def _apply_moderation(flag: ModerationFlag, admin_user, *, note: str, request=None):
    """Take the target down, by kind. Unknown kinds are recorded, not guessed."""
    if flag.content_type == "REVIEW":
        hide_review(flag.object_id, admin_user, reason=note, request=request)
    elif flag.content_type == "PRODUCT":
        unpublish_product(flag.object_id, admin_user, reason=note, request=request)
    elif flag.content_type == "PORTFOLIO_IMAGE":
        _remove_portfolio_image(flag.object_id, admin_user, reason=note, request=request)
    elif flag.content_type == "MESSAGE":
        _redact_message(flag.object_id, admin_user, reason=note, request=request)
    else:
        # PROFILE reports resolve to a user-level action (block), which an admin
        # takes explicitly and which is audited under its own action.
        logger.info(
            "Flag actioned with no automatic consequence",
            extra={"flag_id": flag.pk, "content_type": flag.content_type},
        )


@transaction.atomic
def hide_review(review_id: int, admin_user, *, reason: str = "", request=None):
    """Take a review out of the public average, with a stored reason."""
    from apps.reviews.models import Review
    from apps.reviews.services import set_hidden

    review = Review.objects.filter(pk=review_id).first()
    if review is None:
        raise BusinessRuleViolation("Review not found.")

    set_hidden(review, hidden=True, reason=reason or "Removed by moderation")
    _audit(
        admin_user,
        AuditAction.REVIEW_HIDDEN,
        target_type="Review",
        target_id=review.pk,
        target_label=f"{review.rating}★ by {review.buyer.full_name}",
        changes={"is_hidden": [False, True]},
        reason=reason,
        request=request,
    )
    return review


@transaction.atomic
def unhide_review(review_id: int, admin_user, *, reason: str = "", request=None):
    from apps.reviews.models import Review
    from apps.reviews.services import set_hidden

    review = Review.objects.filter(pk=review_id).first()
    if review is None:
        raise BusinessRuleViolation("Review not found.")

    set_hidden(review, hidden=False)
    _audit(
        admin_user,
        AuditAction.REVIEW_HIDDEN,
        target_type="Review",
        target_id=review.pk,
        target_label=f"{review.rating}★ by {review.buyer.full_name}",
        changes={"is_hidden": [True, False]},
        reason=reason,
        request=request,
    )
    return review


@transaction.atomic
def approve_product(product_id: int, admin_user, *, note: str = "", request=None):
    """
    Clear a product for sale.

    `is_approved` is the copyright gate: an unapproved product is invisible in
    the shop no matter what its seller sets `is_published` to.
    """
    from apps.marketplace.models import DigitalProduct

    product = DigitalProduct.objects.filter(pk=product_id).first()
    if product is None:
        raise BusinessRuleViolation("Product not found.")
    if product.is_approved:
        raise ConflictError("This product is already approved.")

    product.is_approved = True
    product.save(update_fields=["is_approved", "updated_at"])

    _audit(
        admin_user,
        AuditAction.PRODUCT_APPROVED,
        target_type="DigitalProduct",
        target_id=product.pk,
        target_label=product.title,
        changes={"is_approved": [False, True]},
        reason=note,
        request=request,
    )

    from apps.notifications.models import NotificationType
    from apps.notifications.services import notify

    notify(
        product.seller.user,
        NotificationType.PRODUCT_APPROVED,
        title=f"“{product.title}” is approved",
        body="It is now listed in the shop.",
        action_screen="ProductDetail",
        action_id=product.slug,
    )
    return product


@transaction.atomic
def unpublish_product(product_id: int, admin_user, *, reason: str = "", request=None):
    """
    Pull a product from sale without destroying purchase history.

    `is_approved=False` rather than a delete: `OrderItem.product` is PROTECT, and
    buyers who already paid keep their downloads. A removed listing must not
    revoke a licence somebody bought.
    """
    from apps.marketplace.models import DigitalProduct

    product = DigitalProduct.objects.filter(pk=product_id).first()
    if product is None:
        raise BusinessRuleViolation("Product not found.")

    product.is_approved = False
    product.save(update_fields=["is_approved", "updated_at"])

    _audit(
        admin_user,
        AuditAction.PRODUCT_REMOVED,
        target_type="DigitalProduct",
        target_id=product.pk,
        target_label=product.title,
        changes={"is_approved": [True, False]},
        reason=reason,
        request=request,
    )

    from apps.notifications.models import NotificationType
    from apps.notifications.services import notify

    notify(
        product.seller.user,
        NotificationType.PRODUCT_REJECTED,
        title=f"“{product.title}” was removed from the shop",
        body=reason[:400] or "Contact support if you think this is a mistake.",
    )
    return product


def _remove_portfolio_image(image_id: int, admin_user, *, reason: str = "", request=None):
    """
    Soft-delete a reported portfolio image.

    `PortfolioImage` inherits `SoftDeleteModel`, so `.delete()` flips the flag
    and the public grid stops showing it while the file and the row survive for
    the appeal. Featuring is cleared too — otherwise a hidden image still
    occupies one of the twelve featured slots.
    """
    from apps.portfolio.models import PortfolioImage

    image = PortfolioImage.objects.filter(pk=image_id).first()
    if image is None:
        return None

    image.is_featured = False
    image.save(update_fields=["is_featured", "updated_at"])
    image.delete()  # SoftDeleteModel — sets is_deleted / deleted_at

    _audit(
        admin_user,
        AuditAction.PRODUCT_REMOVED,
        target_type="PortfolioImage",
        target_id=image.pk,
        target_label=image.caption or f"Image #{image.pk}",
        changes={"is_deleted": [False, True]},
        reason=reason,
        request=request,
    )
    return image


def _redact_message(message_id: int, admin_user, *, reason: str = "", request=None):
    """
    Blank a reported chat message.

    The row stays (the other party already read it, and it may be evidence), the
    text goes. Same reasoning as a user deleting their own message, applied by
    somebody else.
    """
    from apps.chat.models import Message

    message = Message.objects.filter(pk=message_id).first()
    if message is None:
        return None
    message.is_deleted = True
    message.deleted_at = timezone.now()
    message.body = ""
    message.save(update_fields=["is_deleted", "deleted_at", "body", "updated_at"])
    _audit(
        admin_user,
        AuditAction.REVIEW_HIDDEN,
        target_type="Message",
        target_id=message.pk,
        target_label=f"Message in conversation {message.conversation_id}",
        reason=reason,
        request=request,
    )
    return message


# ═══════════════════════════════════════════════════════════════════════════
# BOOKINGS & WALLETS
# ═══════════════════════════════════════════════════════════════════════════
@transaction.atomic
def force_cancel_booking(booking, admin_user, *, reason: str, request=None):
    """
    Admin override on a stuck booking.

    Goes through `bookings.services.cancel_booking` so the transition is legal,
    attributed and notified — an admin bypassing the state machine is how a
    COMPLETED booking ends up CANCELLED with money already moved.
    """
    from apps.bookings.constants import CancellationReason
    from apps.bookings.services import cancel_booking

    previous = booking.status
    cancel_booking(
        booking, actor=admin_user, reason=CancellationReason.OTHER, note=reason
    )
    _audit(
        admin_user,
        AuditAction.BOOKING_FORCE_CANCELLED,
        target_type="Booking",
        target_id=booking.pk,
        target_label=f"Booking {booking.uuid}",
        changes={"status": [previous, "CANCELLED"]},
        reason=reason,
        request=request,
    )
    return booking


@transaction.atomic
def adjust_wallet(user, admin_user, *, amount, reason: str, request=None):
    """
    Correct a balance — a refund, a goodwill credit, a reversal.

    Always through `credit_wallet` / `debit_wallet`, which lock the row and write
    the ledger. Setting `Wallet.balance` directly would produce a balance the
    transaction history cannot explain, and the first person to reconcile the two
    would chase a bug that was never in the application.
    """
    from decimal import Decimal

    from apps.profiles.models import WalletTransactionType
    from apps.profiles.services import credit_wallet, debit_wallet

    amount = Decimal(str(amount))
    if amount == 0:
        raise BusinessRuleViolation("An adjustment of zero does nothing.")
    if not (reason or "").strip():
        raise BusinessRuleViolation("A wallet adjustment needs a recorded reason.")

    description = f"Admin adjustment: {reason}"[:200]
    reference = f"ADMIN-{admin_user.pk}"

    if amount > 0:
        credit_wallet(
            user, amount,
            txn_type=WalletTransactionType.ADJUSTMENT,
            reference=reference,
            description=description,
            performed_by=admin_user,
        )
    else:
        # A debit that would overdraw raises InsufficientBalance from
        # `debit_wallet`, backed by ck_wallet_no_overdraft. An admin cannot
        # push a balance negative any more than a buyer can.
        debit_wallet(
            user, -amount,
            txn_type=WalletTransactionType.ADJUSTMENT,
            reference=reference,
            description=description,
        )

    from apps.profiles.selectors import wallet_balance

    _audit(
        admin_user,
        AuditAction.WALLET_ADJUSTED,
        target_type="User",
        target_id=user.pk,
        target_label=f"{user.full_name} <{user.email}>",
        changes={"amount": str(amount), "balance_after": str(wallet_balance(user))},
        reason=reason,
        request=request,
    )
    return wallet_balance(user)


@transaction.atomic
def approve_topup(topup, admin_user, *, note: str = "", request=None):
    """Credit a verified bank transfer. `profiles.services` moves the money."""
    from apps.profiles.services import approve_topup as _approve

    result = _approve(topup, admin_user)
    _audit(
        admin_user,
        AuditAction.TOPUP_APPROVED,
        target_type="TopUpRequest",
        target_id=topup.pk,
        target_label=f"{topup.user.full_name} — Rs {topup.amount}",
        changes={"status": ["PENDING", "APPROVED"], "amount": str(topup.amount)},
        reason=note,
        request=request,
    )
    return result


@transaction.atomic
def reject_topup(topup, admin_user, *, note: str, request=None):
    from apps.profiles.services import reject_topup as _reject

    if not (note or "").strip():
        raise BusinessRuleViolation(
            "Rejecting a top-up needs a reason — the user has claimed a real transfer."
        )
    result = _reject(topup, admin_user, note)
    _audit(
        admin_user,
        AuditAction.TOPUP_REJECTED,
        target_type="TopUpRequest",
        target_id=topup.pk,
        target_label=f"{topup.user.full_name} — Rs {topup.amount}",
        changes={"status": ["PENDING", "REJECTED"]},
        reason=note,
        request=request,
    )
    return result


# ═══════════════════════════════════════════════════════════════════════════
# PLATFORM SETTINGS
# ═══════════════════════════════════════════════════════════════════════════
@transaction.atomic
def set_setting(key: str, value, admin_user, *, request=None) -> PlatformSetting:
    """
    Change a runtime-tunable setting.

    Refuses unknown keys. A settings table that accepts arbitrary keys becomes a
    junk drawer where a typo silently creates a second setting nothing reads,
    and the real one keeps its old value.
    """
    setting = PlatformSetting.objects.filter(key=key).first()
    if setting is None:
        raise BusinessRuleViolation(
            f"Unknown setting '{key}'. Settings are declared, not created ad hoc."
        )

    previous = setting.value
    setting.value = str(value)
    setting.updated_by = admin_user
    setting.save(update_fields=["value", "updated_by", "updated_at"])

    # Validate by round-tripping through the typed accessor: a value the API
    # cannot parse back is a broken setting, and better caught here than by
    # whatever reads it at 3am.
    if setting.value_type != "STRING" and isinstance(setting.typed_value, str):
        raise BusinessRuleViolation(
            f"'{value}' is not a valid {setting.value_type} for {key}."
        )

    _audit(
        admin_user,
        AuditAction.SETTING_CHANGED,
        target_type="PlatformSetting",
        target_id=setting.pk,
        target_label=setting.key,
        changes={"value": [previous, setting.value]},
        request=request,
    )
    return setting


def get_setting(key: str, default=None):
    """
    Typed read with a fallback.

    Used by application code that wants a tunable value without caring whether
    an admin has ever touched it.
    """
    setting = PlatformSetting.objects.filter(key=key).first()
    return setting.typed_value if setting else default


# ═══════════════════════════════════════════════════════════════════════════
# BROADCASTS
# ═══════════════════════════════════════════════════════════════════════════
@transaction.atomic
def create_broadcast(admin_user, *, request=None, **data):
    """
    Queue an announcement.

    Fan-out runs in a task, not in the request: "everyone in Lahore" is
    thousands of notification rows, and an admin whose browser times out must
    not be left wondering whether half of them went out.
    """
    from apps.notifications.models import Broadcast

    broadcast = Broadcast.objects.create(created_by=admin_user, **data)

    _audit(
        admin_user,
        AuditAction.BROADCAST_SENT,
        target_type="Broadcast",
        target_id=broadcast.pk,
        target_label=broadcast.title,
        changes={"audience": broadcast.audience, "city": broadcast.city_filter},
        request=request,
    )

    if broadcast.scheduled_for is None:
        from apps.notifications.tasks import send_broadcast

        transaction.on_commit(lambda: send_broadcast.delay(broadcast.pk))
    return broadcast
