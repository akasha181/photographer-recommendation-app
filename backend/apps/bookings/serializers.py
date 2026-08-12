"""
Booking serializers.

WHAT THE INPUT SERIALIZER REFUSES TO ACCEPT
-------------------------------------------
`BookingCreateSerializer` has no `unit_price`, `total_price`, `travel_fee`,
`discount` or `status` field. Every one of those is derived on the server from
the catalogue. A buyer who can post their own price can book an Rs 85,000
wedding for Rs 1, and no amount of later validation is as reliable as simply
never reading the number.

THREE OUTPUT SHAPES
-------------------
List  — what a card draws (~20 fields).
Detail— adds the timeline, payment record and the actions the caller may take.
Status— the tiny payload the accept/reject/cancel/complete routes accept.
"""

from datetime import timedelta

from django.utils import timezone
from rest_framework import serializers

from apps.bookings.constants import (
    ALLOWED_TRANSITIONS,
    BookingStatus,
    CancellationReason,
    can_transition,
)
from apps.bookings.models import Booking, BookingPayment, BookingStatusHistory
from apps.catalog.models import Service, ServicePackage

#: How far ahead a booking may be requested. Beyond this it is guesswork, and
#: the slot is held against every other buyer for the whole time.
MAX_ADVANCE_DAYS = 365


def _absolute(request, file_field) -> str | None:
    if not file_field:
        return None
    return request.build_absolute_uri(file_field.url) if request else file_field.url


# ═══════════════════════════════════════════════════════════════════════════
# INPUT
# ═══════════════════════════════════════════════════════════════════════════
class BookingCreateSerializer(serializers.Serializer):
    """
    What a buyer sends. Shape and sanity only — availability, pricing and the
    double-booking guard belong to `services.create_booking`, because they
    need a database lock that a serializer has no business holding.
    """

    service = serializers.PrimaryKeyRelatedField(
        queryset=Service.objects.filter(is_active=True)
    )
    package = serializers.PrimaryKeyRelatedField(
        queryset=ServicePackage.objects.all(), required=False, allow_null=True
    )

    event_date = serializers.DateField()
    start_time = serializers.TimeField()
    duration_hours = serializers.IntegerField(
        required=False, min_value=1, max_value=24,
        help_text="Ignored when a package is chosen — packages have a fixed length.",
    )

    location_address = serializers.CharField(max_length=300)
    location_city = serializers.CharField(max_length=80)
    location_latitude = serializers.DecimalField(
        max_digits=9, decimal_places=6, required=False, allow_null=True
    )
    location_longitude = serializers.DecimalField(
        max_digits=9, decimal_places=6, required=False, allow_null=True
    )

    guest_count = serializers.IntegerField(required=False, allow_null=True, min_value=0)
    notes = serializers.CharField(
        max_length=2000, required=False, allow_blank=True, default=""
    )
    special_requirements = serializers.CharField(
        max_length=1000, required=False, allow_blank=True, default=""
    )

    def validate_event_date(self, value):
        today = timezone.localdate()
        if value < today:
            raise serializers.ValidationError("The event date cannot be in the past.")
        if value > today + timedelta(days=MAX_ADVANCE_DAYS):
            raise serializers.ValidationError(
                f"Bookings can be made up to {MAX_ADVANCE_DAYS} days ahead."
            )
        return value

    def validate(self, attrs):
        package = attrs.get("package")
        service = attrs["service"]
        if package is not None and package.service_id != service.id:
            raise serializers.ValidationError(
                {"package": "That package does not belong to the selected service."}
            )
        return attrs


class BookingActionSerializer(serializers.Serializer):
    """Accept and complete: an optional note for the timeline."""

    note = serializers.CharField(
        max_length=500, required=False, allow_blank=True, default=""
    )


class BookingRejectSerializer(serializers.Serializer):
    """Reject: the reason is the whole point, so it is required."""

    reason = serializers.CharField(
        max_length=500, min_length=5,
        help_text="Shown to the buyer. Explain what would work instead if you can.",
    )


class BookingCancelSerializer(serializers.Serializer):
    reason = serializers.ChoiceField(
        choices=CancellationReason.choices, required=False, allow_blank=True
    )
    note = serializers.CharField(
        max_length=500, required=False, allow_blank=True, default=""
    )


# ═══════════════════════════════════════════════════════════════════════════
# OUTPUT
# ═══════════════════════════════════════════════════════════════════════════
class BookingPartySerializer(serializers.Serializer):
    """
    The *other* person on the booking.

    Both sides are included on every row so one list endpoint serves the buyer
    and the photographer without branching — the client draws whichever party
    it is not.
    """

    id = serializers.IntegerField()
    name = serializers.CharField()
    avatar_url = serializers.CharField(allow_null=True)
    city = serializers.CharField(allow_blank=True)
    phone = serializers.CharField(allow_blank=True, required=False)


class BookingStatusHistorySerializer(serializers.ModelSerializer):
    """One step of the audit trail."""

    changed_by_name = serializers.SerializerMethodField()
    label = serializers.SerializerMethodField()

    class Meta:
        model = BookingStatusHistory
        fields = (
            "id", "from_status", "to_status", "label",
            "actor_role", "changed_by_name", "note", "created_at",
        )

    def get_changed_by_name(self, obj) -> str:
        if obj.changed_by is None:
            return "SnapSphere"
        return obj.changed_by.full_name

    def get_label(self, obj) -> str:
        return BookingStatus(obj.to_status).label


