"""
Taxonomy and service offerings.

CATEGORY vs SPECIALIZATION — why both exist
-------------------------------------------
`Category` is the closed, five-value taxonomy that every dataset in
ml/data/raw agrees on (Wedding, Corporate, Fashion, Birthday, Graduation).
It is what the recommendation models are trained on, so it must not grow
casually — adding a sixth category means retraining.

`Specialization` is the open, free-form tag list (Portrait, Newborn, Drone,
Architecture, …). It exists so photographers can describe themselves richly
without polluting the ML feature space. It is display and search only.

Keeping these separate is what lets the catalogue evolve without invalidating
the models.
"""

from decimal import Decimal

from django.db import models
from django.utils.text import slugify

from apps.core.models import BaseModel, TimeStampedModel
from apps.core.utils import upload_to


class Category(TimeStampedModel):
    name = models.CharField(max_length=60, unique=True)
    slug = models.SlugField(max_length=70, unique=True, db_index=True)
    description = models.TextField(blank=True)
    icon = models.CharField(
        max_length=40, blank=True, help_text="Icon name used by the mobile app."
    )
    image = models.ImageField(upload_to=upload_to("categories"), null=True, blank=True)

    display_order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True, db_index=True)

    # Denormalised so category tiles can show counts without a COUNT() per tile.
    photographer_count = models.PositiveIntegerField(default=0)
    booking_count = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "categories"
        verbose_name_plural = "Categories"
        ordering = ("display_order", "name")

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class Specialization(TimeStampedModel):
    name = models.CharField(max_length=60, unique=True)
    slug = models.SlugField(max_length=70, unique=True)
    category = models.ForeignKey(
        Category, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="specializations",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "specializations"
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class PricingUnit(models.TextChoices):
    FIXED = "FIXED", "Fixed package price"
    PER_HOUR = "PER_HOUR", "Per hour"
    PER_DAY = "PER_DAY", "Per day"
    PER_EVENT = "PER_EVENT", "Per event"


class Service(BaseModel):
    """
    A concrete, bookable offering — "Full-Day Wedding Coverage, Rs 85,000".

    A photographer has many services; a booking always points at exactly one.
    Bookings snapshot the price at creation time (see bookings/models.py), so
    editing a service here never rewrites the history of past bookings.
    """

    photographer = models.ForeignKey(
        "profiles.PhotographerProfile", on_delete=models.CASCADE,
        related_name="services",
    )
    category = models.ForeignKey(
        Category, on_delete=models.PROTECT, related_name="services",
        help_text="PROTECT: a category with live services cannot be deleted.",
    )

    title = models.CharField(max_length=140)
    description = models.TextField(max_length=3000, blank=True)
    cover_image = models.ImageField(
        upload_to=upload_to("services"), null=True, blank=True
    )

    # ─── Pricing ─────────────────────────────────────────────────────────────
    price = models.DecimalField(max_digits=12, decimal_places=2, db_index=True)
    pricing_unit = models.CharField(
        max_length=16, choices=PricingUnit.choices, default=PricingUnit.FIXED
    )
    min_hours = models.PositiveSmallIntegerField(default=1)

    # ─── Deliverables ────────────────────────────────────────────────────────
    duration_hours = models.PositiveSmallIntegerField(default=4)
    edited_photos_count = models.PositiveIntegerField(default=0)
    raw_photos_included = models.BooleanField(default=False)
    delivery_days = models.PositiveSmallIntegerField(default=14)
    includes = models.JSONField(
        default=list, blank=True,
        help_text='List of bullet points, e.g. ["2 photographers", "Drone shots"]',
    )

    # ─── Booking rules ───────────────────────────────────────────────────────
    advance_payment_percent = models.PositiveSmallIntegerField(default=30)
    max_travel_km = models.PositiveSmallIntegerField(default=50)

    is_active = models.BooleanField(default=True, db_index=True)
    display_order = models.PositiveSmallIntegerField(default=0)

    # ─── Denormalised counters ───────────────────────────────────────────────
    booking_count = models.PositiveIntegerField(default=0)
    view_count = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "services"
        ordering = ("display_order", "price")
        indexes = [
            models.Index(
                fields=["photographer", "is_active"], name="idx_service_by_photog"
            ),
            models.Index(
                fields=["category", "is_active", "price"], name="idx_service_browse"
            ),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(price__gte=0), name="ck_service_price_positive"
            ),
            models.CheckConstraint(
                check=models.Q(advance_payment_percent__lte=100),
                name="ck_service_advance_percent",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.title} — Rs {self.price}"


class ServicePackage(TimeStampedModel):
    """
    Optional tiered variants of a service (Silver / Gold / Platinum).

    Modelled as a child table rather than three price columns so photographers
    can offer any number of tiers, and so a booking can reference the exact
    tier the buyer chose.
    """

    service = models.ForeignKey(
        Service, on_delete=models.CASCADE, related_name="packages"
    )
    name = models.CharField(max_length=80)
    price = models.DecimalField(max_digits=12, decimal_places=2)
    description = models.TextField(blank=True, max_length=1000)
    features = models.JSONField(default=list, blank=True)
    duration_hours = models.PositiveSmallIntegerField(default=4)
    edited_photos_count = models.PositiveIntegerField(default=0)
    is_popular = models.BooleanField(default=False)
    display_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = "service_packages"
        ordering = ("display_order", "price")
        constraints = [
            models.UniqueConstraint(
                fields=["service", "name"], name="uniq_package_name_per_service"
            ),
            models.CheckConstraint(
                check=models.Q(price__gte=Decimal("0")), name="ck_package_price_positive"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.service.title} — {self.name}"
