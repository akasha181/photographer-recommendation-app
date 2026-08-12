"""
Read-side queries for the marketplace.

THE ONE RULE THIS MODULE ENFORCES
---------------------------------
`purchasable_products()` is the only entry point for anything a buyer can see
or buy, and every other product selector builds on it. Four conditions have to
hold — published, admin-approved, not deleted, and the seller still publicly
visible — and centralising them means a suspended photographer's catalogue
cannot leak through one endpoint because someone forgot a filter.

The seller check matters more here than it looks: a blocked photographer's
products would otherwise stay on sale, take buyers' money, and credit a wallet
belonging to an account the platform has disabled.
"""

from __future__ import annotations

from decimal import Decimal

from django.db.models import Count, Prefetch, Q, QuerySet, Sum

from apps.marketplace.models import (
    CartItem,
    DigitalProduct,
    DownloadToken,
    Order,
    OrderItem,
    OrderStatus,
    ProductFile,
)


# ═══════════════════════════════════════════════════════════════════════════
# PRODUCTS
# ═══════════════════════════════════════════════════════════════════════════
def purchasable_products() -> QuerySet[DigitalProduct]:
    """Everything a buyer is allowed to see and buy."""
    return DigitalProduct.objects.filter(
        is_published=True,
        is_approved=True,
        is_deleted=False,
        seller__is_approved=True,
        seller__is_deleted=False,
        seller__user__is_active=True,
        seller__user__is_blocked=False,
    ).select_related("seller", "seller__user", "category")


def products_for_list() -> QuerySet[DigitalProduct]:
    return purchasable_products()


def product_detail(slug: str) -> DigitalProduct | None:
    """
    One product, with its file manifest pre-joined.

    The file *names and sizes* are public — a buyer deciding whether to spend
    Rs 5,700 needs to know they get 42 presets and not one. The bytes are not:
    `ProductFile.file` lives on private storage and has no reachable URL.
    """
    return (
        purchasable_products()
        .prefetch_related(
            Prefetch(
                "files",
                queryset=ProductFile.objects.order_by("display_order").only(
                    "id", "product_id", "name", "file_size_mb", "display_order"
                ),
            )
        )
        .filter(slug=slug)
        .first()
    )


def featured_products(limit: int = 10):
    return purchasable_products().filter(is_featured=True).order_by("-sales_count")[:limit]


def bestsellers(limit: int = 10):
    return purchasable_products().order_by("-sales_count", "-avg_rating")[:limit]


def products_by_seller(photographer) -> QuerySet[DigitalProduct]:
    """A photographer's own catalogue — including unpublished drafts."""
    return (
        DigitalProduct.objects.filter(seller=photographer, is_deleted=False)
        .select_related("category")
        .order_by("-created_at")
    )


def filter_options() -> dict:
    """
    Real values for the Shop filter sheet.

    Hard-coding a price slider is wrong the moment a seller prices outside it,
    and listing every ProductType shows the buyer eight filters that return
    nothing. Both come from the data.
    """
    from django.db.models import Max, Min

    base = purchasable_products()
    price = base.aggregate(min=Min("price"), max=Max("price"))
    types = (
        base.values("product_type")
        .annotate(count=Count("id"))
        .filter(count__gt=0)
        .order_by("-count")
    )
    return {
        "types": [
            {
                "value": row["product_type"],
                "label": _TYPE_LABELS.get(row["product_type"], row["product_type"]),
                "count": row["count"],
            }
            for row in types
        ],
        "price_range": {
            "min": float(price["min"] or 0),
            "max": float(price["max"] or 0),
        },
        "sort_options": [
            {"value": "-popularity", "label": "Best selling"},
            {"value": "price", "label": "Price: low to high"},
            {"value": "-price", "label": "Price: high to low"},
            {"value": "-rating", "label": "Highest rated"},
            {"value": "-newest", "label": "Newest"},
        ],
    }


_TYPE_LABELS = {value: label for value, label in DigitalProduct._meta.get_field(
    "product_type"
).choices}


# ═══════════════════════════════════════════════════════════════════════════
# OWNERSHIP
# ═══════════════════════════════════════════════════════════════════════════
def owned_product_ids(user) -> set[int]:
    """
    Products this user has already paid for.

    Loaded once per request and handed to the serializer through context. The
    alternative — checking ownership per row — fires one query per card, and
    the Shop grid shows twenty at a time.
    """
    if not user or not user.is_authenticated:
        return set()
    return set(
        OrderItem.objects.filter(
            order__buyer=user, order__status=OrderStatus.PAID
        ).values_list("product_id", flat=True)
    )


