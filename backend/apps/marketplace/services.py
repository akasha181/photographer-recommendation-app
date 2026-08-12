"""
Marketplace write logic — Module 8.

WHY THERE IS NO PAYMENT GATEWAY HERE
------------------------------------
The proposal excludes online payments, so a purchase is a wallet debit: the
buyer tops up by bank transfer or Easypaisa, an admin verifies the receipt,
and the balance is then spendable instantly. That keeps downloads immediate —
the thing a digital product must be — without pretending to integrate a
payment processor the project never scoped.

WHAT CHECKOUT GUARANTEES
------------------------
1. MONEY AND GOODS MOVE TOGETHER. The wallet debit, the order, the items and
   every seller credit happen in ONE `transaction.atomic()`. There is no
   window in which a buyer has been charged but owns nothing, or owns
   something nobody was paid for.
2. THE WALLET CANNOT GO NEGATIVE. `debit_wallet` takes `select_for_update()`
   on the wallet row, so two devices checking out at once serialize instead of
   both reading the same balance. `ck_wallet_no_overdraft` backs it in the
   database.
3. PRICES ARE SNAPSHOTTED onto OrderItem. An order is a receipt, and a receipt
   that changes when the seller edits their listing is not a receipt.
4. RETRIES ARE SAFE. `Order.idempotency_key` is uniquely constrained per
   buyer, so a double-tap on Checkout cannot produce two orders — and cannot
   charge twice.

THE DOWNLOAD FLOW
-----------------
Files never sit at a reachable URL (see `core/storage.py`). A buyer asks for a
token, gets a single-use ticket valid for 15 minutes, and redeems it once.
Even if that URL is copied out of a proxy log it is dead on arrival.
"""

from __future__ import annotations

import logging
import secrets
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.core.exceptions import BusinessRuleViolation, ResourceGone
from apps.marketplace.models import (
    CartItem,
    DigitalProduct,
    DownloadToken,
    Order,
    OrderItem,
    OrderStatus,
    ProductFile,
)

logger = logging.getLogger("snapsphere")


# ═══════════════════════════════════════════════════════════════════════════
# CART
# ═══════════════════════════════════════════════════════════════════════════
def add_to_cart(user, product: DigitalProduct) -> CartItem:
    """
    Put a product in the basket.

    Refuses what checkout would refuse anyway — an unavailable product, your
    own listing, something you already own — because finding out at the cart
    screen is much cheaper than finding out at checkout with a full basket.
    """
    _assert_buyer(user)
    _assert_purchasable(product)

    if product.seller.user_id == user.id:
        raise BusinessRuleViolation("This is your own product.")

    from apps.marketplace.selectors import owns_product

    if owns_product(user, product):
        raise BusinessRuleViolation(
            "You already own this. Find it in Purchases to download it again."
        )

    item, created = CartItem.objects.get_or_create(user=user, product=product)
    if not created:
        # Adding twice is not an error — a digital product has no quantity, so
        # the second tap simply means "yes, it is in the cart".
        logger.debug("Cart item already present", extra={"product_id": product.pk})
    return item


def remove_from_cart(user, product_id: int) -> int:
    deleted, _ = CartItem.objects.filter(user=user, product_id=product_id).delete()
    return deleted


def clear_cart(user) -> int:
    deleted, _ = CartItem.objects.filter(user=user).delete()
    return deleted


# ═══════════════════════════════════════════════════════════════════════════
# CHECKOUT
# ═══════════════════════════════════════════════════════════════════════════
def checkout(user, *, idempotency_key: str = "") -> Order:
    """
    Turn the cart into a paid order.

    Everything below the `atomic()` either all happens or none of it does.
    """
    _assert_buyer(user)

    if idempotency_key:
        existing = Order.objects.filter(
            buyer=user, idempotency_key=idempotency_key
        ).first()
        if existing is not None:
            logger.info("Idempotent replay of order %s", existing.pk)
            return existing

    try:
        return _checkout_atomic(user, idempotency_key)
    except IntegrityError as exc:
        # Two genuinely simultaneous submits: the unique constraint caught the
        # loser. Return the winner's order rather than an error — the buyer
        # asked for one purchase and got exactly one.
        if "uniq_order_idempotency" in str(exc) and idempotency_key:
            existing = Order.objects.filter(
                buyer=user, idempotency_key=idempotency_key
            ).first()
            if existing is not None:
                return existing
        raise


