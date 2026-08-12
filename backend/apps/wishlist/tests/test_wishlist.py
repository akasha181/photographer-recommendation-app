"""
Wishlist — Module 4.

The behaviour worth pinning is that `toggle` reports the state it left behind,
not the change it made, so a heart icon can render the truth after a
double-tap on a slow connection.
"""

import pytest

from apps.wishlist.models import WishlistItem
from apps.wishlist.services import clear, toggle_photographer, toggle_product

pytestmark = pytest.mark.django_db

URL = "/api/v1/wishlist/"


# ═══════════════════════════════════════════════════════════════════════════
# SERVICE
# ═══════════════════════════════════════════════════════════════════════════
def test_toggle_saves_then_unsaves(buyer, photographer):
    assert toggle_photographer(buyer, photographer) is True
    assert WishlistItem.objects.filter(user=buyer).count() == 1

    assert toggle_photographer(buyer, photographer) is False
    assert WishlistItem.objects.filter(user=buyer).count() == 0


def test_saving_a_photographer_feeds_the_recommender(buyer, photographer):
    from apps.recommendations.models import BuyerInteraction

    toggle_photographer(buyer, photographer)

    assert BuyerInteraction.objects.filter(
        buyer=buyer, photographer=photographer, interaction_type="WISHLIST"
    ).exists()


def test_saving_a_product_moves_its_counter(buyer, product):
    toggle_product(buyer, product)
    product.refresh_from_db()
    assert product.wishlist_count == 1

    toggle_product(buyer, product)
    product.refresh_from_db()
    assert product.wishlist_count == 0


def test_the_product_counter_never_goes_negative(buyer, product):
    """
    `wishlist_count` is a PositiveIntegerField — decrementing a zero raises
    rather than clamping, so the guard is not decorative.
    """
    toggle_product(buyer, product)
    WishlistItem.objects.filter(user=buyer, product=product).delete()
    product.refresh_from_db()
    product.wishlist_count = 0
    product.save(update_fields=["wishlist_count"])

    toggle_product(buyer, product)   # save
    toggle_product(buyer, product)   # unsave, counter already at 0 + 1
    product.refresh_from_db()
    assert product.wishlist_count >= 0


def test_two_users_save_the_same_photographer(buyer, other_buyer, photographer):
    toggle_photographer(buyer, photographer)
    toggle_photographer(other_buyer, photographer)

    assert WishlistItem.objects.filter(photographer=photographer).count() == 2


def test_clear_empties_everything(buyer, photographer, product):
    toggle_photographer(buyer, photographer)
    toggle_product(buyer, product)

    assert clear(buyer) == 2
    assert WishlistItem.objects.filter(user=buyer).count() == 0


# ═══════════════════════════════════════════════════════════════════════════
# VISIBILITY
# ═══════════════════════════════════════════════════════════════════════════
def test_a_suspended_photographer_drops_out_of_the_list(buyer, photographer):
    """
    Tapping through to a dead profile is worse than the row quietly going
    away — the underlying record is kept, it is just not shown.
    """
    from apps.wishlist import selectors

    toggle_photographer(buyer, photographer)
    assert selectors.saved_photographers(buyer).count() == 1

    photographer.user.is_blocked = True
    photographer.user.save(update_fields=["is_blocked"])

    assert selectors.saved_photographers(buyer).count() == 0
    assert WishlistItem.objects.filter(user=buyer).count() == 1


def test_a_delisted_product_drops_out_of_the_list(buyer, product):
    from apps.wishlist import selectors

    toggle_product(buyer, product)
    product.is_published = False
    product.save(update_fields=["is_published"])

    assert selectors.saved_products(buyer).count() == 0


# ═══════════════════════════════════════════════════════════════════════════
# API
# ═══════════════════════════════════════════════════════════════════════════
def test_toggle_over_http(buyer_client, photographer):
    response = buyer_client.post(
        f"{URL}toggle/", {"photographer": photographer.pk}, format="json"
    )

    assert response.status_code == 200
    assert response.json()["data"]["is_saved"] is True
    assert response.json()["data"]["counts"]["photographers"] == 1

    again = buyer_client.post(
        f"{URL}toggle/", {"photographer": photographer.pk}, format="json"
    )
    assert again.json()["data"]["is_saved"] is False


def test_toggle_requires_exactly_one_target(buyer_client, photographer, product):
    both = buyer_client.post(
        f"{URL}toggle/",
        {"photographer": photographer.pk, "product": product.pk},
        format="json",
    )
    neither = buyer_client.post(f"{URL}toggle/", {}, format="json")

    assert both.status_code == 400
    assert neither.status_code == 400


def test_toggling_an_invisible_photographer_is_404(buyer_client, photographer):
    photographer.is_approved = False
    photographer.save(update_fields=["is_approved"])

    response = buyer_client.post(
        f"{URL}toggle/", {"photographer": photographer.pk}, format="json"
    )
    assert response.status_code == 404


def test_list_splits_by_type(buyer_client, buyer, photographer, product):
    toggle_photographer(buyer, photographer)
    toggle_product(buyer, product)

    body = buyer_client.get(URL).json()["data"]

    assert len(body["photographers"]) == 1
    assert len(body["products"]) == 1
    assert body["counts"] == {"photographers": 1, "products": 1}
    # Each row reuses the card shape its own screen already renders.
    assert body["photographers"][0]["photographer"]["display_name"]
    assert body["products"][0]["product"]["price"]


def test_wishlist_is_private(other_buyer_client, buyer, photographer):
    toggle_photographer(buyer, photographer)
    body = other_buyer_client.get(URL).json()["data"]

    assert body["photographers"] == []


def test_anonymous_is_refused(api_client):
    assert api_client.get(URL).status_code == 401


def test_the_shop_grid_reflects_saved_state(buyer_client, buyer, product):
    toggle_product(buyer, product)
    body = buyer_client.get("/api/v1/marketplace/products/").json()["data"]
    row = next(r for r in body if r["id"] == product.pk)

    assert row["is_wishlisted"] is True
