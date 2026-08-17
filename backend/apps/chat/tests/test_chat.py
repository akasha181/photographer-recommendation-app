"""
Chat — Module 13.

THE PROPERTIES UNDER TEST
------------------------
1. **One thread per pair.** Two taps on "Message" must not split the history in
   two, and neither party can tell which half the other is reading.
2. **Nothing lives only in the socket.** Every message is a row before it is
   broadcast, and `?after=<id>` replays exactly what a reconnecting client
   missed.
3. **A thread is private to its participants.** Not "filtered from the list" —
   unreachable, including by id.
4. **Only a buyer may start a cold thread.** Without that asymmetry the chat is
   a cold-outreach channel aimed at everyone who ever viewed a profile.
"""

import pytest

from apps.chat import selectors, services
from apps.chat.models import Conversation, ConversationParticipant, Message
from apps.core.exceptions import BusinessRuleViolation

pytestmark = pytest.mark.django_db

URL = "/api/v1/chat/"


@pytest.fixture
def thread(buyer, photographer):
    conversation, _ = services.get_or_create_conversation(buyer, photographer.user)
    return conversation


# ═══════════════════════════════════════════════════════════════════════════
# ONE THREAD PER PAIR
# ═══════════════════════════════════════════════════════════════════════════
def test_opening_twice_returns_the_same_thread(buyer, photographer):
    first, created_first = services.get_or_create_conversation(buyer, photographer.user)
    second, created_second = services.get_or_create_conversation(buyer, photographer.user)

    assert first.pk == second.pk
    assert (created_first, created_second) == (True, False)
    assert Conversation.objects.count() == 1


def test_the_photographer_reopening_finds_the_same_thread(buyer, photographer, booking):
    """
    Direction does not matter once a thread exists.

    The photographer is allowed here because they have a booking with this
    buyer — the cold-start rule below is what stops the general case.
    """
    opened, _ = services.get_or_create_conversation(buyer, photographer.user)
    found, created = services.get_or_create_conversation(photographer.user, buyer)

    assert found.pk == opened.pk
    assert created is False


def test_the_api_returns_200_for_an_existing_thread_and_201_for_a_new_one(
    buyer_client, photographer
):
    first = buyer_client.post(
        URL + "conversations/", {"user": photographer.user_id}, format="json"
    )
    second = buyer_client.post(
        URL + "conversations/", {"user": photographer.user_id}, format="json"
    )

    assert first.status_code == 201
    assert second.status_code == 200
    assert first.json()["data"]["id"] == second.json()["data"]["id"]


def test_a_booking_attaches_to_a_thread_that_predates_it(buyer, photographer, booking):
    conversation, _ = services.get_or_create_conversation(buyer, photographer.user)
    assert conversation.booking_id is None

    again, _ = services.get_or_create_conversation(
        buyer, photographer.user, booking=booking
    )
    again.refresh_from_db()

    assert again.booking_id == booking.pk


def test_you_cannot_message_yourself(buyer):
    with pytest.raises(BusinessRuleViolation, match="message yourself"):
        services.get_or_create_conversation(buyer, buyer)


# ═══════════════════════════════════════════════════════════════════════════
# WHO MAY START ONE
# ═══════════════════════════════════════════════════════════════════════════
def test_a_photographer_cannot_cold_message_a_buyer(photographer, other_buyer):
    with pytest.raises(BusinessRuleViolation, match="reply to buyers"):
        services.get_or_create_conversation(photographer.user, other_buyer)


def test_a_photographer_may_message_a_buyer_they_have_a_booking_with(
    photographer, buyer, booking
):
    conversation, created = services.get_or_create_conversation(
        photographer.user, buyer
    )

    assert created is True
    assert conversation.participant_links.count() == 2


def test_a_buyer_cannot_message_an_unapproved_photographer(buyer, photographer):
    photographer.is_approved = False
    photographer.save(update_fields=["is_approved"])

    with pytest.raises(BusinessRuleViolation, match="not accepting messages"):
        services.get_or_create_conversation(buyer, photographer.user)


def test_a_buyer_cannot_message_another_buyer(buyer, other_buyer):
    with pytest.raises(BusinessRuleViolation, match="only message photographers"):
        services.get_or_create_conversation(buyer, other_buyer)