@transaction.atomic
def _checkout_atomic(user, idempotency_key: str) -> Order:
    from apps.marketplace.selectors import owned_product_ids
    from apps.profiles.models import WalletTransactionType
    from apps.profiles.services import credit_wallet, debit_wallet

    items = list(
        CartItem.objects.select_for_update()
        .filter(user=user)
        .select_related("product", "product__seller", "product__seller__user")
    )
    if not items:
        raise BusinessRuleViolation("Your cart is empty.")

    owned = owned_product_ids(user)
    purchasable = []
    for item in items:
        product = item.product
        if product.pk in owned:
            raise BusinessRuleViolation(
                f'You already own "{product.title}". Remove it from your cart to continue.'
            )
        if not product.is_purchasable:
            raise ResourceGone(
                f'"{product.title}" is no longer on sale. Remove it to continue.'
            )
        purchasable.append(product)

    subtotal = sum((p.price for p in purchasable), Decimal("0.00"))

    order = Order.objects.create(
        buyer=user,
        subtotal=subtotal,
        discount=Decimal("0.00"),
        total=subtotal,
        status=OrderStatus.PENDING,
        payment_method="WALLET",
        idempotency_key=idempotency_key,
    )

    # ─── Pay first, then grant ───────────────────────────────────────────────
    # debit_wallet raises InsufficientBalance, which rolls the whole block back
    # including the order above. Creating the items before the debit would mean
    # a failed payment still left a receipt behind.
    debit_wallet(
        user,
        subtotal,
        txn_type=WalletTransactionType.PURCHASE,
        reference=order.order_number,
        description=f"{len(purchasable)} item(s) from the SnapSphere shop",
    )

    order_items = []
    for product in purchasable:
        commission = (product.price * product.commission_percent / Decimal("100")).quantize(
            Decimal("0.01")
        )
        order_items.append(
            OrderItem(
                order=order,
                product=product,
                seller=product.seller,
                product_title=product.title,
                price=product.price,
                commission_amount=commission,
                seller_earning=product.price - commission,
                max_downloads=settings.MAX_DOWNLOADS_PER_PURCHASE,
            )
        )
    OrderItem.objects.bulk_create(order_items)

    order.status = OrderStatus.PAID
    order.paid_at = timezone.now()
    order.save(update_fields=["status", "paid_at", "updated_at"])

    _credit_sellers(order_items, order, credit_wallet, WalletTransactionType)
    _bump_product_metrics(order_items)

    CartItem.objects.filter(user=user).delete()

    _notify_sellers(order_items, user)

    logger.info(
        "Order paid",
        extra={"order_id": order.pk, "buyer_id": user.id, "total": str(subtotal)},
    )
    return order


def _credit_sellers(order_items, order, credit_wallet, WalletTransactionType) -> None:
    """
    Pay each seller their share, in the same transaction as the debit.

    Earnings are aggregated per seller first: a basket with three products from
    one photographer should move their balance once, not three times, or the
    ledger reads like three separate sales.
    """
    by_seller: dict[int, tuple[object, Decimal]] = {}
    for item in order_items:
        seller_user = item.seller.user
        current = by_seller.get(seller_user.id, (seller_user, Decimal("0.00")))
        by_seller[seller_user.id] = (seller_user, current[1] + item.seller_earning)

    for seller_user, amount in by_seller.values():
        if amount <= 0:
            continue
        credit_wallet(
            seller_user,
            amount,
            txn_type=WalletTransactionType.EARNING,
            reference=order.order_number,
            description="Marketplace sale",
        )


