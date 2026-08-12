"""
Read-side queries for the wishlist.

The list is deliberately split by type rather than returned as one
heterogeneous array. A photographer card and a product card render nothing in
common, so a mixed list forces the client to branch per row and makes the
response impossible to type cleanly.
"""

from __future__ import annotations

from django.db.models import QuerySet

from apps.wishlist.models import WishlistItem


def get_wishlist(user) -> QuerySet[WishlistItem]:
    """Everything saved, newest first, with both targets pre-joined."""
    return (
        WishlistItem.objects.filter(user=user)
        .select_related(
            "photographer",
            "photographer__user",
            "product",
            "product__seller",
            "product__seller__user",
        )
        .prefetch_related("photographer__categories")
        .order_by("-created_at")
    )


def saved_photographers(user) -> QuerySet[WishlistItem]:
    """
    Saved photographers who are still publicly visible.

    A suspended photographer must not keep appearing in someone's saved list —
    tapping through to a dead profile is worse than the row quietly going away.
    """
    return get_wishlist(user).filter(
        photographer__isnull=False,
        photographer__is_approved=True,
        photographer__is_deleted=False,
        photographer__user__is_active=True,
        photographer__user__is_blocked=False,
    )


def saved_products(user) -> QuerySet[WishlistItem]:
    return get_wishlist(user).filter(
        product__isnull=False,
        product__is_published=True,
        product__is_approved=True,
        product__is_deleted=False,
    )


def wishlisted_photographer_ids(user) -> set[int]:
    """One query, handed to serializers through context."""
    if not user or not user.is_authenticated:
        return set()
    return set(
        WishlistItem.objects.filter(user=user, photographer__isnull=False).values_list(
            "photographer_id", flat=True
        )
    )


def wishlisted_product_ids(user) -> set[int]:
    if not user or not user.is_authenticated:
        return set()
    return set(
        WishlistItem.objects.filter(user=user, product__isnull=False).values_list(
            "product_id", flat=True
        )
    )


def wishlist_counts(user) -> dict[str, int]:
    return {
        "photographers": saved_photographers(user).count(),
        "products": saved_products(user).count(),
    }