def test_a_blocked_account_cannot_be_messaged(buyer, photographer):
    photographer.user.block("Suspended for review")

    with pytest.raises(BusinessRuleViolation, match="not available"):
        services.get_or_create_conversation(buyer, photographer.user)


# ═══════════════════════════════════════════════════════════════════════════
# PRIVACY
# ═══════════════════════════════════════════════════════════════════════════
def test_a_stranger_cannot_read_a_thread(other_buyer_client, thread):
    """404, not 403 — confirming the thread exists is itself a leak."""
    assert other_buyer_client.get(f"{URL}conversations/{thread.pk}/").status_code == 404
    assert (
        other_buyer_client.get(f"{URL}conversations/{thread.pk}/messages/").status_code
        == 404
    )


def test_a_stranger_cannot_send_into_a_thread(other_buyer_client, thread):
    response = other_buyer_client.post(
        f"{URL}conversations/{thread.pk}/messages/", {"body": "Hi"}, format="json"
    )

    assert response.status_code == 404
    assert Message.objects.count() == 0


def test_the_list_shows_only_your_own_threads(other_buyer_client, thread):
    assert other_buyer_client.get(f"{URL}conversations/").json()["data"] == []


def test_selector_scoping(thread, buyer, other_buyer):
    assert selectors.get_conversation(buyer, thread.pk) is not None
    assert selectors.get_conversation(other_buyer, thread.pk) is None


# ═══════════════════════════════════════════════════════════════════════════
# SENDING
# ═══════════════════════════════════════════════════════════════════════════
def test_sending_writes_the_row_and_the_denormalised_preview(thread, buyer):
    services.send_message(thread, buyer, body="Are you free on the 25th?")
    thread.refresh_from_db()

    assert Message.objects.filter(conversation=thread).count() == 1
    assert thread.last_message_text == "Are you free on the 25th?"
    assert thread.message_count == 1
    assert thread.last_message_sender_id == buyer.id


def test_the_recipient_gets_an_unread_bump_and_the_sender_does_not(
    thread, buyer, photographer
):
    services.send_message(thread, buyer, body="Hello")

    mine = ConversationParticipant.objects.get(conversation=thread, user=buyer)
    theirs = ConversationParticipant.objects.get(
        conversation=thread, user=photographer.user
    )

    assert mine.unread_count == 0
    assert theirs.unread_count == 1


def test_an_empty_message_is_refused(thread, buyer):
    with pytest.raises(BusinessRuleViolation, match="Write something"):
        services.send_message(thread, buyer, body="   ")


def test_a_client_id_makes_a_retry_return_the_same_message(thread, buyer):
    """
    The dropped-response case.

    Without this the buyer taps Send once, the network eats the 201, the app
    retries and the photographer sees the message twice.
    """
    first = services.send_message(thread, buyer, body="Hello", client_id="tap-1")
    second = services.send_message(thread, buyer, body="Hello", client_id="tap-1")

    assert first.pk == second.pk
    assert Message.objects.filter(conversation=thread).count() == 1


def test_the_api_echoes_the_client_id_back(buyer_client, thread):
    body = buyer_client.post(
        f"{URL}conversations/{thread.pk}/messages/",
        {"body": "Hello", "client_id": "bubble-9"},
        format="json",
    ).json()["data"]

    assert body["client_id"] == "bubble-9"
    assert body["is_mine"] is True


def test_is_mine_is_computed_per_caller(buyer_client, photographer_client, thread, buyer):
    services.send_message(thread, buyer, body="Hello")

    mine = buyer_client.get(f"{URL}conversations/{thread.pk}/messages/").json()["data"]
    theirs = photographer_client.get(
        f"{URL}conversations/{thread.pk}/messages/"
    ).json()["data"]

    assert mine[0]["is_mine"] is True
    assert theirs[0]["is_mine"] is False


def test_the_first_message_can_ride_along_with_opening_the_thread(
    buyer_client, photographer
):
    response = buyer_client.post(
        URL + "conversations/",
        {"user": photographer.user_id, "message": "Hi, are you free in September?"},
        format="json",
    )

    assert response.status_code == 201
    assert response.json()["data"]["last_message_text"] == (
        "Hi, are you free in September?"
    )


