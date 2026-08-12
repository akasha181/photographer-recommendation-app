"""
Platform administration: approvals, moderation, audit and runtime settings.

WHY THE AUDIT LOG IS APPEND-ONLY
--------------------------------
An audit log an administrator can edit is not an audit log. `AuditLog` has no
update path in the admin (ReadOnlyAdminMixin), no service function that
modifies a row, and records the actor, the IP and the before/after state of
every privileged action. When a user asks "why was my account blocked", this
table answers it with evidence.

WHY PLATFORM SETTINGS LIVE IN THE DATABASE
------------------------------------------
Commission rate, booking expiry window and the recommendation blend weights
all need to change without a code deploy. Settings that never change at
runtime stay in settings.py; anything a non-developer might reasonably tune
lives here.
"""

from django.db import models

from apps.core.models import TimeStampedModel


class ApprovalStatus(models.TextChoices):
    PENDING = "PENDING", "Pending review"
    APPROVED = "APPROVED", "Approved"
    REJECTED = "REJECTED", "Rejected"
    MORE_INFO = "MORE_INFO", "More information required"


class ApprovalRequest(TimeStampedModel):
    """A photographer's application to become publicly listed."""

    photographer = models.ForeignKey(
        "profiles.PhotographerProfile", on_delete=models.CASCADE,
        related_name="approval_requests",
    )
    status = models.CharField(
        max_length=16, choices=ApprovalStatus.choices,
        default=ApprovalStatus.PENDING, db_index=True,
    )

    # Snapshot of what the reviewer saw, so a later profile edit cannot make
    # a past approval decision look unjustified.
    submitted_data = models.JSONField(default=dict, blank=True)

    reviewed_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="approval_reviews",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    admin_note = models.TextField(blank=True, max_length=1000)
    rejection_reason = models.TextField(blank=True, max_length=1000)

    class Meta:
        db_table = "approval_requests"
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["status", "created_at"], name="idx_approval_queue"),
        ]

    def __str__(self) -> str:
        return f"Approval for {self.photographer_id} [{self.status}]"


class FlagReason(models.TextChoices):
    INAPPROPRIATE = "INAPPROPRIATE", "Inappropriate content"
    COPYRIGHT = "COPYRIGHT", "Copyright infringement"
    SPAM = "SPAM", "Spam"
    FAKE = "FAKE", "Fake or misleading"
    HARASSMENT = "HARASSMENT", "Harassment"
    OFF_PLATFORM = "OFF_PLATFORM", "Attempting to take the deal off-platform"
    OTHER = "OTHER", "Other"


class ModerationFlag(TimeStampedModel):
    """
    A user report about any piece of content.

    `content_type` + `object_id` here is a deliberate, *narrow* generic
    reference: reports can target many kinds of content and the set genuinely
    grows over time, which is the one case where a generic relation earns its
    cost (unlike the wishlist, where the set is fixed at two).
    """

    reporter = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="flags_raised",
    )
    content_type = models.CharField(
        max_length=40,
        choices=[
            ("REVIEW", "Review"), ("PORTFOLIO_IMAGE", "Portfolio image"),
            ("PRODUCT", "Digital product"), ("MESSAGE", "Chat message"),
            ("PROFILE", "Profile"),
        ],
        db_index=True,
    )
    object_id = models.BigIntegerField(db_index=True)

    reason = models.CharField(max_length=24, choices=FlagReason.choices)
    detail = models.TextField(blank=True, max_length=1000)

    status = models.CharField(
        max_length=16,
        choices=[
            ("OPEN", "Open"), ("REVIEWING", "Under review"),
            ("ACTIONED", "Actioned"), ("DISMISSED", "Dismissed"),
        ],
        default="OPEN", db_index=True,
    )
    resolved_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="flags_resolved",
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolution_note = models.TextField(blank=True, max_length=1000)

    class Meta:
        db_table = "moderation_flags"
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["status", "-created_at"], name="idx_flag_queue"),
            models.Index(
                fields=["content_type", "object_id"], name="idx_flag_target"
            ),
        ]

    def __str__(self) -> str:
        return f"Flag on {self.content_type}#{self.object_id} [{self.status}]"


