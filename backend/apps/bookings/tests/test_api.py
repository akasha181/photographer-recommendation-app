"""
The booking HTTP surface.

Covers what the service-layer tests cannot: authorisation at the endpoint,
the response envelope the mobile app parses, and the `available_actions` list
the app renders its buttons from.
"""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.bookings.constants import BookingStatus
from conftest import working_date

pytestmark = pytest.mark.django_db

URL = "/api/v1/bookings/"


def _payload(service, event_date, **overrides):
    return {
        "service": service.pk,
        "event_date": event_date.isoformat(),
        "start_time": "14:00",
        "location_address": "F-7 Markaz, Islamabad",
        "location_city": "Islamabad",
        **overrides,
    }


# ═══════════════════════════════════════════════════════════════════════════
# CREATE
# ═══════════════════════════════════════════════════════════════════════════
def test_buyer_creates_a_booking(buyer_client, service, event_date):
    response = buyer_client.post(URL, _payload(service, event_date), format="json")

    assert response.status_code == 201
    body = response.json()
    assert body["success"] is True
    assert body["data"]["status"] == BookingStatus.PENDING
    assert body["data"]["total_price"] == "85000.00"
    assert body["data"]["reference"].startswith("SNP-")


def test_anonymous_cannot_create(api_client, service, event_date):
    response = api_client.post(URL, _payload(service, event_date), format="json")
    assert response.status_code == 401


def test_photographer_cannot_create(photographer_client, service, event_date):
    response = photographer_client.post(URL, _payload(service, event_date), format="json")
    assert response.status_code == 403


def test_the_client_cannot_dictate_the_price(buyer_client, service, event_date):
    """Unknown fields are ignored, not honoured."""
    response = buyer_client.post(
        URL,
        _payload(service, event_date, total_price="1.00", unit_price="1.00", status="ACCEPTED"),
        format="json",
    )

    assert response.status_code == 201
    assert response.json()["data"]["total_price"] == "85000.00"
    assert response.json()["data"]["status"] == BookingStatus.PENDING