# ═══════════════════════════════════════════════════════════════════════════
# PAGING — replay, not page numbers
# ═══════════════════════════════════════════════════════════════════════════
def test_after_replays_exactly_what_was_missed(buyer_client, thread, buyer):
    sent = [services.send_message(thread, buyer, body=f"m{i}") for i in range(5)]

    rows = buyer_client.get(
        f"{URL}conversations/{thread.pk}/messages/?after={sent[1].pk}"
    ).json()["data"]

    assert [row["body"] for row in rows] == ["m2", "m3", "m4"]


def test_before_returns_the_window_just_above_the_scroll_position(
    buyer_client, thread, buyer
):
    """
    Scroll-back must return the NEWEST rows below the cursor, not the oldest.

    Selecting `pk < before` ordered ascending would hand back the start of the
    conversation, so an old thread would jump to its beginning on every pull.
    """
    sent = [services.send_message(thread, buyer, body=f"m{i}") for i in range(10)]

    rows = buyer_client.get(
        f"{URL}conversations/{thread.pk}/messages/?before={sent[9].pk}&limit=3"
    ).json()["data"]

    assert [row["body"] for row in rows] == ["m6", "m7", "m8"]


def test_the_default_window_is_the_newest_messages_oldest_first(
    buyer_client, thread, buyer
):
    for index in range(4):
        services.send_message(thread, buyer, body=f"m{index}")

    rows = buyer_client.get(
        f"{URL}conversations/{thread.pk}/messages/?limit=2"
    ).json()["data"]

    assert [row["body"] for row in rows] == ["m2", "m3"]


def test_limit_is_capped(buyer_client, thread, buyer):
    services.send_message(thread, buyer, body="only one")

    response = buyer_client.get(
        f"{URL}conversations/{thread.pk}/messages/?limit=99999"
    )
    assert response.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════
# READ WATERMARK
# ═══════════════════════════════════════════════════════════════════════════
def test_marking_read_clears_the_badge_and_stamps_the_other_sides_messages(
    thread, buyer, photographer
):
    message = services.send_message(thread, buyer, body="Hello")

    services.mark_read(thread, photographer.user)

    link = ConversationParticipant.objects.get(
        conversation=thread, user=photographer.user
    )
    message.refresh_from_db()

    assert link.unread_count == 0
    assert link.last_read_message_id == message.pk
    assert message.read_at is not None


def test_reading_your_own_message_does_not_stamp_it(thread, buyer):
    message = services.send_message(thread, buyer, body="Hello")

    services.mark_read(thread, buyer)
    message.refresh_from_db()

    # A read receipt on your own message means nothing, and stamping it would
    # show the sender their own tick as if the other side had read it.
    assert message.read_at is None


def test_the_watermark_never_moves_backwards(thread, buyer, photographer):
    """
    A reconnecting client can replay an old `read` frame out of order. Accepting
    it would resurrect messages the user has already seen as unread.
    """
    first = services.send_message(thread, buyer, body="m1")
    second = services.send_message(thread, buyer, body="m2")

    services.mark_read(thread, photographer.user, up_to=second.pk)
    services.mark_read(thread, photographer.user, up_to=first.pk)

    link = ConversationParticipant.objects.get(
        conversation=thread, user=photographer.user
    )
    assert link.last_read_message_id == second.pk


def test_unread_total_across_threads(buyer, photographer, other_photographer):
    first, _ = services.get_or_create_conversation(buyer, photographer.user)
    second, _ = services.get_or_create_conversation(buyer, other_photographer.user)

    services.send_message(first, photographer.user, body="a")
    services.send_message(second, other_photographer.user, body="b")
    services.send_message(second, other_photographer.user, body="c")

    assert services.unread_total(buyer) == 3


def test_the_badge_endpoint_matches(buyer_client, thread, photographer):
    services.send_message(thread, photographer.user, body="Yes, I'm free.")

    body = buyer_client.get(f"{URL}conversations/unread-count/").json()["data"]
    assert body["unread_total"] == 1


