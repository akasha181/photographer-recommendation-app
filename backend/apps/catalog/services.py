"""
Catalogue writes — a photographer managing what they sell.

WHY DEACTIVATING BEATS DELETING
-------------------------------
`Booking.service` is `on_delete=PROTECT` and every booking snapshots the
price, so a service with history cannot be removed without either destroying
that history or orphaning the foreign key. `archive_service` flips
`is_active` instead: the listing disappears from discovery immediately, past
bookings keep pointing at a real row, and the photographer can bring it back.

A service that has never been booked is genuinely deleted, because keeping a
typo'd draft forever helps nobody.
"""

import logging

from django.db import transaction

from apps.catalog.models import Service, ServicePackage
from apps.core.exceptions import BusinessRuleViolation

logger = logging.getLogger("snapsphere")

#: Above this a profile is a catalogue, not a portfolio — and the booking
#: screen's service picker becomes unusable on a phone.
MAX_SERVICES_PER_PHOTOGRAPHER = 20
MAX_PACKAGES_PER_SERVICE = 6


@transaction.atomic
def create_service(photographer, **data) -> Service:
    live = Service.objects.filter(photographer=photographer, is_deleted=False).count()
    if live >= MAX_SERVICES_PER_PHOTOGRAPHER:
        raise BusinessRuleViolation(
            f"You can list up to {MAX_SERVICES_PER_PHOTOGRAPHER} services. "
            f"Archive one you no longer offer to add another."
        )

    service = Service.objects.create(photographer=photographer, **data)
    _refresh_base_price(photographer)
    logger.info(
        "Service created",
        extra={"photographer_id": photographer.pk, "service_id": service.pk},
    )
    return service


@transaction.atomic
def update_service(service: Service, **data) -> Service:
    """
    Edit a listing.

    Changing the price here does NOT change any existing booking: the amount
    was snapshotted onto the booking at creation (see bookings/models.py), and
    that is the whole reason this edit is safe to allow at all.
    """
    for field, value in data.items():
        setattr(service, field, value)
    service.save()
    _refresh_base_price(service.photographer)
    return service


@transaction.atomic
def archive_service(service: Service) -> Service:
    """Hide from discovery, keep for history."""
    if not service.is_active:
        raise BusinessRuleViolation("This service is already archived.")

    service.is_active = False
    service.save(update_fields=["is_active", "updated_at"])
    _refresh_base_price(service.photographer)
    return service


@transaction.atomic
def restore_service(service: Service) -> Service:
    service.is_active = True
    service.save(update_fields=["is_active", "updated_at"])
    _refresh_base_price(service.photographer)
    return service


@transaction.atomic
def delete_service(service: Service) -> None:
    """
    Remove a service outright — only allowed while it has no bookings.

    The PROTECT foreign key would raise anyway; checking here turns a database
    error into a sentence explaining that archiving is the right move.
    """
    from apps.bookings.models import Booking

    if Booking.objects.filter(service=service).exists():
        raise BusinessRuleViolation(
            "This service has bookings, so it cannot be deleted. "
            "Archive it instead — your booking history stays intact."
        )

    photographer = service.photographer
    service.hard_delete()
    _refresh_base_price(photographer)


# ═══════════════════════════════════════════════════════════════════════════
# PACKAGES
# ═══════════════════════════════════════════════════════════════════════════
@transaction.atomic
def create_package(service: Service, **data) -> ServicePackage:
    if service.packages.count() >= MAX_PACKAGES_PER_SERVICE:
        raise BusinessRuleViolation(
            f"A service can have up to {MAX_PACKAGES_PER_SERVICE} tiers."
        )
    if service.packages.filter(name__iexact=data.get("name", "")).exists():
        raise BusinessRuleViolation("You already have a tier with that name.")

    return ServicePackage.objects.create(service=service, **data)


@transaction.atomic
def update_package(package: ServicePackage, **data) -> ServicePackage:
    name = data.get("name")
    if name and (
        package.service.packages.filter(name__iexact=name)
        .exclude(pk=package.pk)
        .exists()
    ):
        raise BusinessRuleViolation("You already have a tier with that name.")

    for field, value in data.items():
        setattr(package, field, value)
    package.save()
    return package


@transaction.atomic
def delete_package(package: ServicePackage) -> None:
    """
    Bookings reference packages with `SET_NULL`, so removal is safe — the
    booking keeps its snapshotted price and simply loses the tier label.
    """
    package.delete()


# ═══════════════════════════════════════════════════════════════════════════
# DENORMALISED PRICE
# ═══════════════════════════════════════════════════════════════════════════
def _refresh_base_price(photographer) -> None:
    """
    `base_price` is the "from Rs X" on every search card, and search sorts and
    filters on it. Recomputing it here — inside the same transaction as the
    edit — is what stops a photographer editing their cheapest service and
    still being filtered out of a budget search that should now match them.
    """
    from decimal import Decimal

    from django.db.models import Min

    cheapest = Service.objects.filter(
        photographer=photographer, is_active=True, is_deleted=False
    ).aggregate(low=Min("price"))["low"]

    photographer.base_price = cheapest or Decimal("0.00")
    photographer.save(update_fields=["base_price", "updated_at"])
