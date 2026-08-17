"""
Shared test fixtures.

Fixtures build accounts through `profiles.services` rather than by calling
`Model.objects.create()` directly. That is deliberate: a photographer created
by hand has no wallet, no notification preference and — crucially for the
booking tests — no `AvailabilityRule` rows, so tests would silently exercise
the "no rules means available" default instead of the real seeded calendar.
"""

from datetime import date, time, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.core.constants import UserRole

User = get_user_model()

PASSWORD = "TestPass123!"


# ═══════════════════════════════════════════════════════════════════════════
# DATES
# The seeded calendar has Sunday off, so a test that happens to pick a Sunday
# would fail for a reason that has nothing to do with what it is testing.
# ═══════════════════════════════════════════════════════════════════════════
def working_date(days_ahead: int = 7, *, from_date: date | None = None) -> date:
    """A date at least `days_ahead` away that is not a Sunday."""
    candidate = (from_date or date.today()) + timedelta(days=days_ahead)
    while candidate.weekday() == 6:  # Sunday
        candidate += timedelta(days=1)
    return candidate


@pytest.fixture
def event_date() -> date:
    """Comfortably past BOOKING_MIN_LEAD_HOURS and not a Sunday."""
    return working_date(7)


# ═══════════════════════════════════════════════════════════════════════════
# ACCOUNTS
# ═══════════════════════════════════════════════════════════════════════════
@pytest.fixture
def buyer(db):
    from apps.profiles.services import create_buyer_profile

    user = User.objects.create_user(
        email="buyer@test.pk",
        password=PASSWORD,
        full_name="Ayesha Khan",
        phone="03001112233",
        city="Islamabad",
        role=UserRole.BUYER,
        is_email_verified=True,
    )
    create_buyer_profile(user)
    return user


@pytest.fixture
def other_buyer(db):
    from apps.profiles.services import create_buyer_profile

    user = User.objects.create_user(
        email="buyer2@test.pk",
        password=PASSWORD,
        full_name="Bilal Ahmed",
        city="Lahore",
        role=UserRole.BUYER,
        is_email_verified=True,
    )
    create_buyer_profile(user)
    return user


@pytest.fixture
def admin_user(db):
    return User.objects.create_superuser(
        email="admin@test.pk", password=PASSWORD, full_name="Platform Admin"
    )


@pytest.fixture
def photographer(db):
    """An approved, publicly visible photographer with the default calendar."""
    from apps.profiles.services import create_photographer_profile

    user = User.objects.create_photographer(
        email="photog@test.pk",
        password=PASSWORD,
        full_name="Hamza Studio",
        phone="03004445566",
        city="Islamabad",
        is_email_verified=True,
    )
    profile = create_photographer_profile(user)
    profile.business_name = "Hamza Studio"
    profile.is_approved = True
    profile.base_price = Decimal("50000.00")
    profile.save()
    return profile


@pytest.fixture
def other_photographer(db):
    """A second photographer, for proving one cannot reach the other's data."""
    from apps.profiles.services import create_photographer_profile

    user = User.objects.create_photographer(
        email="photog2@test.pk",
        password=PASSWORD,
        full_name="Sana Films",
        city="Lahore",
        is_email_verified=True,
    )
    profile = create_photographer_profile(user)
    profile.business_name = "Sana Films"
    profile.is_approved = True
    profile.save()
    return profile


@pytest.fixture
def other_photographer_service(db, other_photographer, category):
    from apps.catalog.models import Service

    return Service.objects.create(
        photographer=other_photographer,
        category=category,
        title="Someone Else's Service",
        price=Decimal("40000.00"),
        duration_hours=4,
    )


@pytest.fixture
def category(db):
    from apps.catalog.models import Category

    return Category.objects.create(name="Wedding", slug="wedding")


@pytest.fixture
def service(db, photographer, category):
    from apps.catalog.models import PricingUnit, Service

    return Service.objects.create(
        photographer=photographer,
        category=category,
        title="Full-Day Wedding Coverage",
        price=Decimal("85000.00"),
        pricing_unit=PricingUnit.FIXED,
        duration_hours=8,
        min_hours=1,
    )


@pytest.fixture
def hourly_service(db, photographer, category):
    from apps.catalog.models import PricingUnit, Service

    return Service.objects.create(
        photographer=photographer,
        category=category,
        title="Hourly Event Coverage",
        price=Decimal("6000.00"),
        pricing_unit=PricingUnit.PER_HOUR,
        duration_hours=3,
        min_hours=2,
    )


@pytest.fixture
def package(db, service):
    from apps.catalog.models import ServicePackage

    return ServicePackage.objects.create(
        service=service,
        name="Platinum",
        price=Decimal("120000.00"),
        duration_hours=10,
    )


