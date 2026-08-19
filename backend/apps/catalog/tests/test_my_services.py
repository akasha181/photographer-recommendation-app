"""
Module 5 — a photographer managing what they sell.

The property that matters most: editing a price must never rewrite a booking
that already exists. Everything else here is scoping and quotas.
"""

from decimal import Decimal

import pytest

from apps.catalog.models import Service
from apps.catalog.services import (
    archive_service,
    create_service,
    delete_service,
    update_service,
)
from apps.core.exceptions import BusinessRuleViolation

pytestmark = pytest.mark.django_db

URL = "/api/v1/catalog/my-services/"


def payload(**overrides):
    return {
        "title": "Half-Day Portrait Session",
        "description": "Two hours, 30 edited photos.",
        "price": "18000.00",
        "pricing_unit": "FIXED",
        "duration_hours": 2,
        "min_hours": 1,
        "edited_photos_count": 30,
        "delivery_days": 7,
        "includes": ["30 edited photos", "Online gallery"],
        **overrides,
    }


# ═══════════════════════════════════════════════════════════════════════════
# SERVICE LIFECYCLE
# ═══════════════════════════════════════════════════════════════════════════
def test_create_over_http(photographer_client, photographer, category):
    response = photographer_client.post(
        URL, payload(category=category.pk), format="json"
    )

    assert response.status_code == 201
    body = response.json()["data"]
    assert body["title"] == "Half-Day Portrait Session"
    assert body["is_active"] is True
    assert body["can_delete"] is True


def test_base_price_follows_the_cheapest_service(
    photographer_client, photographer, category, service
):
    """
    `base_price` is the "from Rs X" on every search card, and search filters on
    it. If it did not follow the catalogue, a photographer could add a cheap
    service and still be filtered out of a budget search that now matches them.
    """
    assert photographer.base_price == Decimal("50000.00")

    photographer_client.post(
        URL, payload(category=category.pk, price="12000.00"), format="json"
    )
    photographer.refresh_from_db()

    assert photographer.base_price == Decimal("12000.00")


def test_editing_a_price_does_not_rewrite_a_booking(booking, service):
    """The whole reason editing is safe to allow at all."""
    update_service(service, price=Decimal("999999.00"))
    booking.refresh_from_db()

    assert booking.unit_price == Decimal("85000.00")
    assert booking.total_price == Decimal("85000.00")


def test_archive_hides_from_discovery_but_keeps_history(
    photographer_client, service, booking
):
    response = photographer_client.post(f"{URL}{service.pk}/archive/", {}, format="json")

    assert response.status_code == 200
    assert response.json()["data"]["is_active"] is False
    # The booking still points at a real row.
    booking.refresh_from_db()
    assert booking.service_id == service.pk


def test_archived_services_disappear_from_the_public_list(
    api_client, photographer, service
):
    archive_service(service)
    body = api_client.get(f"/api/v1/profiles/photographers/{photographer.pk}/").json()
    assert body["data"]["services"] == []


def test_the_owner_still_sees_archived_services(photographer_client, service):
    archive_service(service)
    rows = photographer_client.get(URL).json()["data"]

    assert [r["id"] for r in rows] == [service.pk]
    assert rows[0]["is_active"] is False


def test_restore_puts_it_back(photographer_client, service):
    archive_service(service)
    response = photographer_client.post(f"{URL}{service.pk}/restore/", {}, format="json")
    assert response.json()["data"]["is_active"] is True


def test_a_booked_service_cannot_be_deleted(service, booking):
    """PROTECT would raise anyway; the guard turns it into a usable sentence."""
    with pytest.raises(BusinessRuleViolation, match="Archive it instead"):
        delete_service(service)

    assert Service.objects.filter(pk=service.pk).exists()


def test_an_unbooked_service_can_be_deleted(photographer_client, service):
    response = photographer_client.delete(f"{URL}{service.pk}/")

    assert response.status_code == 204
    assert not Service.objects.filter(pk=service.pk).exists()


def test_delete_over_http_reports_why_it_is_refused(
    photographer_client, service, booking
):
    response = photographer_client.delete(f"{URL}{service.pk}/")

    assert response.status_code == 400
    assert "Archive it instead" in response.json()["message"]


def test_the_service_cap(photographer, category, settings):
    from apps.catalog import services as catalog_services

    settings.__dict__  # touch, keeps the fixture honest about intent
    for index in range(catalog_services.MAX_SERVICES_PER_PHOTOGRAPHER):
        create_service(
            photographer,
            title=f"Service {index}",
            category=category,
            price=Decimal("1000.00"),
        )

    with pytest.raises(BusinessRuleViolation, match="Archive one"):
        create_service(
            photographer, title="One too many", category=category,
            price=Decimal("1000.00"),
        )


