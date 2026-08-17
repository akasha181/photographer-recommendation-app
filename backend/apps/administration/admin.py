"""
Django admin registrations for the administration app.

WHY THESE MODELS AND NOT EVERY MODEL
------------------------------------
`/django-admin/` is emergency ops, not the product admin (see config/urls.py) —
the product admin is the REST API in `views.py`. What earns a place here is what
an operator may need when the API is not enough: reading the audit trail,
editing a platform setting by hand, and seeing the moderation queue without a
token.

`AuditLog` is registered through `ReadOnlyAdminMixin`, which existed in
`core/admin.py` unused. An audit log an administrator can edit is not an audit
log, and "the API has no write path" is only half the guarantee while Django's
admin offers a change form for the same table.
"""

from django.contrib import admin

from apps.administration.models import (
    ApprovalRequest,
    AuditLog,
    ModerationFlag,
    PlatformSetting,
)
from apps.core.admin import BaseModelAdmin, ReadOnlyAdminMixin


@admin.register(ApprovalRequest)
class ApprovalRequestAdmin(BaseModelAdmin):
    list_display = ("photographer", "status", "reviewed_by", "reviewed_at", "created_at")
    list_filter = ("status",)
    search_fields = ("photographer__business_name", "photographer__user__email")
    autocomplete_fields = ()
    readonly_fields = BaseModelAdmin.readonly_fields + ("submitted_data",)


@admin.register(ModerationFlag)
class ModerationFlagAdmin(BaseModelAdmin):
    list_display = (
        "content_type", "object_id", "reason", "status", "reporter", "created_at",
    )
    list_filter = ("status", "content_type", "reason")
    search_fields = ("detail", "resolution_note")


@admin.register(AuditLog)
class AuditLogAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    """Append-only. No add form, no change form, no delete."""

    list_display = ("created_at", "action", "actor", "target_type", "target_label")
    list_filter = ("action", "target_type")
    search_fields = ("target_label", "reason", "request_id")
    ordering = ("-created_at",)
    list_per_page = 100


@admin.register(PlatformSetting)
class PlatformSettingAdmin(BaseModelAdmin):
    """
    Editable here on purpose.

    The API refuses unknown keys — settings are declared, not created ad hoc —
    so declaring a NEW one is a deliberate act, and this is where it happens.
    Changes made here are not audited (there is no request behind them), which
    is why routine tuning belongs on `PATCH /admin/settings/{key}/`.
    """

    list_display = ("key", "value", "value_type", "group", "is_public", "updated_at")
    list_filter = ("group", "value_type", "is_public")
    search_fields = ("key", "label", "description")
    ordering = ("group", "key")