# ═══════════════════════════════════════════════════════════════════════════
# BOOKINGS
# ═══════════════════════════════════════════════════════════════════════════
@pytest.fixture
def booking_payload(service, event_date):
    return {
        "service": service,
        "event_date": event_date,
        "start_time": time(14, 0),
        "location_address": "F-7 Markaz, Islamabad",
        "location_city": "Islamabad",
    }


@pytest.fixture
def make_booking(buyer, booking_payload):
    """Create a real booking through the service layer, with overrides."""
    from apps.bookings.services import create_booking

    def _make(**overrides):
        payload = {**booking_payload, **overrides}
        return create_booking(buyer=payload.pop("buyer", buyer), **payload)

    return _make


@pytest.fixture
def booking(make_booking):
    return make_booking()


@pytest.fixture
def completed_booking(booking, photographer):
    """
    A booking driven all the way to COMPLETED through the real state machine.

    Built by transitioning rather than by `Booking.objects.create(status=...)`:
    reviews depend on `has_review`, the status history and the photographer's
    metrics all being consistent, and a hand-built row has none of them. The
    event date is moved into the past first because completion before the shoot
    is deliberately refused.
    """
    from apps.bookings.services import accept_booking, complete_booking

    accept_booking(booking, photographer.user)
    booking.event_date = date.today() - timedelta(days=1)
    booking.save(update_fields=["event_date"])
    return complete_booking(booking, photographer.user)


@pytest.fixture
def paid_order_item(funded_buyer, product):
    """One purchased product — the eligibility proof for a product review."""
    from apps.marketplace.services import add_to_cart, checkout

    add_to_cart(funded_buyer, product)
    order = checkout(funded_buyer)
    return order.items.first()


# ═══════════════════════════════════════════════════════════════════════════
# MARKETPLACE
# ═══════════════════════════════════════════════════════════════════════════
@pytest.fixture
def product(db, photographer, category):
    """A published, approved product with two real files on private storage."""
    from django.core.files.base import ContentFile

    from apps.marketplace.models import DigitalProduct, ProductFile, ProductType

    item = DigitalProduct.objects.create(
        seller=photographer,
        category=category,
        title="Warm Desi Wedding Presets",
        description="Twelve presets tuned for South Asian wedding lighting.",
        product_type=ProductType.LIGHTROOM_PRESET,
        price=Decimal("3500.00"),
        compare_at_price=Decimal("5000.00"),
        is_published=True,
        is_approved=True,
        file_count=2,
    )
    for index in range(2):
        product_file = ProductFile(product=item, name=f"preset-{index + 1}.xmp")
        product_file.file.save(
            f"preset-{index + 1}.xmp", ContentFile(b"sample"), save=False
        )
        product_file.save()
    return item


@pytest.fixture
def second_product(db, photographer, category):
    from apps.marketplace.models import DigitalProduct, ProductType

    return DigitalProduct.objects.create(
        seller=photographer,
        category=category,
        title="Cinematic Wedding LUT Bundle",
        product_type=ProductType.WEDDING_LUT,
        price=Decimal("2000.00"),
        is_published=True,
        is_approved=True,
    )


@pytest.fixture
def funded_buyer(buyer):
    """A buyer with Rs 50,000 credited through the real ledger."""
    from apps.profiles.models import WalletTransactionType
    from apps.profiles.services import credit_wallet

    credit_wallet(
        buyer,
        Decimal("50000.00"),
        txn_type=WalletTransactionType.TOPUP,
        description="Test opening balance",
    )
    return buyer


# ═══════════════════════════════════════════════════════════════════════════
# API CLIENTS
# ═══════════════════════════════════════════════════════════════════════════
@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def buyer_client(buyer):
    client = APIClient()
    client.force_authenticate(user=buyer)
    return client


@pytest.fixture
def photographer_client(photographer):
    client = APIClient()
    client.force_authenticate(user=photographer.user)
    return client


@pytest.fixture
def other_buyer_client(other_buyer):
    client = APIClient()
    client.force_authenticate(user=other_buyer)
    return client


@pytest.fixture
def other_photographer_client(other_photographer):
    client = APIClient()
    client.force_authenticate(user=other_photographer.user)
    return client


@pytest.fixture
def admin_client_authed(admin_user):
    """
    An authenticated ADMIN client.

    Named to avoid colliding with pytest-django's own `admin_client`, which logs
    into the Django admin with a session rather than a JWT and would silently
    fail every `IsAdmin` check here.
    """
    client = APIClient()
    client.force_authenticate(user=admin_user)
    return client
