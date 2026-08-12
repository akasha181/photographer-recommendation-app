"""
Wishlist — saved photographers and products.

WHY TWO NULLABLE FOREIGN KEYS INSTEAD OF A GENERIC RELATION
-----------------------------------------------------------
Django's contenttypes framework would model "save anything" elegantly, but it
costs a JOIN through django_content_type on every read and makes
`select_related` impossible. With exactly two saveable types — and no third on
the roadmap — two nullable FKs are faster, indexable, and enforce referential
integrity that a generic `object_id` integer cannot.

A CheckConstraint guarantees exactly one of them is set, so the table can never
hold a row that points at nothing or at both.
"""

from django.db import models

from apps.core.models import TimeStampedModel


class WishlistItem(TimeStampedModel):
    user = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="wishlist_items"
    )
    photographer = models.ForeignKey(
        "profiles.PhotographerProfile", null=True, blank=True,
        on_delete=models.CASCADE, related_name="wishlisted_by",
    )
    product = models.ForeignKey(
        "marketplace.DigitalProduct", null=True, blank=True,
        on_delete=models.CASCADE, related_name="wishlisted_by",
    )
    note = models.CharField(max_length=200, blank=True)

    class Meta:
        db_table = "wishlist_items"
        ordering = ("-created_at",)
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(photographer__isnull=False, product__isnull=True)
                    | models.Q(photographer__isnull=True, product__isnull=False)
                ),
                name="ck_wishlist_exactly_one_target",
            ),
            models.UniqueConstraint(
                fields=["user", "photographer"],
                condition=models.Q(photographer__isnull=False),
                name="uniq_wishlist_photographer",
            ),
            models.UniqueConstraint(
                fields=["user", "product"],
                condition=models.Q(product__isnull=False),
                name="uniq_wishlist_product",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "-created_at"], name="idx_wishlist_by_user"),
        ]

    def __str__(self) -> str:
        target = self.photographer or self.product
        return f"{self.user.email} ♥ {target}"

    @property
    def item_type(self) -> str:
        return "photographer" if self.photographer_id else "product"
