"""
Administration reads — Module 14.

WHAT THE DASHBOARD IS FOR
-------------------------
An admin opening this app has exactly two questions: "is anything waiting for
me?" and "is the platform healthy?". `dashboard()` answers the first with queue
depths (indexed COUNTs, always live) and the second from the analytics rollups
that Module 15 already writes nightly. It does not recompute platform revenue
from 52,000 bookings on page load — that table exists precisely so it doesn't
have to.

WHY THE QUEUE COUNTS ARE LIVE AND THE CHARTS ARE NOT
---------------------------------------------------
Same split as the photographer dashboard, for the same reason: a queue depth
that is an hour stale is useless (the admin acts on it now), while a 30-day
revenue series recomputed per request is slow and no more correct.
"""

from django.db.models import Count, Q, Sum

from apps.administration.models import (
    ApprovalRequest,
    ApprovalStatus,
    AuditLog,
    ModerationFlag,
    PlatformSetting,
)


# ═══════════════════════════════════════════════════════════════════════════
# QUEUES
# ═══════════════════════════════════════════════════════════════════════════
def approval_queue(*, status: str | None = None):
    qs = ApprovalRequest.objects.select_related(
        "photographer", "photographer__user", "reviewed_by"
    )
    if status:
        qs = qs.filter(status=status.upper())
    # Oldest first: a review queue sorted newest-first starves the person who
    # has been waiting longest, which is the opposite of what a queue is for.
    return qs.order_by("status", "created_at")


def get_approval_request(pk) -> ApprovalRequest | None:
    return (
        ApprovalRequest.objects.select_related("photographer", "photographer__user")
        .filter(pk=pk)
        .first()
    )


def moderation_queue(*, status: str | None = None, content_type: str | None = None):
    qs = ModerationFlag.objects.select_related("reporter", "resolved_by")
    if status:
        qs = qs.filter(status=status.upper())
    if content_type:
        qs = qs.filter(content_type=content_type.upper())
    return qs.order_by("created_at")


def get_flag(pk) -> ModerationFlag | None:
    return ModerationFlag.objects.select_related("reporter").filter(pk=pk).first()


def topup_queue(*, status: str = "PENDING"):
    from apps.profiles.models import TopUpRequest

    qs = TopUpRequest.objects.select_related("user", "reviewed_by")
    if status:
        qs = qs.filter(status=status.upper())
    return qs.order_by("created_at")


def get_topup(pk):
    from apps.profiles.models import TopUpRequest

    return TopUpRequest.objects.select_related("user").filter(pk=pk).first()


def product_queue(*, approved: bool = False):
    """
    Products awaiting the copyright gate.

    `is_published=True, is_approved=False` is the real queue: a seller who has
    not published yet has not asked for review.
    """
    from apps.marketplace.models import DigitalProduct

    return (
        DigitalProduct.objects.filter(is_published=True, is_approved=approved)
        .select_related("seller", "seller__user")
        .order_by("created_at")
    )


# ═══════════════════════════════════════════════════════════════════════════
# USERS
# ═══════════════════════════════════════════════════════════════════════════
def users(*, role: str | None = None, blocked: bool | None = None, term: str = ""):
    """
    The admin user table.

    Search covers email and name only. Deliberately not phone: an admin typing a
    partial number would pull up strangers, and the support flow that needs a
    phone lookup should be an exact match, not a prefix scan.
    """
    from django.contrib.auth import get_user_model

    User = get_user_model()
    qs = User.objects.select_related("photographer_profile", "buyer_profile")

    if role:
        qs = qs.filter(role=role.upper())
    if blocked is not None:
        qs = qs.filter(is_blocked=blocked)
    if term:
        qs = qs.filter(Q(email__icontains=term) | Q(full_name__icontains=term))
    # `created_at` from TimeStampedModel — this User does not inherit Django's
    # `AbstractUser`, so there is no `date_joined`.
    return qs.order_by("-created_at")


def get_user(pk):
    from django.contrib.auth import get_user_model

    User = get_user_model()
    return (
        User.objects.select_related("photographer_profile", "buyer_profile", "wallet")
        .filter(pk=pk)
        .first()
    )


def user_detail(user) -> dict:
    """
    One user, with the numbers a support conversation actually needs.

    Assembled here rather than in a serializer because it spans four apps, and a
    serializer reaching into four `models.py` files is the layering violation
    this project's structure exists to prevent.
    """
    from apps.bookings.constants import BookingStatus
    from apps.bookings.models import Booking
    from apps.marketplace.models import Order, OrderStatus
    from apps.profiles.selectors import wallet_balance
    from apps.reviews.models import Review

    bookings = Booking.objects.filter(buyer=user).aggregate(
        total=Count("id"),
        completed=Count("id", filter=Q(status=BookingStatus.COMPLETED)),
        cancelled=Count("id", filter=Q(status=BookingStatus.CANCELLED)),
        spent=Sum("total_price", filter=Q(status=BookingStatus.COMPLETED)),
    )
    profile = getattr(user, "photographer_profile", None)
    received = (
        Booking.objects.filter(photographer=profile).aggregate(
            total=Count("id"),
            completed=Count("id", filter=Q(status=BookingStatus.COMPLETED)),
        )
        if profile
        else {"total": 0, "completed": 0}
    )

    return {
        "bookings_made": bookings["total"] or 0,
        "bookings_completed": bookings["completed"] or 0,
        "bookings_cancelled": bookings["cancelled"] or 0,
        "total_spent": str(bookings["spent"] or 0),
        "bookings_received": received["total"] or 0,
        "shoots_delivered": received["completed"] or 0,
        "orders": Order.objects.filter(
            buyer=user, status=OrderStatus.PAID
        ).count(),
        "reviews_written": Review.objects.filter(buyer=user, is_deleted=False).count(),
        "wallet_balance": str(wallet_balance(user)),
    }


