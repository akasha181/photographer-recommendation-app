"""
Cart and wallet checkout — Module 8.

The property under test throughout: money and goods move together, or neither
moves. Every failure path below is checked for *both* halves — a buyer who was
charged must own something, and a buyer who owns nothing must not have been
charged.
"""

from decimal import Decimal

import pytest

from apps.core.exceptions import BusinessRuleViolation, ResourceGone
from apps.marketplace.models import CartItem, Order, OrderItem, OrderStatus
from apps.marketplace.services import (
    add_to_cart,
    checkout,
    clear_cart,
    remove_from_cart,
)
from apps.profiles.models import Wallet, WalletTransaction

pytestmark = pytest.mark.django_db


def balance(user) -> Decimal:
    return Wallet.objects.get(user=user).balance


# ═══════════════════════════════════════════════════════════════════════════
# CART
# ═══════════════════════════════════════════════════════════════════════════
def test_add_to_cart(buyer, product):
    add_to_cart(buyer, product)
    assert CartItem.objects.filter(user=buyer, product=product).count() == 1


def test_adding_twice_is_not_an_error(buyer, product):
    """A digital product has no quantity — the second tap just means 'yes'."""
    add_to_cart(buyer, product)
    add_to_cart(buyer, product)
    assert CartItem.objects.filter(user=buyer).count() == 1


def test_cannot_cart_your_own_product(photographer, product):
    with pytest.raises(BusinessRuleViolation, match="your own product"):
        add_to_cart(photographer.user, product)


def test_cannot_cart_an_unpublished_product(buyer, product):
    product.is_published = False
    product.save(update_fields=["is_published"])

    with pytest.raises(ResourceGone, match="no longer available"):
        add_to_cart(buyer, product)


def test_cannot_cart_something_already_owned(funded_buyer, product):
    add_to_cart(funded_buyer, product)
    checkout(funded_buyer)

    with pytest.raises(BusinessRuleViolation, match="already own"):
        add_to_cart(funded_buyer, product)


def test_remove_and_clear(buyer, product, second_product):
    add_to_cart(buyer, product)
    add_to_cart(buyer, second_product)

    remove_from_cart(buyer, product.pk)
    assert CartItem.objects.filter(user=buyer).count() == 1

    clear_cart(buyer)
    assert CartItem.objects.filter(user=buyer).count() == 0


# ═══════════════════════════════════════════════════════════════════════════
# CHECKOUT — HAPPY PATH
# ═══════════════════════════════════════════════════════════════════════════
def test_checkout_creates_a_paid_order(funded_buyer, product):
    add_to_cart(funded_buyer, product)
    order = checkout(funded_buyer)

    assert order.status == OrderStatus.PAID
    assert order.paid_at is not None
    assert order.total == product.price
    assert order.items.count() == 1


def test_checkout_debits_the_wallet_exactly_once(funded_buyer, product):
    before = balance(funded_buyer)
    add_to_cart(funded_buyer, product)
    checkout(funded_buyer)

    assert balance(funded_buyer) == before - product.price
    assert (
        WalletTransaction.objects.filter(
            wallet__user=funded_buyer, txn_type="PURCHASE"
        ).count()
        == 1
    )


def test_checkout_credits_the_seller_net_of_commission(funded_buyer, product, photographer):
    add_to_cart(funded_buyer, product)
    order = checkout(funded_buyer)
    item = order.items.first()

    expected_commission = (
        product.price * product.commission_percent / Decimal("100")
    ).quantize(Decimal("0.01"))

    assert item.commission_amount == expected_commission
    assert item.seller_earning == product.price - expected_commission
    assert balance(photographer.user) == item.seller_earning


def test_one_seller_is_credited_once_for_a_multi_item_basket(
    funded_buyer, product, second_product, photographer
):
    """
    Three products from one photographer must move their balance once, not
    three times, or the ledger reads like three separate sales.
    """
    add_to_cart(funded_buyer, product)
    add_to_cart(funded_buyer, second_product)
    order = checkout(funded_buyer)

    earnings = sum(item.seller_earning for item in order.items.all())
    assert balance(photographer.user) == earnings
    assert (
        WalletTransaction.objects.filter(
            wallet__user=photographer.user, txn_type="EARNING"
        ).count()
        == 1
    )


def test_checkout_snapshots_the_price(funded_buyer, product):
    add_to_cart(funded_buyer, product)
    order = checkout(funded_buyer)

    product.price = Decimal("9999.00")
    product.save(update_fields=["price"])

    item = order.items.first()
    item.refresh_from_db()
    assert item.price == Decimal("3500.00")
    assert item.product_title == "Warm Desi Wedding Presets"


