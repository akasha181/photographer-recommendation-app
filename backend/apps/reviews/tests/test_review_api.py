"""
Review endpoints — authorisation, scoping and the server-computed flags.

WHAT THESE TESTS ARE FOR THAT THE SERVICE TESTS ARE NOT
------------------------------------------------------
`test_reviews.py` proves the rules. This file proves nobody can reach around
them through HTTP: that a photographer cannot post a review, that one buyer
cannot edit another's, that `can_edit` and `marked_helpful` are computed per
caller, and that the public list is genuinely public.
"""

import pytest

from apps.reviews import services

pytestmark = pytest.mark.django_db

REVIEWS = "/api/v1/reviews/"


def payload(booking, **overrides):
    data = {"booking": booking.pk, "rating": 5, "comment": "Wonderful shoot, thank you."}
    data.update(overrides)
    return data


# ═══════════════════════════════════════════════════════════════════════════
# WHO MAY WRITE
# ═══════════════════════════════════════════════════════════════════════════
def test_buyer_can_post(buyer_client, completed_booking):
    response = buyer_client.post(REVIEWS, payload(completed_booking), format="json")

    assert response.status_code == 201
    assert response.json()["data"]["rating"] == 5
    assert response.json()["data"]["can_edit"] is True


def test_photographer_cannot_post(photographer_client, completed_booking):
    response = photographer_client.post(
        REVIEWS, payload(completed_booking), format="json"
    )
    assert response.status_code == 403


def test_anonymous_cannot_post(api_client, completed_booking):
    response = api_client.post(REVIEWS, payload(completed_booking), format="json")
    assert response.status_code == 401


def test_another_buyers_booking_is_not_found(other_buyer_client, completed_booking):
    """
    404-shaped, not 403.

    A 403 would confirm that booking id exists and belongs to somebody — which
    is enough to enumerate other people's bookings.
    """
    response = other_buyer_client.post(
        REVIEWS, payload(completed_booking), format="json"
    )
    assert response.status_code == 400
    assert "not found" in str(response.data).lower()


def test_a_pending_booking_is_refused_with_a_readable_message(buyer_client, booking):
    response = buyer_client.post(REVIEWS, payload(booking), format="json")

    assert response.status_code == 400
    assert "completed" in str(response.data).lower()


# ═══════════════════════════════════════════════════════════════════════════
# PUBLIC READS
# ═══════════════════════════════════════════════════════════════════════════
def test_the_public_list_needs_no_login(api_client, completed_booking, buyer, photographer):
    services.create_review(completed_booking, buyer, rating=5, comment="Superb work.")

    response = api_client.get(f"{REVIEWS}photographers/{photographer.pk}/")

    assert response.status_code == 200
    assert len(response.json()["data"]) == 1
    assert response.json()["data"][0]["photographer_name"] == "Hamza Studio"


def test_the_summary_needs_no_login(api_client, completed_booking, buyer, photographer):
    services.create_review(completed_booking, buyer, rating=4, comment="Very good.")

    response = api_client.get(f"{REVIEWS}photographers/{photographer.pk}/summary/")

    assert response.status_code == 200
    assert response.json()["data"]["total_reviews"] == 1
    assert response.json()["data"]["breakdown"]["4"] == 1


def test_hidden_reviews_are_absent_from_the_public_list(
    api_client, completed_booking, buyer, photographer
):
    review = services.create_review(
        completed_booking, buyer, rating=1, comment="Terrible, avoid."
    )
    services.set_hidden(review, hidden=True, reason="Abusive")

    response = api_client.get(f"{REVIEWS}photographers/{photographer.pk}/")
    assert response.json()["data"] == []


def test_the_public_shape_does_not_leak_the_sentiment_label(
    api_client, completed_booking, buyer, photographer
):
    """
    A machine label on somebody else's words is not evidence.

    The photographer sees it on their own inbox endpoint; buyers do not.
    """
    services.create_review(completed_booking, buyer, rating=5, comment="Lovely photos.")

    response = api_client.get(f"{REVIEWS}photographers/{photographer.pk}/")
    assert "sentiment" not in response.json()["data"][0]


