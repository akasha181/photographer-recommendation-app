"""Read-side queries for the catalogue. No writes happen in this module."""

from django.db.models import QuerySet

from apps.catalog.models import Category, Service, Specialization


def get_active_categories() -> QuerySet[Category]:
    """The five canonical categories, ordered for display."""
    return Category.objects.filter(is_active=True).order_by("display_order", "name")


def get_specializations(category_slug: str | None = None) -> QuerySet[Specialization]:
    qs = Specialization.objects.filter(is_active=True).select_related("category")
    if category_slug:
        qs = qs.filter(category__slug=category_slug)
    return qs.order_by("name")


def get_own_services(photographer) -> QuerySet[Service]:
    """
    A photographer's own catalogue, **including archived listings**.

    Deliberately not built on `get_photographer_services` — that one hides
    inactive rows because it feeds public discovery. The owner needs to see
    what they archived in order to restore it.
    """
    return (
        Service.objects.filter(photographer=photographer, is_deleted=False)
        .select_related("category")
        .prefetch_related("packages")
        .order_by("-is_active", "display_order", "price")
    )


def get_own_service(photographer, service_id: int) -> Service | None:
    """Scoped to the owner — someone else's listing is a 404, not a 403."""
    return get_own_services(photographer).filter(pk=service_id).first()


def get_photographer_services(photographer_id: int) -> QuerySet[Service]:
    """
    Active services for one photographer.

    `prefetch_related("packages")` matters: without it, serializing 3 services
    with tiers fires one extra query per service. With 200 photographers on a
    list screen that is the difference between 2 queries and 600.
    """
    return (
        Service.objects.filter(
            photographer_id=photographer_id, is_active=True, is_deleted=False
        )
        .select_related("category")
        .prefetch_related("packages")
        .order_by("display_order", "price")
    )