# ═══════════════════════════════════════════════════════════════════════════
# SCOPING — the security property
# ═══════════════════════════════════════════════════════════════════════════
def test_a_photographer_cannot_touch_another_catalogue(
    photographer_client, other_photographer_service
):
    """Someone else's listing is a 404, not a 403 — its existence is not leaked."""
    pk = other_photographer_service.pk

    assert photographer_client.get(f"{URL}{pk}/").status_code == 404
    assert photographer_client.patch(f"{URL}{pk}/", {"price": "1.00"}, format="json").status_code == 404
    assert photographer_client.delete(f"{URL}{pk}/").status_code == 404
    assert photographer_client.post(f"{URL}{pk}/archive/", {}, format="json").status_code == 404


def test_the_body_cannot_reassign_a_service(photographer_client, category, other_photographer):
    """`photographer` is not a writable field — it comes from the token."""
    response = photographer_client.post(
        URL,
        payload(category=category.pk, photographer=other_photographer.pk),
        format="json",
    )
    service = Service.objects.get(pk=response.json()["data"]["id"])

    assert response.status_code == 201
    assert service.photographer_id != other_photographer.pk


def test_a_buyer_has_no_catalogue(buyer_client):
    assert buyer_client.get(URL).status_code == 403


def test_anonymous_is_refused(api_client):
    assert api_client.get(URL).status_code == 401


# ═══════════════════════════════════════════════════════════════════════════
# VALIDATION
# ═══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize(
    "field,value,fragment",
    [
        ("price", "0.00", "above zero"),
        ("title", "Hi", "descriptive title"),
        ("min_hours", 9, "cannot exceed"),
    ],
)
def test_validation(photographer_client, category, field, value, fragment):
    response = photographer_client.post(
        URL, payload(category=category.pk, **{field: value}), format="json"
    )

    assert response.status_code == 400
    assert fragment in response.json()["message"]


def test_includes_is_coerced_to_a_clean_list(photographer_client, category):
    response = photographer_client.post(
        URL,
        payload(category=category.pk, includes=["  Drone shots  ", "", "2 shooters"]),
        format="json",
    )
    assert response.json()["data"]["includes"] == ["Drone shots", "2 shooters"]


# ═══════════════════════════════════════════════════════════════════════════
# PACKAGES (tiers)
# ═══════════════════════════════════════════════════════════════════════════
def test_add_and_edit_a_tier(photographer_client, service):
    created = photographer_client.post(
        f"{URL}{service.pk}/packages/",
        {"name": "Platinum", "price": "120000.00", "duration_hours": 10},
        format="json",
    )
    assert created.status_code == 201
    package_id = created.json()["data"]["id"]

    edited = photographer_client.patch(
        f"{URL}{service.pk}/packages/{package_id}/",
        {"price": "130000.00"},
        format="json",
    )
    assert edited.json()["data"]["price"] == "130000.00"


def test_duplicate_tier_names_are_refused(photographer_client, service):
    body = {"name": "Gold", "price": "50000.00"}
    photographer_client.post(f"{URL}{service.pk}/packages/", body, format="json")
    again = photographer_client.post(f"{URL}{service.pk}/packages/", body, format="json")

    assert again.status_code == 400
    assert "already have a tier" in again.json()["message"]


def test_removing_a_tier_keeps_the_booking(photographer_client, service, package, buyer):
    """`Booking.package` is SET_NULL — the snapshotted price survives."""
    from datetime import time

    from apps.bookings.services import create_booking
    from conftest import working_date

    booking = create_booking(
        buyer=buyer,
        service=service,
        package=package,
        event_date=working_date(9),
        start_time=time(10, 0),
        location_address="F-7",
        location_city="Islamabad",
    )

    response = photographer_client.delete(
        f"{URL}{service.pk}/packages/{package.pk}/remove/"
    )
    booking.refresh_from_db()

    assert response.status_code == 204
    assert booking.package_id is None
    assert booking.unit_price == Decimal("120000.00")


def test_a_tier_on_someone_elses_service_is_404(
    photographer_client, other_photographer_service
):
    response = photographer_client.post(
        f"{URL}{other_photographer_service.pk}/packages/",
        {"name": "Gold", "price": "1.00"},
        format="json",
    )
    assert response.status_code == 404
