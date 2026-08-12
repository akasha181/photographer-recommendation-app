"""
Wishlist writes.

WHY TOGGLE RATHER THAN ADD AND REMOVE
-------------------------------------
The UI is a heart icon: one control, two outcomes. Exposing separate add and
remove endpoints makes the client track which state it believes the server is
in, and a double-tap on a slow connection then sends two ADDs or two REMOVEs
and ends up disagreeing with the icon it just drew.

`toggle` returns what the state IS now, not what changed, so the client
renders the truth rather than a guess.
"""

import logging

from django.db import IntegrityError, transaction
from django.db.models import F

from apps.core.exceptions import BusinessRuleViolation
from apps.wishlist.models import WishlistItem

logger = logging.getLogger("snapsphere")


@transaction.atomic
def toggle_photographer(user, photographer) -> bool:
    """Returns True if it is now saved, False if it was just removed."""
    existing = WishlistItem.objects.filter(user=user, photographer=photographer).first()
    if existing is not None:
        existing.delete()
        return False

    try:
        WishlistItem.objects.create(user=user, photographer=photographer)
    except IntegrityError:
        # Two taps landing together: the unique constraint caught the second.
        # It is saved either way, which is what the caller asked for.
        return True

    _log_interaction(user, photographer)
    return True


@transaction.atomic
def toggle_product(user, product) -> bool:
    from apps.marketplace.models import DigitalProduct

    existing = WishlistItem.objects.filter(user=user, product=product).first()
    if existing is not None:
        existing.delete()
        # Guarded against underflow: wishlist_count is a PositiveIntegerField,
        # so decrementing a zero would raise rather than clamp.
        DigitalProduct.objects.filter(pk=product.pk, wishlist_count__gt=0).update(
            wishlist_count=F("wishlist_count") - 1
        )
        return False

    try:
        WishlistItem.objects.create(user=user, product=product)
    except IntegrityError:
        return True

    DigitalProduct.objects.filter(pk=product.pk).update(
        wishlist_count=F("wishlist_count") + 1
    )
    return True


def remove_item(user, item_id: int) -> None:
    deleted, _ = WishlistItem.objects.filter(user=user, pk=item_id).delete()
    if not deleted:
        raise BusinessRuleViolation("That item is not in your wishlist.")


def clear(user) -> int:
    deleted, _ = WishlistItem.objects.filter(user=user).delete()
    return deleted


def _log_interaction(user, photographer) -> None:
    """
    Saving a photographer is strong implicit feedback for the recommender —
    stronger than a view, weaker than a booking. See INTERACTION_WEIGHTS.
    """
    try:
        from apps.recommendations.models import BuyerInteraction, BuyerInteractionType

        BuyerInteraction.objects.create(
            buyer=user,
            photographer=photographer,
            interaction_type=BuyerInteractionType.WISHLIST,
            category=photographer.categories.first(),
        )
    except Exception:  # noqa: BLE001 — analytics must never break the tap
        pass