# ═══════════════════════════════════════════════════════════════════════════
# MUTE / BLOCK / ARCHIVE / LEAVE
# ═══════════════════════════════════════════════════════════════════════════
def test_muting_a_thread_stops_the_bell_but_not_the_message(
    thread, buyer, photographer
):
    from apps.notifications.models import Notification, NotificationType

    services.set_muted(thread, photographer.user, muted=True)
    services.send_message(thread, buyer, body="Hello")

    assert Message.objects.filter(conversation=thread).count() == 1
    assert not Notification.objects.filter(
        recipient=photographer.user, notification_type=NotificationType.NEW_MESSAGE
    ).exists()


def test_blocking_stops_the_blockers_unread_count_rising(thread, buyer, photographer):
    services.set_blocked(thread, photographer.user, blocked=True)
    services.send_message(thread, buyer, body="Hello?")

    link = ConversationParticipant.objects.get(
        conversation=thread, user=photographer.user
    )
    assert link.unread_count == 0


def test_blocking_is_silent_to_the_blocked_party(buyer_client, thread, photographer):
    """
    A success response either way.

    Telling somebody they were blocked is what makes people open a second
    account and try again.
    """
    services.set_blocked(thread, photographer.user, blocked=True)

    response = buyer_client.post(
        f"{URL}conversations/{thread.pk}/messages/", {"body": "Hello?"}, format="json"
    )
    assert response.status_code == 201


def test_toggles_report_the_state_they_left_behind(buyer_client, thread):
    muted = buyer_client.post(f"{URL}conversations/{thread.pk}/mute/").json()["data"]
    unmuted = buyer_client.post(f"{URL}conversations/{thread.pk}/mute/").json()["data"]

    assert muted == {"is_muted": True}
    assert unmuted == {"is_muted": False}


def test_archiving_moves_the_thread_out_of_the_default_list(buyer_client, thread):
    buyer_client.post(f"{URL}conversations/{thread.pk}/archive/")

    assert buyer_client.get(f"{URL}conversations/").json()["data"] == []
    assert len(buyer_client.get(f"{URL}conversations/?archived=1").json()["data"]) == 1


def test_leaving_removes_it_from_your_list_but_not_from_theirs(
    buyer_client, photographer_client, thread
):
    buyer_client.post(f"{URL}conversations/{thread.pk}/leave/")

    assert buyer_client.get(f"{URL}conversations/").json()["data"] == []
    assert len(photographer_client.get(f"{URL}conversations/").json()["data"]) == 1


def test_you_cannot_send_after_leaving(thread, buyer):
    services.leave_conversation(thread, buyer)

    with pytest.raises(BusinessRuleViolation, match="left this conversation"):
        services.send_message(thread, buyer, body="One more thing")


def test_reopening_after_leaving_rejoins_rather_than_starting_over(
    thread, buyer, photographer
):
    services.send_message(thread, buyer, body="Hello")
    services.leave_conversation(thread, buyer)

    again, created = services.get_or_create_conversation(buyer, photographer.user)

    assert again.pk == thread.pk
    assert created is False
    assert again.message_count == 1


# ═══════════════════════════════════════════════════════════════════════════
# EDIT / DELETE / REPORT
# ═══════════════════════════════════════════════════════════════════════════
def test_deleting_keeps_the_row_and_replaces_the_text(buyer_client, thread, buyer):
    message = services.send_message(thread, buyer, body="Oops, wrong chat")

    assert buyer_client.delete(f"{URL}messages/{message.pk}/").status_code == 204

    rows = buyer_client.get(f"{URL}conversations/{thread.pk}/messages/").json()["data"]
    assert rows[0]["is_deleted"] is True
    assert rows[0]["body"] == "This message was deleted"


def test_you_cannot_delete_the_other_sides_message(
    photographer_client, thread, buyer
):
    message = services.send_message(thread, buyer, body="Mine")

    response = photographer_client.delete(f"{URL}messages/{message.pk}/")

    assert response.status_code == 400
    message.refresh_from_db()
    assert message.is_deleted is False