# ═══════════════════════════════════════════════════════════════════════════
# DASHBOARD
# ═══════════════════════════════════════════════════════════════════════════
def queue_counts() -> dict:
    """Everything waiting for an admin, in four indexed COUNTs."""
    from apps.marketplace.models import DigitalProduct
    from apps.profiles.models import TopUpRequest, TopUpStatus

    return {
        "pending_approvals": ApprovalRequest.objects.filter(
            status=ApprovalStatus.PENDING
        ).count(),
        "open_flags": ModerationFlag.objects.filter(
            status__in=["OPEN", "REVIEWING"]
        ).count(),
        "pending_topups": TopUpRequest.objects.filter(
            status=TopUpStatus.PENDING
        ).count(),
        "products_awaiting_review": DigitalProduct.objects.filter(
            is_published=True, is_approved=False
        ).count(),
    }


def platform_totals() -> dict:
    """Headline counters. All indexed, all live."""
    from django.contrib.auth import get_user_model

    from apps.bookings.constants import BookingStatus
    from apps.bookings.models import Booking
    from apps.core.constants import UserRole
    from apps.marketplace.models import Order, OrderStatus

    User = get_user_model()

    people = User.objects.aggregate(
        total=Count("id"),
        buyers=Count("id", filter=Q(role=UserRole.BUYER)),
        photographers=Count("id", filter=Q(role=UserRole.PHOTOGRAPHER)),
        blocked=Count("id", filter=Q(is_blocked=True)),
    )
    bookings = Booking.objects.aggregate(
        total=Count("id"),
        pending=Count("id", filter=Q(status=BookingStatus.PENDING)),
        accepted=Count("id", filter=Q(status=BookingStatus.ACCEPTED)),
        completed=Count("id", filter=Q(status=BookingStatus.COMPLETED)),
        gmv=Sum("total_price", filter=Q(status=BookingStatus.COMPLETED)),
    )
    orders = Order.objects.filter(status=OrderStatus.PAID).aggregate(
        count=Count("id"), revenue=Sum("total")
    )

    return {
        "users": people["total"] or 0,
        "buyers": people["buyers"] or 0,
        "photographers": people["photographers"] or 0,
        "blocked_users": people["blocked"] or 0,
        "bookings_total": bookings["total"] or 0,
        "bookings_pending": bookings["pending"] or 0,
        "bookings_accepted": bookings["accepted"] or 0,
        "bookings_completed": bookings["completed"] or 0,
        # Gross merchandise value: completed shoots only. Counting accepted
        # work would report money that has not been earned yet.
        "booking_gmv": str(bookings["gmv"] or 0),
        "orders_paid": orders["count"] or 0,
        "shop_revenue": str(orders["revenue"] or 0),
    }


def dashboard(*, days: int = 30) -> dict:
    """
    The admin home screen.

    The trend series comes from `analytics.PlatformStat`, which the nightly
    rollup writes. Gap-filled on read for the same reason the photographer
    dashboard is: a day with no rows means "nothing happened", and omitting it
    draws the 3rd next to the 11th with no visible break.
    """
    from datetime import timedelta

    from django.utils import timezone

    from apps.analytics.models import PlatformStat

    days = max(1, min(int(days), 365))
    end = timezone.localdate()
    start = end - timedelta(days=days - 1)

    rows = {
        row.date: row
        for row in PlatformStat.objects.filter(date__gte=start, date__lte=end)
    }
    series = []
    for offset in range(days):
        day = start + timedelta(days=offset)
        row = rows.get(day)
        series.append(
            {
                "date": day,
                "new_users": row.new_users if row else 0,
                "bookings_created": row.bookings_created if row else 0,
                "bookings_completed": row.bookings_completed if row else 0,
                "gross_booking_value": str(row.gross_booking_value if row else 0),
                "platform_commission": str(row.platform_commission if row else 0),
                "reviews_posted": row.reviews_posted if row else 0,
            }
        )

    return {
        "queues": queue_counts(),
        "totals": platform_totals(),
        "trend": series,
        "window_days": days,
    }


# ═══════════════════════════════════════════════════════════════════════════
# AUDIT & SETTINGS
# ═══════════════════════════════════════════════════════════════════════════
def audit_log(*, action: str | None = None, actor_id=None, target_type: str = ""):
    """
    Read-only, newest first.

    There is no update or delete path anywhere in this app — an audit log an
    administrator can edit is not an audit log.
    """
    qs = AuditLog.objects.select_related("actor")
    if action:
        qs = qs.filter(action=action.upper())
    if actor_id:
        qs = qs.filter(actor_id=actor_id)
    if target_type:
        qs = qs.filter(target_type=target_type)
    return qs.order_by("-created_at")


def settings_list(*, group: str | None = None):
    qs = PlatformSetting.objects.select_related("updated_by")
    if group:
        qs = qs.filter(group=group)
    return qs.order_by("group", "key")


def public_settings() -> dict:
    """
    The subset the mobile app is allowed to read.

    `is_public` is opt-in per row, so adding a setting never accidentally
    exposes it — commission rates and model weights stay server-side unless
    somebody deliberately marks them otherwise.
    """
    return {
        setting.key: setting.typed_value
        for setting in PlatformSetting.objects.filter(is_public=True)
    }
