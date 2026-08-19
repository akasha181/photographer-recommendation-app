"""
Read-side queries for photographer discovery.

THE ONE RULE THIS MODULE ENFORCES
---------------------------------
`visible_photographers()` is the only entry point for public listings, and
every other selector builds on it. Centralising the visibility predicate means
a suspended photographer cannot leak through one endpoint because someone
forgot a filter — there is exactly one place to get it right.
"""

from __future__ import annotations

from decimal import Decimal

from django.db.models import Count, Prefetch, Q, QuerySet

from apps.core.utils import bounding_box, haversine_km
from apps.profiles.models import PhotographerProfile, Wallet


def visible_photographers() -> QuerySet[PhotographerProfile]:
    """
    Photographers a buyer is allowed to see.

    Four conditions, all required:
      · approved by an admin
      · profile not soft-deleted
      · the underlying account is active
      · the account is not blocked
    """
    return (
        PhotographerProfile.objects.filter(
            is_approved=True,
            is_deleted=False,
            user__is_active=True,
            user__is_blocked=False,
        )
        .select_related("user")
        .prefetch_related("categories", "specializations")
    )


def photographers_for_list() -> QuerySet[PhotographerProfile]:
    """
    List queryset with everything the card renders, pre-joined.

    `annotate(service_count=...)` replaces a COUNT query per row. Combined
    with the select_related/prefetch above, a 20-row page costs 3 queries
    instead of 61.
    """
    return visible_photographers().annotate(
        service_count=Count("services", filter=Q(services__is_active=True), distinct=True)
    )


def photographer_detail(photographer_id: int) -> PhotographerProfile | None:
    """
    Full profile with services, packages, featured portfolio and recent reviews.

    Everything the detail screen needs arrives in one round trip. The mobile
    client should never have to fire four requests to paint one screen.
    """
    from apps.catalog.models import Service
    from apps.portfolio.models import PortfolioImage
    from apps.reviews.models import Review

    return (
        visible_photographers()
        .prefetch_related(
            Prefetch(
                "services",
                queryset=Service.objects.filter(is_active=True, is_deleted=False)
                .select_related("category")
                .prefetch_related("packages")
                .order_by("display_order", "price"),
            ),
            Prefetch(
                "portfolio_images",
                queryset=PortfolioImage.objects.filter(is_deleted=False).order_by(
                    "-is_featured", "display_order", "-created_at"
                )[:12],
                to_attr="preview_images",
            ),
            Prefetch(
                "reviews",
                queryset=Review.objects.visible()
                .select_related("buyer")
                .prefetch_related("images", "reply")
                .order_by("-created_at")[:5],
                to_attr="recent_reviews",
            ),
        )
        .filter(pk=photographer_id)
        .first()
    )


def wallet_balance(user) -> Decimal:
    """
    The authoritative balance — read from the database, never from `user.wallet`.

    Django caches a reverse one-to-one on the instance as soon as it is
    touched (creating `Wallet(user=user)` is enough), and `credit_wallet` /
    `debit_wallet` update a *different* Wallet instance fetched under
    `select_for_update`. So `user.wallet.balance` can report the balance as it
    was before the transaction that just changed it — which is exactly the
    number a cart summary or a checkout response must not show.
    """
    if not user or not getattr(user, "is_authenticated", False):
        return Decimal("0.00")
    balance = (
        Wallet.objects.filter(user=user).values_list("balance", flat=True).first()
    )
    return balance if balance is not None else Decimal("0.00")


def photographer_self(user) -> PhotographerProfile | None:
    """
    A photographer's own profile, for their Profile tab.

    Deliberately does NOT go through `visible_photographers()`: someone still
    awaiting approval must be able to see and edit their own listing. Hiding
    it from them would mean the only way to fix an incomplete profile is to
    already have an approved one.
    """
    from apps.catalog.models import Service
    from apps.portfolio.models import PortfolioImage

    return (
        PhotographerProfile.objects.filter(user=user)
        .select_related("user")
        .prefetch_related(
            "categories",
            "specializations",
            Prefetch(
                "services",
                queryset=Service.objects.filter(is_deleted=False)
                .select_related("category")
                .prefetch_related("packages")
                .order_by("display_order", "price"),
            ),
            Prefetch(
                "portfolio_images",
                queryset=PortfolioImage.objects.filter(is_deleted=False).order_by(
                    "-is_featured", "display_order"
                )[:12],
                to_attr="preview_images",
            ),
        )
        .first()
    )


def featured_photographers(limit: int = 10) -> QuerySet[PhotographerProfile]:
    """Editorially featured, best-rated first."""
    return photographers_for_list().filter(is_featured=True).order_by(
        "-avg_rating", "-reviews_count", "-completed_bookings"
    )[:limit]


def trending_photographers(city: str | None = None, limit: int = 10):
    """
    "Trending near you".
    """
    qs = photographers_for_list().filter(is_accepting_bookings=True)
    if city:
        qs = qs.filter(user__city__iexact=city)
    return qs.order_by("-avg_rating", "-completed_bookings", "-reviews_count")[:limit]


def photographers_by_category(slug: str, limit: int | None = None):
    qs = photographers_for_list().filter(categories__slug=slug).order_by(
        "-avg_rating", "-reviews_count", "-completed_bookings"
    )
    return qs[:limit] if limit else qs


def annotate_distance(photographers, lat: float, lng: float) -> list:
    """
    Attach `distance_km` to each row, computed in Python.

    WHY NOT IN SQL
    --------------
    MySQL cannot use a B-tree index for a trigonometric distance expression,
    so `ORDER BY haversine(...)` degrades into a full scan plus a sort. The
    filter step narrows candidates with an indexed bounding box first (see
    `filter_by_radius`), and the exact distance is then computed on the
    handful of rows that survive — where the cost is trivial.
    """
    out = []
    for p in photographers:
        if p.user.latitude is None or p.user.longitude is None:
            p.distance_km = None
        else:
            p.distance_km = round(
                haversine_km(lat, lng, float(p.user.latitude), float(p.user.longitude)),
                1,
            )
        out.append(p)
    return out


def filter_by_radius(qs: QuerySet, lat: float, lng: float, radius_km: float):
    """Indexed bounding-box pre-filter — the cheap half of a distance query."""
    min_lat, max_lat, min_lng, max_lng = bounding_box(lat, lng, radius_km)
    return qs.filter(
        user__latitude__gte=Decimal(str(min_lat)),
        user__latitude__lte=Decimal(str(max_lat)),
        user__longitude__gte=Decimal(str(min_lng)),
        user__longitude__lte=Decimal(str(max_lng)),
    )