class AuditAction(models.TextChoices):
    USER_BLOCKED = "USER_BLOCKED", "User blocked"
    USER_UNBLOCKED = "USER_UNBLOCKED", "User unblocked"
    USER_DELETED = "USER_DELETED", "User deleted"
    PHOTOGRAPHER_APPROVED = "PHOTOGRAPHER_APPROVED", "Photographer approved"
    PHOTOGRAPHER_REJECTED = "PHOTOGRAPHER_REJECTED", "Photographer rejected"
    BOOKING_FORCE_CANCELLED = "BOOKING_FORCE_CANCELLED", "Booking force-cancelled"
    PRODUCT_APPROVED = "PRODUCT_APPROVED", "Product approved"
    PRODUCT_REMOVED = "PRODUCT_REMOVED", "Product removed"
    REVIEW_HIDDEN = "REVIEW_HIDDEN", "Review hidden"
    WALLET_ADJUSTED = "WALLET_ADJUSTED", "Wallet adjusted"
    TOPUP_APPROVED = "TOPUP_APPROVED", "Top-up approved"
    TOPUP_REJECTED = "TOPUP_REJECTED", "Top-up rejected"
    SETTING_CHANGED = "SETTING_CHANGED", "Platform setting changed"
    CATEGORY_CHANGED = "CATEGORY_CHANGED", "Category changed"
    BROADCAST_SENT = "BROADCAST_SENT", "Broadcast sent"
    MODEL_PROMOTED = "MODEL_PROMOTED", "ML model promoted"


class AuditLog(TimeStampedModel):
    """Append-only. Never updated, never deleted."""

    actor = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="audit_entries",
    )
    action = models.CharField(max_length=40, choices=AuditAction.choices, db_index=True)

    target_type = models.CharField(max_length=40, blank=True, db_index=True)
    target_id = models.CharField(max_length=64, blank=True, db_index=True)
    target_label = models.CharField(
        max_length=200, blank=True,
        help_text="Human-readable snapshot, so the log stays readable even "
                  "after the target row is anonymised or removed.",
    )

    # Before/after is what turns "someone changed it" into "here is exactly
    # what changed".
    changes = models.JSONField(default=dict, blank=True)
    reason = models.TextField(blank=True, max_length=1000)

    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=300, blank=True)
    request_id = models.CharField(max_length=40, blank=True, db_index=True)

    class Meta:
        db_table = "audit_logs"
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["actor", "-created_at"], name="idx_audit_by_actor"),
            models.Index(fields=["action", "-created_at"], name="idx_audit_by_action"),
        ]

    def __str__(self) -> str:
        return f"{self.action} by {self.actor_id} on {self.target_type}#{self.target_id}"


class PlatformSetting(TimeStampedModel):
    """
    Runtime-tunable configuration.

    Typed `value_type` exists so the API can hand back a real int/float/bool
    instead of the caller string-parsing every read and getting it wrong once.
    """

    key = models.CharField(max_length=80, unique=True, db_index=True)
    value = models.TextField()
    value_type = models.CharField(
        max_length=16,
        choices=[
            ("STRING", "String"), ("INT", "Integer"),
            ("FLOAT", "Float"), ("BOOL", "Boolean"), ("JSON", "JSON"),
        ],
        default="STRING",
    )
    label = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    group = models.CharField(
        max_length=40, default="general", db_index=True,
        help_text="Groups settings into tabs in the admin dashboard.",
    )
    is_public = models.BooleanField(
        default=False, help_text="Exposed to the mobile app via /settings/public/."
    )
    updated_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="setting_changes",
    )

    class Meta:
        db_table = "platform_settings"
        ordering = ("group", "key")

    def __str__(self) -> str:
        return f"{self.key} = {self.value}"

    @property
    def typed_value(self):
        import json

        try:
            if self.value_type == "INT":
                return int(self.value)
            if self.value_type == "FLOAT":
                return float(self.value)
            if self.value_type == "BOOL":
                return self.value.strip().lower() in ("1", "true", "yes", "on")
            if self.value_type == "JSON":
                return json.loads(self.value)
        except (ValueError, TypeError, json.JSONDecodeError):
            return self.value
        return self.value