class BookingPaymentSerializer(serializers.ModelSerializer):
    outstanding = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True
    )

    class Meta:
        model = BookingPayment
        fields = (
            "method", "status", "advance_amount", "paid_amount", "outstanding",
            "transaction_reference", "is_verified", "verified_at", "note",
        )


class BookingListSerializer(serializers.ModelSerializer):
    """Card payload for the Bookings tab."""

    reference = serializers.CharField(read_only=True)
    status_label = serializers.SerializerMethodField()
    service_title = serializers.CharField(source="service.title", read_only=True)
    category_name = serializers.CharField(source="category.name", read_only=True)
    cover_image_url = serializers.SerializerMethodField()
    photographer = serializers.SerializerMethodField()
    buyer = serializers.SerializerMethodField()
    days_until_event = serializers.IntegerField(read_only=True)
    is_reviewable = serializers.BooleanField(read_only=True)

    class Meta:
        model = Booking
        fields = (
            "id", "uuid", "reference", "status", "status_label",
            "event_date", "start_time", "end_time", "duration_hours",
            "location_city", "location_address",
            "service_title", "category_name", "cover_image_url",
            "total_price", "photographer", "buyer",
            "days_until_event", "is_reviewable", "has_review", "created_at",
        )

    def get_status_label(self, obj) -> str:
        return BookingStatus(obj.status).label

    def get_cover_image_url(self, obj) -> str | None:
        return _absolute(self.context.get("request"), obj.service.cover_image)

    def get_photographer(self, obj) -> dict:
        request = self.context.get("request")
        return {
            "id": obj.photographer_id,
            "name": obj.photographer.display_name,
            "avatar_url": _absolute(request, obj.photographer.user.avatar),
            "city": obj.photographer.user.city,
        }

    def get_buyer(self, obj) -> dict:
        request = self.context.get("request")
        return {
            "id": obj.buyer_id,
            "name": obj.buyer.full_name,
            "avatar_url": _absolute(request, obj.buyer.avatar),
            "city": obj.buyer.city,
        }


class BookingDetailSerializer(BookingListSerializer):
    """Everything the detail screen renders, in one response."""

    timeline = BookingStatusHistorySerializer(
        source="status_history", many=True, read_only=True
    )
    payment = BookingPaymentSerializer(read_only=True)
    available_actions = serializers.SerializerMethodField()
    price_breakdown = serializers.SerializerMethodField()
    contact = serializers.SerializerMethodField()

    class Meta(BookingListSerializer.Meta):
        fields = BookingListSerializer.Meta.fields + (
            "package", "guest_count", "notes", "special_requirements",
            "location_latitude", "location_longitude",
            "unit_price", "quantity", "travel_fee", "discount",
            "commission_percent", "commission_amount", "photographer_payout",
            "price_breakdown", "expires_at", "responded_at", "accepted_at",
            "rejected_at", "cancelled_at", "completed_at",
            "rejection_reason", "cancellation_reason", "cancellation_note",
            "buyer_confirmed_completion", "photographer_marked_complete",
            "timeline", "payment", "available_actions", "contact",
        )

    def get_available_actions(self, obj) -> list[str]:
        """
        What this caller may do right now, straight from the state machine.

        The mobile app renders its buttons from this list. Deriving it here
        rather than reimplementing the rules in TypeScript is what stops the
        two from drifting — a button that appears but always errors is worse
        than no button.
        """
        from apps.bookings.services import actor_role_for

        user = getattr(self.context.get("request"), "user", None)
        if user is None or not user.is_authenticated:
            return []

        role = actor_role_for(obj, user)
        action_for = {
            BookingStatus.ACCEPTED: "accept",
            BookingStatus.REJECTED: "reject",
            BookingStatus.CANCELLED: "cancel",
            BookingStatus.COMPLETED: "complete",
        }
        actions = [
            action_for[target]
            for target in ALLOWED_TRANSITIONS.get(obj.status, set())
            if target in action_for and can_transition(obj.status, target, role)
        ]

        # Completing before the shoot has happened is refused by the service;
        # offering the button anyway would be a guaranteed error.
        if "complete" in actions and obj.event_date > timezone.localdate():
            actions.remove("complete")
        if obj.is_reviewable and role == "BUYER":
            actions.append("review")
        return actions

    def get_price_breakdown(self, obj) -> list[dict]:
        """
        The invoice, as lines the app prints without doing arithmetic.

        Money is formatted server-side for the same reason it is stored as
        DECIMAL: JavaScript cannot be trusted to add currency.
        """
        lines = [
            {
                "label": f"{obj.service.title} × {obj.quantity}",
                "amount": str(obj.unit_price * obj.quantity),
            }
        ]
        if obj.travel_fee:
            lines.append({"label": "Travel fee", "amount": str(obj.travel_fee)})
        if obj.discount:
            lines.append({"label": "Discount", "amount": f"-{obj.discount}"})
        lines.append({"label": "Total", "amount": str(obj.total_price)})
        return lines

    def get_contact(self, obj) -> dict | None:
        """
        Phone numbers, released only once the booking is confirmed.

        Handing over a photographer's number the moment anyone taps "request"
        turns the platform into a free lead list and gives them every reason
        to take the next job off-platform.
        """
        if obj.status not in (BookingStatus.ACCEPTED, BookingStatus.COMPLETED):
            return None
        return {
            "buyer_phone": obj.buyer.phone,
            "photographer_phone": obj.photographer.user.phone,
        }


class BookingCountsSerializer(serializers.Serializer):
    """Tab badges."""

    pending = serializers.IntegerField()
    upcoming = serializers.IntegerField()
    completed = serializers.IntegerField()
    cancelled = serializers.IntegerField()
    total = serializers.IntegerField()