def _bump_product_metrics(order_items) -> None:
    """F() expressions — two buyers purchasing at once must not lose a count."""
    from django.db.models import F

    from apps.profiles.models import PhotographerProfile

    for item in order_items:
        DigitalProduct.objects.filter(pk=item.product_id).update(
            sales_count=F("sales_count") + 1,
            total_revenue=F("total_revenue") + item.price,
        )
        PhotographerProfile.objects.filter(pk=item.seller_id).update(
            total_earnings=F("total_earnings") + item.seller_earning
        )


def _notify_sellers(order_items, buyer) -> None:
    from apps.notifications.services import notify

    for item in order_items:
        notify(
            item.seller.user,
            "PRODUCT_SOLD",
            title="You made a sale",
            body=f'{buyer.full_name} bought "{item.product_title}".',
            action_screen="SellerProducts",
            action_id=str(item.product_id),
            actor=buyer,
        )


# ═══════════════════════════════════════════════════════════════════════════
# DOWNLOADS
# ═══════════════════════════════════════════════════════════════════════════
@transaction.atomic
def issue_download_token(user, order_item: OrderItem, product_file: ProductFile) -> DownloadToken:
    """
    Mint a single-use, short-lived ticket for one file.

    The download counter is incremented HERE, when the ticket is issued, not
    when the bytes finish streaming. Counting on completion sounds fairer but
    is unenforceable — a client that disconnects at 99% has still received the
    file, and making the count depend on the client's honesty makes
    `max_downloads` decorative.
    """
    if order_item.order.buyer_id != user.id:
        raise BusinessRuleViolation("This purchase is not yours.")
    if order_item.order.status != OrderStatus.PAID:
        raise BusinessRuleViolation("This order has not been paid.")
    if product_file.product_id != order_item.product_id:
        raise BusinessRuleViolation("That file is not part of this purchase.")

    locked = OrderItem.objects.select_for_update().get(pk=order_item.pk)
    if locked.downloads_remaining <= 0:
        raise BusinessRuleViolation(
            f"You have used all {locked.max_downloads} downloads for this item. "
            f"Contact support if you need it again."
        )

    locked.download_count += 1
    locked.save(update_fields=["download_count", "updated_at"])

    token = DownloadToken.objects.create(
        order_item=locked,
        product_file=product_file,
        user=user,
        token=secrets.token_urlsafe(32),
        expires_at=timezone.now()
        + timedelta(minutes=settings.DOWNLOAD_TOKEN_TTL_MINUTES),
    )
    logger.info(
        "Download token issued",
        extra={"user_id": user.id, "order_item_id": locked.pk},
    )
    return token


@transaction.atomic
def redeem_download_token(token_value: str, *, ip_address: str | None = None) -> DownloadToken:
    """
    Spend a ticket. Raises rather than returning None so the view stays thin.

    The row is locked and re-read before the used_at check: without it, two
    parallel requests with the same token both see `used_at is None` and both
    get the file — which is exactly the reuse the token exists to prevent.
    """
    token = (
        DownloadToken.objects.select_for_update()
        .select_related("product_file", "order_item")
        .filter(token=token_value)
        .first()
    )
    if token is None:
        raise ResourceGone("This download link is not valid.")
    if token.used_at is not None:
        raise ResourceGone("This download link has already been used.")
    if timezone.now() >= token.expires_at:
        raise ResourceGone("This download link has expired. Request a new one.")

    token.used_at = timezone.now()
    token.ip_address = ip_address
    token.save(update_fields=["used_at", "ip_address", "updated_at"])
    return token


# ═══════════════════════════════════════════════════════════════════════════
# GUARDS
# ═══════════════════════════════════════════════════════════════════════════
def _assert_buyer(user) -> None:
    from apps.core.constants import UserRole

    if getattr(user, "role", None) not in (UserRole.BUYER, UserRole.PHOTOGRAPHER):
        raise BusinessRuleViolation("Sign in with a buyer account to purchase.")


def _assert_purchasable(product: DigitalProduct) -> None:
    if product is None or not product.is_purchasable:
        raise ResourceGone("This product is no longer available.")