def test_deleting_the_last_message_keeps_the_preview_honest(thread, buyer):
    message = services.send_message(thread, buyer, body="Wrong chat")

    services.delete_message(message, buyer)
    thread.refresh_from_db()

    assert thread.last_message_text == "This message was deleted"


def test_editing_marks_it_edited(buyer_client, thread, buyer):
    message = services.send_message(thread, buyer, body="Are you free on the 25th")

    body = buyer_client.patch(
        f"{URL}messages/{message.pk}/",
        {"body": "Are you free on the 26th?"},
        format="json",
    ).json()["data"]

    assert body["is_edited"] is True
    assert body["body"] == "Are you free on the 26th?"


def test_a_stranger_cannot_reach_a_message_at_all(other_buyer_client, thread, buyer):
    message = services.send_message(thread, buyer, body="Private")

    assert other_buyer_client.delete(f"{URL}messages/{message.pk}/").status_code == 404


def test_reporting_a_message_reaches_the_moderation_queue(
    photographer_client, thread, buyer
):
    from apps.administration.models import ModerationFlag

    message = services.send_message(
        thread, buyer, body="Let's do this off the platform, call me"
    )

    response = photographer_client.post(
        f"{URL}messages/{message.pk}/report/",
        {"reason": "OFF_PLATFORM", "detail": "Asked to move off-platform."},
        format="json",
    )

    assert response.status_code == 200
    assert ModerationFlag.objects.filter(
        content_type="MESSAGE", object_id=message.pk
    ).count() == 1


def test_you_cannot_report_your_own_message(buyer_client, thread, buyer):
    message = services.send_message(thread, buyer, body="Hello")

    response = buyer_client.post(
        f"{URL}messages/{message.pk}/report/", {"reason": "SPAM"}, format="json"
    )
    assert response.status_code == 400


# ═══════════════════════════════════════════════════════════════════════════
# CONTACTS
# ═══════════════════════════════════════════════════════════════════════════
def test_a_buyers_contact_picker_offers_approved_photographers(
    buyer_client, photographer, other_photographer
):
    other_photographer.is_approved = False
    other_photographer.save(update_fields=["is_approved"])

    rows = buyer_client.get(f"{URL}conversations/contacts/").json()["data"]

    assert [row["id"] for row in rows] == [photographer.user_id]


def test_a_photographers_picker_offers_only_their_own_buyers(
    photographer_client, buyer, other_buyer, booking
):
    rows = photographer_client.get(f"{URL}conversations/contacts/").json()["data"]
    ids = [row["id"] for row in rows]

    assert buyer.id in ids
    assert other_buyer.id not in ids


def test_the_picker_never_offers_somebody_the_server_would_refuse(
    photographer_client, buyer, other_buyer, booking, photographer
):
    """
    The picker and `_assert_may_initiate` must agree.

    A list offering a person the POST then rejects is worse than a shorter list.
    """
    rows = photographer_client.get(f"{URL}conversations/contacts/").json()["data"]

    for row in rows:
        from django.contrib.auth import get_user_model

        target = get_user_model().objects.get(pk=row["id"])
        services.get_or_create_conversation(photographer.user, target)


# ═══════════════════════════════════════════════════════════════════════════
# THREAD HEADER
# ═══════════════════════════════════════════════════════════════════════════
def test_the_header_carries_the_other_party_and_the_booking(
    buyer_client, buyer, photographer, booking
):
    conversation, _ = services.get_or_create_conversation(
        buyer, photographer.user, booking=booking
    )

    body = buyer_client.get(f"{URL}conversations/{conversation.pk}/").json()["data"]

    assert body["other_participant"]["id"] == photographer.user_id
    assert body["other_participant"]["business_name"] == "Hamza Studio"
    assert body["booking"]["id"] == booking.pk
    assert body["booking"]["status"] == booking.status


def test_a_thread_with_no_messages_still_appears_in_the_list(buyer_client, thread):
    """
    `last_message_at` is NULL until the first message.

    Ordering on it alone would drop a freshly opened thread to the bottom of the
    list — the one place the user is looking right after tapping "Message".
    """
    rows = buyer_client.get(f"{URL}conversations/").json()["data"]

    assert len(rows) == 1
    assert rows[0]["last_message_at"] is None