def owns_product(user, product) -> bool:
    return OrderItem.objects.filter(
        order__buyer=user, order__status=OrderStatus.PAID, product=product
    ).exists()


# ═══════════════════════════════════════════════════════════════════════════
# CART
# ═══════════════════════════════════════════════════════════════════════════
def get_cart(user) -> QuerySet[CartItem]:
    return (
        CartItem.objects.filter(user=user)
        .select_related("product", "product__seller", "product__seller__user")
        .order_by("-created_at")
    )


def cart_summary(user) -> dict:
    """
    Everything the cart screen renders, including why a line is unbuyable.

    A product can be delisted, or already owned, between adding it and opening
    the cart. Reporting that per line — rather than failing the whole checkout
    with one opaque error — lets the buyer remove the offending item and carry
    on with the rest.
    """
    items = list(get_cart(user))
    owned = owned_product_ids(user)

    payable = Decimal("0.00")
    blocked = 0
    for item in items:
        item.is_owned = item.product_id in owned
        item.is_available = item.product.is_purchasable and not item.is_owned
        if item.is_available:
            payable += item.product.price
        else:
            blocked += 1

    return {
        "items": items,
        "count": len(items),
        "subtotal": payable,
        "total": payable,
        "unavailable_count": blocked,
        "wallet_balance": wallet_balance(user),
    }


def wallet_balance(user) -> Decimal:
    """Delegates to profiles — the wallet is that app's table, not this one's."""
    from apps.profiles.selectors import wallet_balance as balance

    return balance(user)


# ═══════════════════════════════════════════════════════════════════════════
# ORDERS & LIBRARY
# ═══════════════════════════════════════════════════════════════════════════
def get_orders(user) -> QuerySet[Order]:
    return (
        Order.objects.filter(buyer=user)
        .prefetch_related("items", "items__product")
        .order_by("-created_at")
    )


def get_order(user, order_id: int) -> Order | None:
    """Scoped to the caller — someone else's receipt is a 404, not a 403."""
    return (
        Order.objects.filter(buyer=user, pk=order_id)
        .prefetch_related(
            Prefetch(
                "items",
                queryset=OrderItem.objects.select_related(
                    "product", "seller", "seller__user"
                ),
            )
        )
        .first()
    )


def get_purchases(user) -> QuerySet[OrderItem]:
    """
    The buyer's library: every paid item, newest first.

    Keyed off OrderItem rather than Order because a download belongs to one
    product, and the library is browsed by product, not by receipt.
    """
    return (
        OrderItem.objects.filter(order__buyer=user, order__status=OrderStatus.PAID)
        .select_related("order", "product", "product__category", "seller", "seller__user")
        .prefetch_related("product__files")
        .order_by("-order__created_at")
    )


def get_purchase(user, item_id: int) -> OrderItem | None:
    return (
        OrderItem.objects.filter(
            pk=item_id, order__buyer=user, order__status=OrderStatus.PAID
        )
        .select_related("order", "product")
        .prefetch_related("product__files")
        .first()
    )


def find_download_token(token: str) -> DownloadToken | None:
    return (
        DownloadToken.objects.filter(token=token)
        .select_related("order_item", "product_file", "user")
        .first()
    )


# ═══════════════════════════════════════════════════════════════════════════
# SELLER
# ═══════════════════════════════════════════════════════════════════════════
def seller_sales_summary(photographer) -> dict:
    """Headline numbers for the photographer's own products view."""
    agg = OrderItem.objects.filter(
        seller=photographer, order__status=OrderStatus.PAID
    ).aggregate(
        sales=Count("id"),
        revenue=Sum("price"),
        earnings=Sum("seller_earning"),
    )
    products = DigitalProduct.objects.filter(seller=photographer, is_deleted=False)
    return {
        "products_total": products.count(),
        "products_live": products.filter(is_published=True, is_approved=True).count(),
        "sales_count": agg["sales"] or 0,
        "gross_revenue": agg["revenue"] or Decimal("0.00"),
        "net_earnings": agg["earnings"] or Decimal("0.00"),
    }


def seller_recent_sales(photographer, limit: int = 10) -> QuerySet[OrderItem]:
    return (
        OrderItem.objects.filter(seller=photographer, order__status=OrderStatus.PAID)
        .select_related("order", "order__buyer", "product")
        .order_by("-created_at")[:limit]
    )
