"""
Abstract base models shared by every app.

Nothing here creates a table — these are mixins that guarantee every domain
model has consistent timestamps, soft-delete behaviour and UUID identifiers
where needed.
"""

import uuid

from django.db import models
from django.utils import timezone


class TimeStampedModel(models.Model):
    """Adds `created_at` / `updated_at`. Every model in SnapSphere inherits it."""

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        get_latest_by = "created_at"


class SoftDeleteQuerySet(models.QuerySet):
    """QuerySet that understands soft deletion."""

    def alive(self):
        return self.filter(is_deleted=False)

    def dead(self):
        return self.filter(is_deleted=True)

    def delete(self):
        """Bulk soft-delete — overrides the destructive default."""
        return self.update(is_deleted=True, deleted_at=timezone.now())

    def hard_delete(self):
        """Genuinely remove rows. Use only in data-repair scripts."""
        return super().delete()


class SoftDeleteManager(models.Manager):
    """Default manager that hides soft-deleted rows."""

    def get_queryset(self):
        return SoftDeleteQuerySet(self.model, using=self._db).filter(is_deleted=False)


class AllObjectsManager(models.Manager):
    """Escape hatch that sees deleted rows too (admin, audits, reports)."""

    def get_queryset(self):
        return SoftDeleteQuerySet(self.model, using=self._db)


class SoftDeleteModel(models.Model):
    """
    Rows are never physically removed.

    Why: a deleted booking or user is still referenced by financial records,
    audit logs and analytics. Hard deletion would either break those foreign
    keys or silently destroy history the platform is accountable for.
    """

    is_deleted = models.BooleanField(default=False, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    objects = SoftDeleteManager()
    all_objects = AllObjectsManager()

    class Meta:
        abstract = True

    def delete(self, using=None, keep_parents=False):
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.save(update_fields=["is_deleted", "deleted_at", "updated_at"])

    def restore(self):
        self.is_deleted = False
        self.deleted_at = None
        self.save(update_fields=["is_deleted", "deleted_at", "updated_at"])

    def hard_delete(self, using=None, keep_parents=False):
        super().delete(using=using, keep_parents=keep_parents)


class UUIDModel(models.Model):
    """
    Adds a public, non-guessable identifier.

    Sequential integer PKs leak business volume ("booking #4" tells a
    competitor you have four bookings) and invite enumeration attacks. Models
    exposed in shareable URLs carry a UUID for external use while keeping the
    fast integer PK internally.
    """

    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)

    class Meta:
        abstract = True


class BaseModel(TimeStampedModel, SoftDeleteModel):
    """Convenience combination used by most domain models."""

    class Meta:
        abstract = True
