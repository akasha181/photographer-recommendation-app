"""
Administration serializers.

EVERY DESTRUCTIVE ACTION REQUIRES A TYPED REASON
-----------------------------------------------
`reason` is `required=True` on blocking, rejecting and force-cancelling — not
because a schema needs it, but because these are the actions a user will later
ask about. An audit row with an empty reason answers "who and when" and leaves
"why" to somebody's memory.
"""

from rest_framework import serializers

from apps.administration.models import (
    ApprovalRequest,
    AuditLog,
    ModerationFlag,
    PlatformSetting,
)


# ═══════════════════════════════════════════════════════════════════════════
# APPROVALS
# ═══════════════════════════════════════════════════════════════════════════
class ApprovalRequestSerializer(serializers.ModelSerializer):
    photographer_id = serializers.IntegerField(read_only=True)
    photographer_name = serializers.SerializerMethodField()
    photographer_email = serializers.SerializerMethodField()
    city = serializers.SerializerMethodField()
    reviewed_by_name = serializers.SerializerMethodField()

    class Meta:
        model = ApprovalRequest
        fields = (
            "id", "status", "photographer_id", "photographer_name",
            "photographer_email", "city", "submitted_data",
            "admin_note", "rejection_reason",
            "reviewed_by_name", "reviewed_at", "created_at",
        )

    def get_photographer_name(self, obj) -> str:
        return obj.photographer.display_name

    def get_photographer_email(self, obj) -> str:
        return obj.photographer.user.email

    def get_city(self, obj) -> str:
        return obj.photographer.user.city or ""

    def get_reviewed_by_name(self, obj) -> str | None:
        return obj.reviewed_by.full_name if obj.reviewed_by_id else None


class ApprovalDecisionSerializer(serializers.Serializer):
    note = serializers.CharField(max_length=1000, required=False, allow_blank=True)


class RejectionSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=1000)

    def validate_reason(self, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) < 10:
            raise serializers.ValidationError(
                "Give a reason the applicant can act on (at least 10 characters)."
            )
        return cleaned


# ═══════════════════════════════════════════════════════════════════════════
# MODERATION
# ═══════════════════════════════════════════════════════════════════════════
class ModerationFlagSerializer(serializers.ModelSerializer):
    reporter_name = serializers.SerializerMethodField()
    resolved_by_name = serializers.SerializerMethodField()
    target_preview = serializers.SerializerMethodField()

    class Meta:
        model = ModerationFlag
        fields = (
            "id", "content_type", "object_id", "reason", "detail", "status",
            "reporter_name", "resolved_by_name", "resolution_note",
            "resolved_at", "target_preview", "created_at",
        )

    def get_reporter_name(self, obj) -> str | None:
        return obj.reporter.full_name if obj.reporter_id else None

    def get_resolved_by_name(self, obj) -> str | None:
        return obj.resolved_by.full_name if obj.resolved_by_id else None

    def get_target_preview(self, obj) -> str:
        """
        A one-line look at what was reported.

        Without it the queue is a list of ids and an admin has to open four
        screens to judge one report. Fetched per row and deliberately so: the
        queue is a handful of rows an admin works through, not a hot list
        endpoint, and a generic reference cannot be prefetched.
        """
        try:
            if obj.content_type == "REVIEW":
                from apps.reviews.models import Review

                review = Review.all_objects.filter(pk=obj.object_id).first()
                return f"{review.rating}★ “{review.comment[:80]}”" if review else "—"
            if obj.content_type == "MESSAGE":
                from apps.chat.models import Message

                message = Message.objects.filter(pk=obj.object_id).first()
                return f"“{message.body[:80]}”" if message else "—"
            if obj.content_type == "PRODUCT":
                from apps.marketplace.models import DigitalProduct

                product = DigitalProduct.all_objects.filter(pk=obj.object_id).first()
                return product.title if product else "—"
            if obj.content_type == "PORTFOLIO_IMAGE":
                from apps.portfolio.models import PortfolioImage

                image = PortfolioImage.all_objects.filter(pk=obj.object_id).first()
                return (image.caption or f"Image #{image.pk}") if image else "—"
            if obj.content_type == "PROFILE":
                from apps.profiles.models import PhotographerProfile

                profile = PhotographerProfile.all_objects.filter(
                    pk=obj.object_id
                ).first()
                return profile.display_name if profile else "—"
        except Exception:  # noqa: BLE001
            # A queue that 500s because one target row vanished is worse than a
            # queue with one dash in it.
            return "—"
        return "—"


class FlagResolutionSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=["ACTIONED", "DISMISSED"])
    note = serializers.CharField(max_length=1000, required=False, allow_blank=True)

    def validate(self, attrs):
        if attrs["action"] == "ACTIONED" and not (attrs.get("note") or "").strip():
            raise serializers.ValidationError(
                {"note": "Say what was done — this note is shown in the audit log."}
            )
        return attrs


# ═══════════════════════════════════════════════════════════════════════════
# USERS
# ═══════════════════════════════════════════════════════════════════════════
class AdminUserSerializer(serializers.Serializer):
    """
    The admin user table row.

    A plain Serializer, not a ModelSerializer: `fields = "__all__"` on the user
    model would put the password hash and every security column on the wire.
    Listing what is exposed is the point.
    """

    id = serializers.IntegerField()
    email = serializers.EmailField()
    full_name = serializers.CharField()
    phone = serializers.CharField()
    role = serializers.CharField()
    city = serializers.CharField()
    is_active = serializers.BooleanField()
    is_blocked = serializers.BooleanField()
    blocked_reason = serializers.CharField()
    is_email_verified = serializers.BooleanField()
    # `created_at`, exposed as `joined_at`: this User inherits TimeStampedModel,
    # not Django's AbstractUser, so there is no `date_joined` column.
    joined_at = serializers.DateTimeField(source="created_at")
    last_login = serializers.DateTimeField()
    is_approved_photographer = serializers.SerializerMethodField()

    def get_is_approved_photographer(self, obj) -> bool | None:
        profile = getattr(obj, "photographer_profile", None)
        return profile.is_approved if profile else None


class AdminUserDetailSerializer(AdminUserSerializer):
    stats = serializers.SerializerMethodField()

    def get_stats(self, obj) -> dict:
        from apps.administration.selectors import user_detail

        return user_detail(obj)


class BlockUserSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=1000)

    def validate_reason(self, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) < 10:
            raise serializers.ValidationError(
                "Record a reason of at least 10 characters — the user will be told it."
            )
        return cleaned


class UnblockUserSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=1000, required=False, allow_blank=True)


class WalletAdjustmentSerializer(serializers.Serializer):
    amount = serializers.DecimalField(
        max_digits=12, decimal_places=2,
        help_text="Positive credits, negative debits.",
    )
    reason = serializers.CharField(max_length=500)

    def validate_amount(self, value):
        if value == 0:
            raise serializers.ValidationError("An adjustment of zero does nothing.")
        return value

    def validate_reason(self, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) < 5:
            raise serializers.ValidationError("Say why the balance is being changed.")
        return cleaned


# ═══════════════════════════════════════════════════════════════════════════
# TOP-UPS
# ═══════════════════════════════════════════════════════════════════════════
class AdminTopUpSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    user_id = serializers.IntegerField()
    user_name = serializers.SerializerMethodField()
    user_email = serializers.SerializerMethodField()
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    method = serializers.CharField()
    transaction_reference = serializers.CharField()
    receipt_url = serializers.SerializerMethodField()
    status = serializers.CharField()
    admin_note = serializers.CharField()
    reviewed_at = serializers.DateTimeField()
    created_at = serializers.DateTimeField()

    def get_user_name(self, obj) -> str:
        return obj.user.full_name

    def get_user_email(self, obj) -> str:
        return obj.user.email

    def get_receipt_url(self, obj) -> str | None:
        """The whole point of the manual gate is that a human sees the receipt."""
        if not obj.receipt_image:
            return None
        request = self.context.get("request")
        url = obj.receipt_image.url
        return request.build_absolute_uri(url) if request else url


class TopUpDecisionSerializer(serializers.Serializer):
    note = serializers.CharField(max_length=1000, required=False, allow_blank=True)


class TopUpRejectionSerializer(serializers.Serializer):
    note = serializers.CharField(max_length=1000)

    def validate_note(self, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) < 5:
            raise serializers.ValidationError(
                "The user claimed a real transfer — tell them why it was refused."
            )
        return cleaned


# ═══════════════════════════════════════════════════════════════════════════
# PRODUCTS
# ═══════════════════════════════════════════════════════════════════════════
class AdminProductSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    title = serializers.CharField()
    slug = serializers.CharField()
    product_type = serializers.CharField()
    price = serializers.DecimalField(max_digits=10, decimal_places=2)
    seller_name = serializers.SerializerMethodField()
    is_published = serializers.BooleanField()
    is_approved = serializers.BooleanField()
    file_count = serializers.IntegerField()
    created_at = serializers.DateTimeField()

    def get_seller_name(self, obj) -> str:
        return obj.seller.display_name