def test_the_photographers_own_inbox_does_include_it(
    photographer_client, completed_booking, buyer
):
    services.create_review(completed_booking, buyer, rating=5, comment="Lovely photos.")

    response = photographer_client.get(f"{REVIEWS}received/")

    assert response.status_code == 200
    assert "sentiment" in response.json()["data"][0]


def test_a_buyer_cannot_open_the_photographer_inbox(buyer_client):
    assert buyer_client.get(f"{REVIEWS}received/").status_code == 403


# ═══════════════════════════════════════════════════════════════════════════
# PER-CALLER FLAGS
# ═══════════════════════════════════════════════════════════════════════════
def test_can_edit_is_false_for_somebody_elses_review(
    other_buyer_client, completed_booking, buyer, photographer
):
    services.create_review(completed_booking, buyer, rating=5, comment="Great stuff.")

    response = other_buyer_client.get(f"{REVIEWS}photographers/{photographer.pk}/")
    assert response.json()["data"][0]["can_edit"] is False


def test_marked_helpful_is_per_caller(
    other_buyer_client, buyer_client, completed_booking, buyer, photographer
):
    review = services.create_review(
        completed_booking, buyer, rating=5, comment="Great stuff."
    )
    other_buyer_client.post(f"{REVIEWS}{review.pk}/helpful/")

    mine = other_buyer_client.get(f"{REVIEWS}photographers/{photographer.pk}/")
    theirs = buyer_client.get(f"{REVIEWS}photographers/{photographer.pk}/")

    assert mine.json()["data"][0]["marked_helpful"] is True
    assert theirs.json()["data"][0]["marked_helpful"] is False


def test_helpful_returns_the_state_it_left_behind(
    other_buyer_client, completed_booking, buyer
):
    review = services.create_review(
        completed_booking, buyer, rating=5, comment="Great stuff."
    )

    first = other_buyer_client.post(f"{REVIEWS}{review.pk}/helpful/")
    second = other_buyer_client.post(f"{REVIEWS}{review.pk}/helpful/")

    assert first.json()["data"] == {"marked_helpful": True, "helpful_count": 1}
    assert second.json()["data"] == {"marked_helpful": False, "helpful_count": 0}


# ═══════════════════════════════════════════════════════════════════════════
# EDIT / DELETE SCOPING
# ═══════════════════════════════════════════════════════════════════════════
def test_another_buyer_cannot_edit_your_review(
    other_buyer_client, completed_booking, buyer
):
    review = services.create_review(
        completed_booking, buyer, rating=5, comment="Great stuff."
    )

    response = other_buyer_client.patch(
        f"{REVIEWS}{review.pk}/", {"rating": 1}, format="json"
    )
    assert response.status_code == 404


def test_another_buyer_cannot_delete_your_review(
    other_buyer_client, completed_booking, buyer
):
    review = services.create_review(
        completed_booking, buyer, rating=5, comment="Great stuff."
    )
    assert other_buyer_client.delete(f"{REVIEWS}{review.pk}/").status_code == 404


def test_the_owner_can_edit_and_delete(buyer_client, completed_booking, buyer):
    review = services.create_review(
        completed_booking, buyer, rating=5, comment="Great stuff."
    )

    edited = buyer_client.patch(
        f"{REVIEWS}{review.pk}/", {"rating": 4, "comment": "Good, with one niggle."},
        format="json",
    )
    assert edited.status_code == 200
    assert edited.json()["data"]["rating"] == 4

    assert buyer_client.delete(f"{REVIEWS}{review.pk}/").status_code == 204


# ═══════════════════════════════════════════════════════════════════════════
# REPLIES
# ═══════════════════════════════════════════════════════════════════════════
def test_photographer_replies_through_the_api(
    photographer_client, completed_booking, buyer
):
    review = services.create_review(
        completed_booking, buyer, rating=5, comment="Great stuff."
    )

    response = photographer_client.post(
        f"{REVIEWS}{review.pk}/reply/", {"comment": "Thank you!"}, format="json"
    )

    assert response.status_code == 201
    assert response.json()["data"]["reply"]["comment"] == "Thank you!"


