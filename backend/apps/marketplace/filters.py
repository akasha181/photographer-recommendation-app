"""
Product search and filtering — Module 8.

Declared rather than hand-rolled in the view for the same three reasons as
`profiles/filters.py`: drf-spectacular documents each parameter, values are
coerced and validated before they reach the ORM, and only whitelisted columns
are sortable — so `?ordering=` cannot be pointed at an unindexed field to
force a table scan.
"""

import django_filters
from django.db.models import F, Q

from apps.marketplace.models import DigitalProduct, LicenseType, ProductType


class ProductFilterSet(django_filters.FilterSet):
    q = django_filters.CharFilter(
        method="filter_search", label="Search title, description and tags"
    )

    product_type = django_filters.ChoiceFilter(choices=ProductType.choices)
    license_type = django_filters.ChoiceFilter(choices=LicenseType.choices)
    category = django_filters.CharFilter(
        field_name="category__slug", lookup_expr="iexact"
    )
    seller = django_filters.NumberFilter(field_name="seller_id")

    min_price = django_filters.NumberFilter(field_name="price", lookup_expr="gte")
    max_price = django_filters.NumberFilter(field_name="price", lookup_expr="lte")
    min_rating = django_filters.NumberFilter(field_name="avg_rating", lookup_expr="gte")

    #: "Show me only things I can actually afford right now" — resolved in the
    #: view, which is the only place that knows the caller's wallet balance.
    affordable = django_filters.BooleanFilter(method="filter_noop")

    on_sale = django_filters.BooleanFilter(method="filter_on_sale")
    featured = django_filters.BooleanFilter(field_name="is_featured")

    ordering = django_filters.OrderingFilter(
        fields=(
            ("price", "price"),
            ("sales_count", "popularity"),
            ("avg_rating", "rating"),
            ("created_at", "newest"),
            ("view_count", "views"),
        ),
        field_labels={
            "price": "Price",
            "sales_count": "Best selling",
            "avg_rating": "Rating",
            "created_at": "Newest",
            "view_count": "Most viewed",
        },
    )

    class Meta:
        model = DigitalProduct
        fields = []

    def filter_search(self, queryset, name, value):
        """
        Title, description and tags.

        `tags` is a JSONField holding a list of strings. `icontains` against it
        matches the serialised JSON, which is loose but correct enough at 124
        products — and cheap, which a JSON_CONTAINS per row would not be.
        """
        term = value.strip()
        if not term:
            return queryset
        return queryset.filter(
            Q(title__icontains=term)
            | Q(description__icontains=term)
            | Q(tags__icontains=term)
            | Q(seller__business_name__icontains=term)
        ).distinct()

    def filter_on_sale(self, queryset, name, value):
        if not value:
            return queryset
        return queryset.filter(compare_at_price__gt=F("price"))

    def filter_noop(self, queryset, name, value):
        """Handled in the view — declared here so it appears in the schema."""
        return queryset