# ═══════════════════════════════════════════════════════════════════════════
# BOOKINGS
# ═══════════════════════════════════════════════════════════════════════════
class ForceCancelSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=1000)

    def validate_reason(self, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) < 10:
            raise serializers.ValidationError(
                "Both parties are told this reason — make it specific."
            )
        return cleaned


# ═══════════════════════════════════════════════════════════════════════════
# AUDIT & SETTINGS
# ═══════════════════════════════════════════════════════════════════════════
class AuditLogSerializer(serializers.ModelSerializer):
    actor_name = serializers.SerializerMethodField()

    class Meta:
        model = AuditLog
        fields = (
            "id", "action", "actor_name", "target_type", "target_id",
            "target_label", "changes", "reason", "ip_address",
            "request_id", "created_at",
        )

    def get_actor_name(self, obj) -> str:
        # "System" rather than null: a task-initiated action has an actor, it is
        # just not a person, and a blank column reads as missing data.
        return obj.actor.full_name if obj.actor_id else "System"


class PlatformSettingSerializer(serializers.ModelSerializer):
    typed_value = serializers.SerializerMethodField()
    updated_by_name = serializers.SerializerMethodField()

    class Meta:
        model = PlatformSetting
        fields = (
            "id", "key", "value", "typed_value", "value_type", "label",
            "description", "group", "is_public", "updated_by_name", "updated_at",
        )
        read_only_fields = fields

    def get_typed_value(self, obj):
        return obj.typed_value

    def get_updated_by_name(self, obj) -> str | None:
        return obj.updated_by.full_name if obj.updated_by_id else None


class SettingWriteSerializer(serializers.Serializer):
    value = serializers.CharField(allow_blank=True)


# ═══════════════════════════════════════════════════════════════════════════
# BROADCASTS
# ═══════════════════════════════════════════════════════════════════════════
class BroadcastSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    title = serializers.CharField(max_length=160)
    body = serializers.CharField(max_length=1000)
    audience = serializers.ChoiceField(
        choices=["ALL", "BUYERS", "PHOTOGRAPHERS", "CITY"], default="ALL"
    )
    city_filter = serializers.CharField(
        max_length=80, required=False, allow_blank=True
    )
    send_push = serializers.BooleanField(default=True)
    send_email = serializers.BooleanField(default=False)
    scheduled_for = serializers.DateTimeField(required=False, allow_null=True)
    sent_at = serializers.DateTimeField(read_only=True)
    recipient_count = serializers.IntegerField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)

    def validate(self, attrs):
        if attrs.get("audience") == "CITY" and not (attrs.get("city_filter") or "").strip():
            raise serializers.ValidationError(
                {"city_filter": "Name the city this announcement is for."}
            )
        return attrs


# ═══════════════════════════════════════════════════════════════════════════
# DASHBOARD
# ═══════════════════════════════════════════════════════════════════════════
class QueueCountSerializer(serializers.Serializer):
    pending_approvals = serializers.IntegerField()
    open_flags = serializers.IntegerField()
    pending_topups = serializers.IntegerField()
    products_awaiting_review = serializers.IntegerField()


class PlatformTotalsSerializer(serializers.Serializer):
    users = serializers.IntegerField()
    buyers = serializers.IntegerField()
    photographers = serializers.IntegerField()
    blocked_users = serializers.IntegerField()
    bookings_total = serializers.IntegerField()
    bookings_pending = serializers.IntegerField()
    bookings_accepted = serializers.IntegerField()
    bookings_completed = serializers.IntegerField()
    booking_gmv = serializers.CharField()
    orders_paid = serializers.IntegerField()
    shop_revenue = serializers.CharField()


class TrendPointSerializer(serializers.Serializer):
    date = serializers.DateField()
    new_users = serializers.IntegerField()
    bookings_created = serializers.IntegerField()
    bookings_completed = serializers.IntegerField()
    gross_booking_value = serializers.CharField()
    platform_commission = serializers.CharField()
    reviews_posted = serializers.IntegerField()


class AdminDashboardSerializer(serializers.Serializer):
    queues = QueueCountSerializer()
    totals = PlatformTotalsSerializer()
    trend = TrendPointSerializer(many=True)
    window_days = serializers.IntegerField()
