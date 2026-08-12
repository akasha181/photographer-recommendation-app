from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from apps.accounts.models import Device, OTPCode, User
from apps.core.admin import ReadOnlyAdminMixin


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    ordering = ("-created_at",)
    list_display = (
        "email", "full_name", "role", "city",
        "is_email_verified", "is_blocked", "is_active", "created_at",
    )
    list_filter = ("role", "is_blocked", "is_active", "is_email_verified", "city")
    search_fields = ("email", "full_name", "phone")
    readonly_fields = ("created_at", "updated_at", "last_login", "token_version")

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Personal", {"fields": ("full_name", "phone", "avatar", "city",
                                 "latitude", "longitude")}),
        ("Role & status", {"fields": ("role", "is_active", "is_staff", "is_superuser",
                                      "is_email_verified", "is_phone_verified")}),
        ("Moderation", {"fields": ("is_blocked", "blocked_reason", "blocked_at",
                                   "blocked_by", "is_deleted", "deleted_at")}),
        ("Security", {"fields": ("token_version", "failed_login_attempts",
                                 "locked_until", "last_login_ip")}),
        ("Permissions", {"fields": ("groups", "user_permissions"), "classes": ("collapse",)}),
        ("Timestamps", {"fields": ("last_login", "created_at", "updated_at")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "full_name", "role", "password1", "password2"),
            },
        ),
    )


@admin.register(OTPCode)
class OTPCodeAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    """Read-only: codes are hashed, and editing one would only break it."""

    list_display = ("user", "purpose", "expires_at", "used_at", "attempts", "created_at")
    list_filter = ("purpose",)
    search_fields = ("user__email",)


@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ("user", "platform", "app_version", "is_active", "last_seen_at")
    list_filter = ("platform", "is_active")
    search_fields = ("user__email", "device_id")
