"""
The Shop HTTP surface.

Covers what the service tests cannot: visibility rules at the endpoint, the
per-request flag loading that keeps the grid at a constant query count, and
the shapes the mobile app parses.
"""

import pytest

from apps.marketplace.services import add_to_cart, checkout

pytestmark = pytest.mark.django_db

URL = "/api/v1/marketplace/"


# ═══════════════════════════════════════════════════════════════════════════
# BROWSING
# ═══════════════════════════════════════════════════════════════════════════
def test_browsing_is_public(api_client, product):
    response = api_client.get(f"{URL}products/")

    assert response.status_code == 200
    assert [row["slug"] for row in response.json()["data"]] == [product.slug]


def test_anonymous_flags_are_all_false(api_client, product):
    row = api_client.get(f"{URL}products/").json()["data"][0]

    assert row["is_owned"] is False
    assert row["is_wishlisted"] is False
    assert row["in_cart"] is False


def test_unapproved_products_are_hidden(api_client, product):
    product.is_approved = False
    product.save(update_fields=["is_approved"])
    assert api_client.get(f"{URL}products/").json()["data"] == []


def test_a_suspended_sellers_catalogue_disappears(api_client, product, photographer):
    """
    A blocked photographer's products must not stay on sale — they would take
    a buyer's money and credit a wallet the platform has disabled.
    """
    photographer.user.is_blocked = True
    photographer.user.save(update_fields=["is_blocked"])

    assert api_client.get(f"{URL}products/").json()["data"] == []


def test_detail_by_slug(api_client, product):
    body = api_client.get(f"{URL}products/{product.slug}/").json()["data"]

    assert body["title"] == product.title
    assert body["discount_percent"] == 30
    assert len(body["files"]) == 2


def test_detail_counts_a_view(api_client, product):
    api_client.get(f"{URL}products/{product.slug}/")
    product.refresh_from_db()
    assert product.view_count == 1


def test_unknown_slug_is_404(api_client):
    assert api_client.get(f"{URL}products/nope/").status_code == 404


def test_search_and_filters(api_client, product, second_product):
    def slugs(query):
        return {r["slug"] for r in api_client.get(f"{URL}products/?{query}").json()["data"]}

    assert slugs("q=desi") == {product.slug}
    assert slugs("product_type=WEDDING_LUT") == {second_product.slug}
    assert slugs("max_price=2500") == {second_product.slug}
    assert slugs("on_sale=true") == {product.slug}
    assert slugs("ordering=price") == {product.slug, second_product.slug}


def test_affordable_filter_uses_the_callers_balance(
    buyer_client, funded_buyer, product, second_product
):
    """Resolved in the view — the FilterSet has no idea who is asking."""
    from decimal import Decimal

    from apps.profiles.models import Wallet

    Wallet.objects.filter(user=funded_buyer).update(balance=Decimal("2500.00"))
    rows = buyer_client.get(f"{URL}products/?affordable=true").json()["data"]

    assert {r["slug"] for r in rows} == {second_product.slug}


def test_filter_options_come_from_the_data(api_client, product, second_product):
    body = api_client.get(f"{URL}products/filters/").json()["data"]

    assert body["price_range"] == {"min": 2000.0, "max": 3500.0}
    assert {t["value"] for t in body["types"]} == {"LIGHTROOM_PRESET", "WEDDING_LUT"}
    assert body["sort_options"]


def test_featured_and_bestsellers(api_client, product, second_product):
    product.is_featured = True
    product.save(update_fields=["is_featured"])

    featured = api_client.get(f"{URL}products/featured/").json()["data"]
    best = api_client.get(f"{URL}products/bestsellers/").json()["data"]

    assert [r["slug"] for r in featured] == [product.slug]
    assert len(best) == 2


def test_the_grid_costs_a_constant_number_of_queries(
    buyer_client, product, second_product, django_assert_max_num_queries
):
    """
    Ownership, wishlist and cart membership are loaded once per request. Read
    per row instead, a 20-card grid would cost 60 extra queries.
    """
    with django_assert_max_num_queries(9):
        buyer_client.get(f"{URL}products/")


# ═══════════════════════════════════════════════════════════════════════════
# CART OVER HTTP
# ═══════════════════════════════════════════════════════════════════════════
def test_cart_round_trip(buyer_client, product):
    empty = buyer_client.get(f"{URL}cart/").json()["data"]
    assert empty["count"] == 0
    assert empty["can_checkout"] is False

    added = buyer_client.post(f"{URL}cart/add/", {"product": product.pk}, format="json")
    assert added.status_code == 201
    assert added.json()["data"]["count"] == 1
    assert added.json()["data"]["subtotal"] == "3500.00"

    removed = buyer_client.post(f"{URL}cart/remove/{product.pk}/", {}, format="json")
    assert removed.json()["data"]["count"] == 0


def test_cart_reports_the_shortfall(buyer_client, product):
    """The number the top-up screen needs, computed once, server-side."""
    body = buyer_client.post(
        f"{URL}cart/add/", {"product": product.pk}, format="json"
    ).json()["data"]

    assert body["can_checkout"] is False
    assert body["shortfall"] == "3500.00"


