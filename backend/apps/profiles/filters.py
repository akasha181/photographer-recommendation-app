"""
Search and filtering for photographer discovery — Module 11.

DESIGN NOTE: WHY DECLARATIVE FILTERS
------------------------------------
Every filter here could be written as `if request.query_params.get(...)` in
the view. Declaring them instead buys three things:

  1. drf-spectacular documents each one automatically in Swagger.
  2. Values are coerced and validated (a non-numeric `min_price` returns a
     clean 400 instead of a 500 from the ORM).
  3. Only whitelisted fields are sortable — `?ordering=` cannot be pointed at
     an unindexed column to force a table scan.

The distance filter is handled separately in the view, because it needs the
two-phase bounding-box-then-haversine treatment that django-filter cannot
express.
"""

import django_filters
from django.db.models import Q

from apps.profiles.models import PhotographerProfile


class PhotographerFilterSet(django_filters.FilterSet):
    # ─── Text search ─────────────────────────────────────────────────────────
    q = django_filters.CharFilter(
        method="filter_search",
        label="Search across name, business name, tagline, bio and city",
    )

    # ─── Category ────────────────────────────────────────────────────────────
    category = django_filters.CharFilter(
        field_name="categories__slug", lookup_expr="iexact"
    )
    specialization = django_filters.CharFilter(
        field_name="specializations__slug", lookup_expr="iexact"
    )

    # ─── Location ────────────────────────────────────────────────────────────
    city = django_filters.CharFilter(field_name="user__city", lookup_expr="iexact")

    # ─── Budget ──────────────────────────────────────────────────────────────
    min_price = django_filters.NumberFilter(field_name="base_price", lookup_expr="gte")
    max_price = django_filters.NumberFilter(field_name="base_price", lookup_expr="lte")

    # ─── Quality ─────────────────────────────────────────────────────────────
    min_rating = django_filters.NumberFilter(
        field_name="avg_rating", lookup_expr="gte"
    )
    min_reviews = django_filters.NumberFilter(
        field_name="reviews_count", lookup_expr="gte"
    )
    min_experience = django_filters.NumberFilter(
        field_name="years_experience", lookup_expr="gte"
    )

    # ─── Availability & badges ───────────────────────────────────────────────
    available = django_filters.BooleanFilter(field_name="is_accepting_bookings")
    verified = django_filters.BooleanFilter(field_name="is_verified")
    featured = django_filters.BooleanFilter(field_name="is_featured")

    # ─── Availability on a specific date ─────────────────────────────────────
    available_on = django_filters.DateFilter(method="filter_available_on")

    # ─── Sorting (whitelisted) ───────────────────────────────────────────────
    ordering = django_filters.OrderingFilter(
        fields=(
            ("bayesian_rating", "rating"),
            ("base_price", "price"),
            ("years_experience", "experience"),
            ("completed_bookings", "popularity"),
            ("reviews_count", "reviews"),
            ("created_at", "newest"),
        ),
        field_labels={
            "bayesian_rating": "Rating",
            "base_price": "Price",
            "years_experience": "Experience",
            "completed_bookings": "Popularity",
            "reviews_count": "Review count",
            "created_at": "Newest",
        },
    )

    class Meta:
        model = PhotographerProfile
        fields = []

    # ─── Custom methods ──────────────────────────────────────────────────────
    def filter_search(self, queryset, name, value):
        """
        Multi-field text search.

        `icontains` across five columns is the right call at this scale — 200
        rows resolve in single-digit milliseconds. A FULLTEXT index becomes
        worthwhile past roughly 50,000 photographers; see ADR-004 in
        docs/01-system-architecture.md for the threshold and the reasoning.
        """
        term = value.strip()
        if not term:
            return queryset
        return queryset.filter(
            Q(business_name__icontains=term)
            | Q(user__full_name__icontains=term)
            | Q(tagline__icontains=term)
            | Q(bio__icontains=term)
            | Q(user__city__icontains=term)
            | Q(categories__name__icontains=term)
            | Q(specializations__name__icontains=term)
        ).distinct()

    def filter_available_on(self, queryset, name, value):
        """
        Exclude photographers who cannot work on the requested date.

        Three reasons someone is unavailable, all checked:
          · their weekly rule marks that weekday as off
          · a blackout range covers the date
          · they already have a PENDING or ACCEPTED booking that day

        Implemented as exclusions rather than an inclusion join, because a
        photographer with no explicit rules should default to available — the
        opposite would hide every newly-registered account.
        """
        from apps.availability.models import AvailabilityRule, BlackoutDate
        from apps.bookings.constants import BLOCKING_STATUSES
        from apps.bookings.models import Booking

        weekday = value.weekday()

        unavailable_weekday = AvailabilityRule.objects.filter(
            weekday=weekday, is_available=False
        ).values("photographer_id")

        blacked_out = BlackoutDate.objects.filter(
            start_date__lte=value, end_date__gte=value
        ).values("photographer_id")

        already_booked = Booking.objects.filter(
            event_date=value, status__in=BLOCKING_STATUSES
        ).values("photographer_id")

        return queryset.exclude(
            Q(pk__in=unavailable_weekday)
            | Q(pk__in=blacked_out)
            | Q(pk__in=already_booked)
        )