def test_a_past_date_is_rejected(buyer_client, service):
    response = buyer_client.post(
        URL,
        _payload(service, timezone.localdate() - timedelta(days=1)),
        format="json",
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_a_full_day_returns_400_with_an_explanation(
    buyer_client, other_buyer_client, service, event_date
):
    """The seeded calendar allows one shoot per day."""
    buyer_client.post(URL, _payload(service, event_date), format="json")
    response = other_buyer_client.post(
        URL, _payload(service, event_date, start_time="18:00"), format="json"
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "BUSINESS_RULE_VIOLATION"
    assert "Fully booked" in response.json()["message"]


def test_a_taken_slot_returns_409(
    buyer_client, other_buyer_client, service, event_date, photographer
):
    """With capacity to spare, the clash is the exact start time — a conflict."""
    from apps.availability.models import AvailabilityRule

    AvailabilityRule.objects.filter(
        photographer=photographer, weekday=event_date.weekday()
    ).update(max_bookings=2)

    buyer_client.post(URL, _payload(service, event_date), format="json")
    response = other_buyer_client.post(URL, _payload(service, event_date), format="json")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CONFLICT"


def test_the_idempotency_key_prevents_a_duplicate(buyer_client, service, event_date):
    payload = _payload(service, event_date)
    headers = {"HTTP_IDEMPOTENCY_KEY": "retry-1"}

    first = buyer_client.post(URL, payload, format="json", **headers)
    second = buyer_client.post(URL, payload, format="json", **headers)

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["data"]["id"] == second.json()["data"]["id"]


# ═══════════════════════════════════════════════════════════════════════════
# READ + SCOPING
# ═══════════════════════════════════════════════════════════════════════════
def test_buyer_lists_their_own_bookings(buyer_client, booking):
    response = buyer_client.get(URL)

    assert response.status_code == 200
    rows = response.json()["data"]
    assert [row["id"] for row in rows] == [booking.pk]


def test_photographer_sees_the_same_booking_from_their_side(photographer_client, booking):
    response = photographer_client.get(URL)
    assert [row["id"] for row in response.json()["data"]] == [booking.pk]


def test_a_stranger_sees_nothing(other_buyer_client, booking):
    response = other_buyer_client.get(URL)
    assert response.json()["data"] == []


def test_a_stranger_gets_404_not_403(other_buyer_client, booking):
    """
    "This exists but is not yours" is itself information worth withholding.
    """
    response = other_buyer_client.get(f"{URL}{booking.pk}/")
    assert response.status_code == 404


def test_the_group_filter_matches_the_app_tabs(buyer_client, booking, photographer):
    from apps.bookings.services import accept_booking

    assert buyer_client.get(f"{URL}?group=pending").json()["data"]
    assert buyer_client.get(f"{URL}?group=upcoming").json()["data"] == []

    accept_booking(booking, photographer.user)

    assert buyer_client.get(f"{URL}?group=pending").json()["data"] == []
    assert buyer_client.get(f"{URL}?group=upcoming").json()["data"]


def test_counts_endpoint(buyer_client, booking):
    body = buyer_client.get(f"{URL}counts/").json()["data"]

    assert body["pending"] == 1
    assert body["upcoming"] == 0
    assert body["total"] == 1


def test_detail_includes_the_timeline(buyer_client, booking):
    body = buyer_client.get(f"{URL}{booking.pk}/").json()["data"]

    assert len(body["timeline"]) == 1
    assert body["timeline"][0]["to_status"] == BookingStatus.PENDING
    assert body["price_breakdown"][-1]["label"] == "Total"


def test_phone_numbers_are_withheld_until_confirmed(
    buyer_client, booking, photographer
):
    from apps.bookings.services import accept_booking

    assert buyer_client.get(f"{URL}{booking.pk}/").json()["data"]["contact"] is None

    accept_booking(booking, photographer.user)
    contact = buyer_client.get(f"{URL}{booking.pk}/").json()["data"]["contact"]

    assert contact["photographer_phone"] == photographer.user.phone


# ═══════════════════════════════════════════════════════════════════════════
# AVAILABLE ACTIONS — what the app draws its buttons from
# ═══════════════════════════════════════════════════════════════════════════
def test_pending_actions_differ_by_role(buyer_client, photographer_client, booking):
    buyer_actions = buyer_client.get(f"{URL}{booking.pk}/").json()["data"][
        "available_actions"
    ]
    photog_actions = photographer_client.get(f"{URL}{booking.pk}/").json()["data"][
        "available_actions"
    ]

    assert buyer_actions == ["cancel"]
    assert sorted(photog_actions) == ["accept", "reject"]


def test_complete_is_not_offered_before_the_event(photographer_client, booking, photographer):
    from apps.bookings.services import accept_booking

    accept_booking(booking, photographer.user)
    actions = photographer_client.get(f"{URL}{booking.pk}/").json()["data"][
        "available_actions"
    ]

    assert "complete" not in actions
    assert "cancel" in actions


def test_review_is_offered_once_completed(buyer_client, booking, photographer):
    from apps.bookings.services import accept_booking, complete_booking

    accepted = accept_booking(booking, photographer.user)
    accepted.event_date = timezone.localdate() - timedelta(days=1)
    accepted.save(update_fields=["event_date"])
    complete_booking(accepted, photographer.user)

    actions = buyer_client.get(f"{URL}{booking.pk}/").json()["data"]["available_actions"]
    assert actions == ["review"]


# ═══════════════════════════════════════════════════════════════════════════
# TRANSITION ROUTES
# ═══════════════════════════════════════════════════════════════════════════
def test_photographer_accepts_over_http(photographer_client, booking):
    response = photographer_client.post(f"{URL}{booking.pk}/accept/", {}, format="json")

    assert response.status_code == 200
    assert response.json()["data"]["status"] == BookingStatus.ACCEPTED
    assert response.json()["message"] == "Booking accepted"


def test_buyer_cannot_call_accept(buyer_client, booking):
    response = buyer_client.post(f"{URL}{booking.pk}/accept/", {}, format="json")
    assert response.status_code == 403


def test_reject_requires_a_reason(photographer_client, booking):
    response = photographer_client.post(f"{URL}{booking.pk}/reject/", {}, format="json")
    assert response.status_code == 400

    response = photographer_client.post(
        f"{URL}{booking.pk}/reject/", {"reason": "Already booked that day."}, format="json"
    )
    assert response.status_code == 200
    assert response.json()["data"]["rejection_reason"] == "Already booked that day."


def test_buyer_cancels_over_http(buyer_client, booking):
    response = buyer_client.post(
        f"{URL}{booking.pk}/cancel/", {"reason": "BUYER_CHANGED_PLANS"}, format="json"
    )

    assert response.status_code == 200
    assert response.json()["data"]["status"] == BookingStatus.CANCELLED


def test_an_illegal_transition_returns_a_business_rule_error(photographer_client, booking):
    photographer_client.post(f"{URL}{booking.pk}/accept/", {}, format="json")
    response = photographer_client.post(f"{URL}{booking.pk}/accept/", {}, format="json")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "BUSINESS_RULE_VIOLATION"
    assert "already accepted" in response.json()["message"]


def test_a_stranger_cannot_act_on_a_booking(other_buyer_client, booking):
    response = other_buyer_client.post(f"{URL}{booking.pk}/cancel/", {}, format="json")
    assert response.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════
# AVAILABILITY API
# ═══════════════════════════════════════════════════════════════════════════
def test_calendar_marks_sunday_off(api_client, photographer):
    response = api_client.get(
        f"/api/v1/availability/photographers/{photographer.pk}/?days=14"
    )

    assert response.status_code == 200
    days = response.json()["data"]["days"]
    assert len(days) == 14

    sundays = [d for d in days if d["reason"] == "WEEKLY_OFF"]
    assert sundays and all("Sunday" in d["message"] for d in sundays)


def test_calendar_marks_a_booked_date(api_client, photographer, booking):
    response = api_client.get(
        f"/api/v1/availability/photographers/{photographer.pk}/?days=30"
    )
    day = next(
        d
        for d in response.json()["data"]["days"]
        if d["date"] == booking.event_date.isoformat()
    )

    assert day["is_available"] is False
    assert day["reason"] == "FULLY_BOOKED"
    assert "14:00" in day["booked_times"]


def test_day_endpoint_offers_start_times(api_client, photographer):
    date = working_date(10)
    response = api_client.get(
        f"/api/v1/availability/photographers/{photographer.pk}/day/"
        f"?date={date.isoformat()}&duration_hours=4"
    )

    assert response.status_code == 200
    body = response.json()["data"]
    assert body["is_available"] is True
    assert body["available_start_times"][0] == "09:00"
    assert "14:00" in body["available_start_times"]


def test_day_endpoint_requires_a_date(api_client, photographer):
    response = api_client.get(f"/api/v1/availability/photographers/{photographer.pk}/day/")
    assert response.status_code == 400