def test_a_funded_cart_can_check_out(buyer_client, funded_buyer, product):
    body = buyer_client.post(
        f"{URL}cart/add/", {"product": product.pk}, format="json"
    ).json()["data"]

    assert body["wallet_balance"] == "50000.00"
    assert body["can_checkout"] is True
    assert body["shortfall"] == "0"


def test_cart_flags_a_line_that_went_off_sale(buyer_client, funded_buyer, product):
    """
    Reported per line, so the buyer removes the offending item rather than
    facing one opaque error for the whole basket.
    """
    add_to_cart(funded_buyer, product)
    product.is_published = False
    product.save(update_fields=["is_published"])

    body = buyer_client.get(f"{URL}cart/").json()["data"]
    assert body["unavailable_count"] == 1
    assert body["items"][0]["is_available"] is False
    assert body["can_checkout"] is False


def test_clear_empties_the_cart(buyer_client, product, second_product):
    buyer_client.post(f"{URL}cart/add/", {"product": product.pk}, format="json")
    buyer_client.post(f"{URL}cart/add/", {"product": second_product.pk}, format="json")

    assert buyer_client.post(f"{URL}cart/clear/", {}, format="json").json()["data"]["count"] == 0


def test_cart_is_private(other_buyer_client, funded_buyer, product):
    add_to_cart(funded_buyer, product)
    assert other_buyer_client.get(f"{URL}cart/").json()["data"]["count"] == 0


def test_anonymous_has_no_cart(api_client):
    assert api_client.get(f"{URL}cart/").status_code == 401


# ═══════════════════════════════════════════════════════════════════════════
# CHECKOUT & ORDERS OVER HTTP
# ═══════════════════════════════════════════════════════════════════════════
def test_checkout_over_http(buyer_client, funded_buyer, product):
    add_to_cart(funded_buyer, product)
    response = buyer_client.post(
        f"{URL}orders/checkout/", {}, format="json",
        HTTP_IDEMPOTENCY_KEY="tap-1",
    )

    assert response.status_code == 201
    body = response.json()["data"]
    assert body["status"] == "PAID"
    assert body["total"] == "3500.00"
    assert len(body["items"]) == 1


def test_checkout_ignores_a_client_supplied_total(buyer_client, funded_buyer, product):
    """The cart is the source of truth; the body carries no money at all."""
    add_to_cart(funded_buyer, product)
    body = buyer_client.post(
        f"{URL}orders/checkout/", {"total": "1.00", "subtotal": "1.00"}, format="json"
    ).json()["data"]

    assert body["total"] == "3500.00"


def test_a_retry_with_the_same_key_charges_once(buyer_client, funded_buyer, product):
    add_to_cart(funded_buyer, product)
    headers = {"HTTP_IDEMPOTENCY_KEY": "tap-1"}

    first = buyer_client.post(f"{URL}orders/checkout/", {}, format="json", **headers)
    second = buyer_client.post(f"{URL}orders/checkout/", {}, format="json", **headers)

    assert first.json()["data"]["id"] == second.json()["data"]["id"]


def test_checkout_without_funds_is_422(buyer_client, buyer, product):
    add_to_cart(buyer, product)
    response = buyer_client.post(f"{URL}orders/checkout/", {}, format="json")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INSUFFICIENT_BALANCE"


def test_orders_list_and_detail(buyer_client, funded_buyer, product):
    add_to_cart(funded_buyer, product)
    order = checkout(funded_buyer)

    listed = buyer_client.get(f"{URL}orders/").json()["data"]
    assert [row["order_number"] for row in listed] == [order.order_number]

    detail = buyer_client.get(f"{URL}orders/{order.pk}/").json()["data"]
    assert detail["items"][0]["product_title"] == product.title


def test_someone_elses_order_is_404(other_buyer_client, funded_buyer, product):
    add_to_cart(funded_buyer, product)
    order = checkout(funded_buyer)

    assert other_buyer_client.get(f"{URL}orders/{order.pk}/").status_code == 404


def test_ownership_shows_up_in_the_grid(buyer_client, funded_buyer, product):
    add_to_cart(funded_buyer, product)
    checkout(funded_buyer)

    row = buyer_client.get(f"{URL}products/").json()["data"][0]
    assert row["is_owned"] is True


# ═══════════════════════════════════════════════════════════════════════════
# SELLER VIEW
# ═══════════════════════════════════════════════════════════════════════════
def test_seller_sees_their_own_catalogue(photographer_client, product):
    rows = photographer_client.get(f"{URL}seller/products/").json()["data"]
    assert [r["slug"] for r in rows] == [product.slug]


def test_seller_summary_reflects_a_sale(
    photographer_client, funded_buyer, product
):
    add_to_cart(funded_buyer, product)
    checkout(funded_buyer)

    body = photographer_client.get(f"{URL}seller/products/summary/").json()["data"]
    assert body["sales_count"] == 1
    assert body["gross_revenue"] == "3500.00"
    assert body["net_earnings"] == "2975.00"   # 15% commission


def test_a_buyer_has_no_seller_catalogue(buyer_client):
    assert buyer_client.get(f"{URL}seller/products/").status_code == 404
