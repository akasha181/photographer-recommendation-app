"""Shared admin base classes."""

from django.contrib import admin


class ReadOnlyAdminMixin:
    """Admin view that can look but never touch — used for audit-log models."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class BaseModelAdmin(admin.ModelAdmin):
    """Sensible defaults: newest first, timestamps visible but not editable."""

    readonly_fields = ("created_at", "updated_at")
    list_per_page = 50
    ordering = ("-created_at",)