def test_a_different_photographer_is_refused(
    other_photographer_client, completed_booking, buyer
):
    review = services.create_review(
        completed_booking, buyer, rating=5, comment="Great stuff."
    )

    response = other_photographer_client.post(
        f"{REVIEWS}{review.pk}/reply/", {"comment": "Mine now."}, format="json"
    )
    assert response.status_code == 403


def test_patch_before_replying_is_a_404(photographer_client, completed_booking, buyer):
    review = services.create_review(
        completed_booking, buyer, rating=5, comment="Great stuff."
    )

    response = photographer_client.patch(
        f"{REVIEWS}{review.pk}/reply/", {"comment": "Edited."}, format="json"
    )
    assert response.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════
# PENDING / MINE
# ═══════════════════════════════════════════════════════════════════════════
def test_pending_endpoint_lists_both_domains(
    buyer_client, completed_booking, paid_order_item
):
    response = buyer_client.get(f"{REVIEWS}pending/")

    assert response.status_code == 200
    assert response.json()["data"]["bookings"][0]["booking_id"] == completed_booking.pk
    assert (
        response.json()["data"]["order_items"][0]["order_item_id"] == paid_order_item.pk
    )


def test_mine_lists_only_your_own(
    buyer_client, other_buyer_client, completed_booking, buyer
):
    services.create_review(completed_booking, buyer, rating=5, comment="Great stuff.")

    assert len(buyer_client.get(f"{REVIEWS}mine/").json()["data"]) == 1
    assert other_buyer_client.get(f"{REVIEWS}mine/").json()["data"] == []


# ═══════════════════════════════════════════════════════════════════════════
# PRODUCT REVIEWS
# ═══════════════════════════════════════════════════════════════════════════
def test_product_review_through_the_api(buyer_client, paid_order_item, product):
    response = buyer_client.post(
        f"{REVIEWS}products/",
        {"order_item": paid_order_item.pk, "rating": 5, "comment": "Perfect."},
        format="json",
    )

    assert response.status_code == 201
    assert response.json()["data"]["product_slug"] == product.slug


def test_product_reviews_are_publicly_readable(
    api_client, buyer_client, paid_order_item, product
):
    buyer_client.post(
        f"{REVIEWS}products/",
        {"order_item": paid_order_item.pk, "rating": 4, "comment": "Good value."},
        format="json",
    )

    response = api_client.get(f"{REVIEWS}products/{product.pk}/")

    assert response.status_code == 200
    assert len(response.json()["data"]) == 1


def test_someone_elses_purchase_cannot_be_reviewed(other_buyer_client, paid_order_item):
    response = other_buyer_client.post(
        f"{REVIEWS}products/",
        {"order_item": paid_order_item.pk, "rating": 5},
        format="json",
    )
    assert response.status_code == 400


# ═══════════════════════════════════════════════════════════════════════════
# REPORTING
# ═══════════════════════════════════════════════════════════════════════════
def test_flagging_a_review_creates_one_moderation_row(
    other_buyer_client, completed_booking, buyer
):
    from apps.administration.models import ModerationFlag

    review = services.create_review(
        completed_booking, buyer, rating=1, comment="Awful, would not recommend."
    )

    first = other_buyer_client.post(
        f"{REVIEWS}{review.pk}/flag/",
        {"reason": "FAKE", "detail": "This buyer never showed up."},
        format="json",
    )
    # Tapping Report twice must not fill the queue with the same complaint.
    other_buyer_client.post(
        f"{REVIEWS}{review.pk}/flag/", {"reason": "FAKE"}, format="json"
    )

    assert first.status_code == 200
    assert ModerationFlag.objects.filter(content_type="REVIEW").count() == 1

    review.refresh_from_db()
    assert review.is_flagged is True
    # Flagging does not hide anything — a human decides.
    assert review.is_hidden is False


def test_you_cannot_flag_your_own_review(buyer_client, completed_booking, buyer):
    review = services.create_review(
        completed_booking, buyer, rating=5, comment="Great stuff."
    )

    response = buyer_client.post(
        f"{REVIEWS}{review.pk}/flag/", {"reason": "SPAM"}, format="json"
    )
    assert response.status_code == 400
    assert "your own review" in str(response.data)