def test_checkout_empties_the_cart(funded_buyer, product):
    add_to_cart(funded_buyer, product)
    checkout(funded_buyer)
    assert CartItem.objects.filter(user=funded_buyer).count() == 0


def test_checkout_bumps_product_metrics(funded_buyer, product):
    add_to_cart(funded_buyer, product)
    checkout(funded_buyer)
    product.refresh_from_db()

    assert product.sales_count == 1
    assert product.total_revenue == product.price


def test_checkout_notifies_the_seller(funded_buyer, product, photographer):
    from apps.notifications.models import Notification

    add_to_cart(funded_buyer, product)
    checkout(funded_buyer)

    assert Notification.objects.filter(
        recipient=photographer.user, notification_type="PRODUCT_SOLD"
    ).exists()


# ═══════════════════════════════════════════════════════════════════════════
# CHECKOUT — FAILURE PATHS
# Each asserts that NOTHING moved: no order, no charge, no grant.
# ═══════════════════════════════════════════════════════════════════════════
def test_empty_cart_is_refused(funded_buyer):
    with pytest.raises(BusinessRuleViolation, match="cart is empty"):
        checkout(funded_buyer)
    assert Order.objects.count() == 0


def test_insufficient_balance_leaves_nothing_behind(buyer, product):
    """
    The buyer has Rs 0. The order row is created before the debit, so this is
    the test that proves the rollback actually rolls the order back too.
    """
    from apps.core.exceptions import InsufficientBalance

    add_to_cart(buyer, product)

    with pytest.raises(InsufficientBalance):
        checkout(buyer)

    assert Order.objects.count() == 0
    assert OrderItem.objects.count() == 0
    assert balance(buyer) == Decimal("0.00")
    # The cart survives, so the buyer can top up and try again.
    assert CartItem.objects.filter(user=buyer).count() == 1


def test_a_delisted_product_blocks_checkout_without_charging(funded_buyer, product):
    add_to_cart(funded_buyer, product)
    before = balance(funded_buyer)

    product.is_published = False
    product.save(update_fields=["is_published"])

    with pytest.raises(ResourceGone, match="no longer on sale"):
        checkout(funded_buyer)

    assert balance(funded_buyer) == before
    assert Order.objects.count() == 0


def test_already_owned_item_in_cart_blocks_checkout(funded_buyer, product, second_product):
    add_to_cart(funded_buyer, product)
    checkout(funded_buyer)

    # Force it back into the cart the way a stale client would.
    CartItem.objects.create(user=funded_buyer, product=product)
    add_to_cart(funded_buyer, second_product)
    before = balance(funded_buyer)

    with pytest.raises(BusinessRuleViolation, match="already own"):
        checkout(funded_buyer)

    assert balance(funded_buyer) == before
    assert Order.objects.filter(status=OrderStatus.PAID).count() == 1


def test_the_wallet_can_never_go_negative(buyer, product):
    """`ck_wallet_no_overdraft` backs the application check."""
    from apps.profiles.models import WalletTransactionType
    from apps.profiles.services import credit_wallet

    credit_wallet(
        buyer, Decimal("100.00"), txn_type=WalletTransactionType.TOPUP
    )
    add_to_cart(buyer, product)

    from apps.core.exceptions import InsufficientBalance

    with pytest.raises(InsufficientBalance):
        checkout(buyer)

    assert balance(buyer) == Decimal("100.00")


# ═══════════════════════════════════════════════════════════════════════════
# IDEMPOTENCY
# ═══════════════════════════════════════════════════════════════════════════
def test_the_same_key_returns_the_same_order(funded_buyer, product):
    add_to_cart(funded_buyer, product)
    first = checkout(funded_buyer, idempotency_key="tap-1")
    second = checkout(funded_buyer, idempotency_key="tap-1")

    assert first.pk == second.pk
    assert Order.objects.count() == 1


def test_a_double_tap_charges_once(funded_buyer, product):
    before = balance(funded_buyer)
    add_to_cart(funded_buyer, product)

    checkout(funded_buyer, idempotency_key="tap-1")
    checkout(funded_buyer, idempotency_key="tap-1")

    assert balance(funded_buyer) == before - product.price


def test_a_different_key_is_a_different_purchase(funded_buyer, product, second_product):
    add_to_cart(funded_buyer, product)
    first = checkout(funded_buyer, idempotency_key="tap-1")

    add_to_cart(funded_buyer, second_product)
    second = checkout(funded_buyer, idempotency_key="tap-2")

    assert first.pk != second.pk
    assert Order.objects.count() == 2
