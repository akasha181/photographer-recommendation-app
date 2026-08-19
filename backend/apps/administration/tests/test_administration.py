"""
Administration — Module 14.

THE PROPERTIES UNDER TEST
------------------------
1. **Nobody but an ADMIN reaches any of it.** A valid token for a photographer
   is a 403, not a filtered view.
2. **Every privileged action leaves an audit row, in the same transaction.** If
   the action rolls back the log entry goes with it; if the action succeeds
   there is no path that forgets to record it.
3. **The audit log cannot be edited.** No endpoint, no service function.
4. **Money only moves through the ledger.** An admin adjustment writes a
   `WalletTransaction` and cannot overdraw.
5. **Blocking actually stops the account** — tokens revoked, open bookings
   cancelled through the state machine with a reason the other party sees.
"""

from decimal import Decimal

import pytest

from apps.administration import selectors, services
from apps.administration.models import (
    ApprovalRequest,
    ApprovalStatus,
    AuditAction,
    AuditLog,
    ModerationFlag,
    PlatformSetting,
)
from apps.core.exceptions import BusinessRuleViolation, ConflictError, InsufficientBalance

pytestmark = pytest.mark.django_db

URL = "/api/v1/admin/"


@pytest.fixture
def pending_application(photographer):
    """An application awaiting review, on a not-yet-approved profile."""
    photographer.is_approved = False
    photographer.save(update_fields=["is_approved"])
    return ApprovalRequest.objects.create(
        photographer=photographer,
        submitted_data={"business_name": photographer.business_name},
    )


@pytest.fixture
def open_flag(buyer, completed_booking):
    from apps.reviews import services as review_services

    review = review_services.create_review(
        completed_booking, buyer, rating=1, comment="Absolutely dreadful, avoid."
    )
    return ModerationFlag.objects.create(
        reporter=buyer, content_type="REVIEW", object_id=review.pk, reason="FAKE"
    ), review


# ═══════════════════════════════════════════════════════════════════════════
# ACCESS CONTROL
# ═══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize(
    "path",
    [
        "dashboard/", "approvals/", "flags/", "users/", "topups/",
        "products/", "audit/", "settings/", "broadcasts/",
    ],
)
def test_a_photographer_is_refused_everywhere(photographer_client, path):
    assert photographer_client.get(URL + path).status_code == 403


@pytest.mark.parametrize("path", ["dashboard/", "users/", "audit/"])
def test_a_buyer_is_refused(buyer_client, path):
    assert buyer_client.get(URL + path).status_code == 403


def test_anonymous_is_refused(api_client):
    assert api_client.get(URL + "dashboard/").status_code == 401


def test_public_settings_need_no_login(api_client):
    """
    The one AllowAny endpoint. It returns only rows marked `is_public`, so a new
    setting is never exposed by accident.
    """
    PlatformSetting.objects.create(
        key="rec_weight_content", value="0.55", value_type="FLOAT",
        label="Content weight", is_public=True,
    )
    PlatformSetting.objects.create(
        key="platform_commission_percent", value="10", value_type="FLOAT",
        label="Commission", is_public=False,
    )

    body = api_client.get(URL + "settings/public/").json()["data"]

    assert body == {"rec_weight_content": 0.55}


# ═══════════════════════════════════════════════════════════════════════════
# DASHBOARD
# ═══════════════════════════════════════════════════════════════════════════
def test_dashboard_reports_queue_depths(admin_client_authed, pending_application):
    body = admin_client_authed.get(URL + "dashboard/").json()["data"]

    assert body["queues"]["pending_approvals"] == 1
    assert body["totals"]["photographers"] >= 1
    assert body["window_days"] == 30


def test_the_trend_is_gap_filled(admin_client_authed):
    """A day with no rollup row means "nothing happened", not "no data"."""
    body = admin_client_authed.get(URL + "dashboard/?days=7").json()["data"]

    assert len(body["trend"]) == 7
    assert body["trend"][0]["bookings_created"] == 0


def test_the_window_is_clamped(admin_client_authed):
    body = admin_client_authed.get(URL + "dashboard/?days=99999").json()["data"]
    assert body["window_days"] == 365


# ═══════════════════════════════════════════════════════════════════════════
# PHOTOGRAPHER APPROVAL
# ═══════════════════════════════════════════════════════════════════════════
def test_approving_lists_the_profile_and_audits_it(
    admin_client_authed, pending_application, photographer
):
    response = admin_client_authed.post(
        f"{URL}approvals/{pending_application.pk}/approve/",
        {"note": "Portfolio looks genuine."},
        format="json",
    )
    photographer.refresh_from_db()
    pending_application.refresh_from_db()

    assert response.status_code == 200
    assert photographer.is_approved is True
    assert pending_application.status == ApprovalStatus.APPROVED
    assert AuditLog.objects.filter(
        action=AuditAction.PHOTOGRAPHER_APPROVED, target_id=str(photographer.pk)
    ).exists()


def test_approving_notifies_the_photographer(
    admin_client_authed, pending_application, photographer
):
    from apps.notifications.models import Notification, NotificationType

    admin_client_authed.post(
        f"{URL}approvals/{pending_application.pk}/approve/", {}, format="json"
    )

    assert Notification.objects.filter(
        recipient=photographer.user,
        notification_type=NotificationType.ACCOUNT_APPROVED,
    ).exists()


def test_a_rejection_without_a_reason_is_refused(
    admin_client_authed, pending_application
):
    response = admin_client_authed.post(
        f"{URL}approvals/{pending_application.pk}/reject/", {"reason": "no"},
        format="json",
    )

    assert response.status_code == 400
    pending_application.refresh_from_db()
    assert pending_application.status == ApprovalStatus.PENDING


def test_rejection_stores_and_sends_the_reason(
    admin_client_authed, pending_application, photographer
):
    from apps.notifications.models import Notification

    admin_client_authed.post(
        f"{URL}approvals/{pending_application.pk}/reject/",
        {"reason": "Portfolio images appear to be stock photography."},
        format="json",
    )
    pending_application.refresh_from_db()

    assert pending_application.status == ApprovalStatus.REJECTED
    assert "stock photography" in pending_application.rejection_reason
    body = Notification.objects.filter(recipient=photographer.user).first().body
    assert "stock photography" in body


def test_a_decided_application_cannot_be_decided_again(
    admin_client_authed, pending_application
):
    admin_client_authed.post(
        f"{URL}approvals/{pending_application.pk}/approve/", {}, format="json"
    )

    second = admin_client_authed.post(
        f"{URL}approvals/{pending_application.pk}/reject/",
        {"reason": "Changed my mind about this application."},
        format="json",
    )
    assert second.status_code == 400


def test_rejecting_a_new_application_does_not_unlist_an_approved_photographer(
    photographer, admin_user
):
    """
    A photographer who is already listed keeps the listing they earned.

    Removing a live listing is `block_user`, which is audited under its own
    action and tells the user why.
    """
    assert photographer.is_approved is True
    application = ApprovalRequest.objects.create(photographer=photographer)

    services.reject_photographer(
        application, admin_user, reason="Duplicate application, already listed."
    )
    photographer.refresh_from_db()

    assert photographer.is_approved is True


def test_the_queue_is_oldest_first(admin_client_authed, photographer, other_photographer):
    older = ApprovalRequest.objects.create(photographer=photographer)
    newer = ApprovalRequest.objects.create(photographer=other_photographer)

    rows = admin_client_authed.get(URL + "approvals/?status=PENDING").json()["data"]

    assert [row["id"] for row in rows] == [older.pk, newer.pk]


# ═══════════════════════════════════════════════════════════════════════════
# USER MODERATION
# ═══════════════════════════════════════════════════════════════════════════
def test_blocking_revokes_tokens_and_audits(admin_client_authed, buyer):
    before = buyer.token_version

    response = admin_client_authed.post(
        f"{URL}users/{buyer.pk}/block/",
        {"reason": "Repeated fraudulent top-up receipts."},
        format="json",
    )
    buyer.refresh_from_db()

    assert response.status_code == 200
    assert buyer.is_blocked is True
    assert buyer.is_active is False
    # The kill switch: without it a blocked user keeps working for up to 30
    # minutes on the access token already in their pocket.
    assert buyer.token_version == before + 1
    assert AuditLog.objects.filter(
        action=AuditAction.USER_BLOCKED, target_id=str(buyer.pk)
    ).exists()


def test_blocking_cancels_open_bookings_through_the_state_machine(
    admin_client_authed, buyer, booking
):
    from apps.bookings.constants import BookingStatus
    from apps.bookings.models import BookingStatusHistory

    admin_client_authed.post(
        f"{URL}users/{buyer.pk}/block/",
        {"reason": "Account compromised, cancelling everything."},
        format="json",
    )
    booking.refresh_from_db()

    assert booking.status == BookingStatus.CANCELLED
    # Through the state machine, so the history row naming the actor exists.
    history = BookingStatusHistory.objects.filter(booking=booking).last()
    assert history.to_status == BookingStatus.CANCELLED
    assert "Account suspended" in history.note


def test_blocking_without_a_reason_is_refused(admin_client_authed, buyer):
    response = admin_client_authed.post(
        f"{URL}users/{buyer.pk}/block/", {"reason": "spam"}, format="json"
    )

    assert response.status_code == 400
    buyer.refresh_from_db()
    assert buyer.is_blocked is False


def test_an_admin_cannot_be_blocked(admin_user, buyer):
    from apps.core.constants import UserRole

    buyer.role = UserRole.ADMIN
    buyer.save(update_fields=["role"])

    with pytest.raises(BusinessRuleViolation, match="Administrator accounts"):
        services.block_user(buyer, admin_user, reason="Trying to lock out a colleague")


def test_blocking_twice_is_a_conflict(admin_user, buyer):
    services.block_user(buyer, admin_user, reason="First suspension, for cause.")

    with pytest.raises(ConflictError, match="already blocked"):
        services.block_user(buyer, admin_user, reason="Second suspension attempt.")


def test_unblocking_restores_and_audits(admin_client_authed, buyer, admin_user):
    services.block_user(buyer, admin_user, reason="Temporary suspension pending review.")

    response = admin_client_authed.post(
        f"{URL}users/{buyer.pk}/unblock/", {"reason": "Appeal upheld."}, format="json"
    )
    buyer.refresh_from_db()

    assert response.status_code == 200
    assert buyer.is_blocked is False
    assert buyer.is_active is True
    assert AuditLog.objects.filter(action=AuditAction.USER_UNBLOCKED).exists()


def test_user_detail_carries_cross_app_stats(admin_client_authed, buyer, completed_booking):
    body = admin_client_authed.get(f"{URL}users/{buyer.pk}/").json()["data"]

    assert body["email"] == buyer.email
    assert body["stats"]["bookings_completed"] == 1
    assert "wallet_balance" in body["stats"]


def test_the_user_table_never_exposes_the_password_hash(admin_client_authed, buyer):
    rows = admin_client_authed.get(URL + "users/").json()["data"]

    for row in rows:
        assert "password" not in row


def test_user_search_and_filters(admin_client_authed, buyer, photographer):
    from apps.core.constants import UserRole

    photographers = admin_client_authed.get(
        f"{URL}users/?role={UserRole.PHOTOGRAPHER}"
    ).json()["data"]
    searched = admin_client_authed.get(f"{URL}users/?q=Ayesha").json()["data"]

    assert {row["role"] for row in photographers} == {UserRole.PHOTOGRAPHER}
    assert [row["email"] for row in searched] == [buyer.email]


# ═══════════════════════════════════════════════════════════════════════════
# WALLET ADJUSTMENTS
# ═══════════════════════════════════════════════════════════════════════════
def test_a_credit_writes_a_ledger_row(admin_client_authed, buyer):
    from apps.profiles.models import WalletTransaction, WalletTransactionType

    response = admin_client_authed.post(
        f"{URL}users/{buyer.pk}/adjust-wallet/",
        {"amount": "2500.00", "reason": "Goodwill credit for a cancelled shoot."},
        format="json",
    )

    assert response.status_code == 200
    assert response.json()["data"]["balance"] == "2500.00"
    # A balance with no transaction behind it breaks the invariant the ledger
    # exists to prove.
    txn = WalletTransaction.objects.filter(
        wallet__user=buyer, txn_type=WalletTransactionType.ADJUSTMENT
    ).first()
    assert txn is not None
    assert txn.balance_after == Decimal("2500.00")
    assert txn.performed_by_id is not None


def test_a_debit_cannot_overdraw(admin_user, funded_buyer):
    from apps.profiles.selectors import wallet_balance

    with pytest.raises(InsufficientBalance):
        services.adjust_wallet(
            funded_buyer, admin_user, amount=Decimal("-999999.00"),
            reason="Attempting to claw back more than the balance",
        )

    assert wallet_balance(funded_buyer) == Decimal("50000.00")


def test_an_adjustment_of_zero_is_refused(admin_client_authed, buyer):
    response = admin_client_authed.post(
        f"{URL}users/{buyer.pk}/adjust-wallet/",
        {"amount": "0.00", "reason": "Doing nothing at all."},
        format="json",
    )
    assert response.status_code == 400


def test_an_adjustment_is_audited_with_the_resulting_balance(admin_user, buyer):
    services.adjust_wallet(
        buyer, admin_user, amount=Decimal("1000.00"), reason="Refund for order 12"
    )

    entry = AuditLog.objects.get(action=AuditAction.WALLET_ADJUSTED)
    assert entry.changes["amount"] == "1000.00"
    assert entry.changes["balance_after"] == "1000.00"
    assert "Refund" in entry.reason


# ═══════════════════════════════════════════════════════════════════════════
# CONTENT MODERATION
# ═══════════════════════════════════════════════════════════════════════════
def test_resolving_a_flag_as_actioned_hides_the_review(
    admin_client_authed, open_flag, photographer
):
    flag, review = open_flag

    response = admin_client_authed.post(
        f"{URL}flags/{flag.pk}/resolve/",
        {"action": "ACTIONED", "note": "Buyer never attended the shoot."},
        format="json",
    )
    review.refresh_from_db()
    photographer.refresh_from_db()

    assert response.status_code == 200
    assert review.is_hidden is True
    # The consequence and the resolution are one transaction — and hiding a
    # review must take it out of the public average.
    assert photographer.reviews_count == 0
    assert AuditLog.objects.filter(action=AuditAction.REVIEW_HIDDEN).exists()


def test_dismissing_a_flag_leaves_the_content_alone(admin_client_authed, open_flag):
    flag, review = open_flag

    admin_client_authed.post(
        f"{URL}flags/{flag.pk}/resolve/",
        {"action": "DISMISSED", "note": "Honest criticism, not a fake review."},
        format="json",
    )
    review.refresh_from_db()
    flag.refresh_from_db()

    assert review.is_hidden is False
    assert flag.status == "DISMISSED"


def test_actioning_without_a_note_is_refused(admin_client_authed, open_flag):
    flag, _ = open_flag

    response = admin_client_authed.post(
        f"{URL}flags/{flag.pk}/resolve/", {"action": "ACTIONED"}, format="json"
    )
    assert response.status_code == 400


def test_a_resolved_flag_cannot_be_resolved_twice(admin_client_authed, open_flag):
    flag, _ = open_flag
    admin_client_authed.post(
        f"{URL}flags/{flag.pk}/resolve/",
        {"action": "DISMISSED", "note": "Fine."},
        format="json",
    )

    second = admin_client_authed.post(
        f"{URL}flags/{flag.pk}/resolve/",
        {"action": "ACTIONED", "note": "Changed my mind."},
        format="json",
    )
    assert second.status_code == 409


def test_claiming_moves_it_to_reviewing(admin_client_authed, open_flag):
    flag, _ = open_flag

    body = admin_client_authed.post(f"{URL}flags/{flag.pk}/claim/").json()["data"]

    assert body["status"] == "REVIEWING"


def test_the_queue_previews_what_was_reported(admin_client_authed, open_flag):
    flag, _ = open_flag

    rows = admin_client_authed.get(URL + "flags/?status=OPEN").json()["data"]

    assert "dreadful" in rows[0]["target_preview"]


def test_the_preview_survives_a_missing_target(admin_client_authed, buyer):
    """A queue that 500s because one target row vanished is worse than a dash."""
    ModerationFlag.objects.create(
        reporter=buyer, content_type="PRODUCT", object_id=999_999, reason="SPAM"
    )

    rows = admin_client_authed.get(URL + "flags/").json()["data"]

    assert rows[0]["target_preview"] == "—"


def test_duplicate_reports_from_one_person_collapse(buyer, completed_booking):
    from apps.reviews import services as review_services

    review = review_services.create_review(
        completed_booking, buyer, rating=5, comment="Fine."
    )
    first = services.report_content(
        reporter=buyer, content_type="REVIEW", object_id=review.pk, reason="SPAM"
    )
    second = services.report_content(
        reporter=buyer, content_type="REVIEW", object_id=review.pk, reason="SPAM"
    )

    assert first.pk == second.pk
    assert ModerationFlag.objects.count() == 1


# ═══════════════════════════════════════════════════════════════════════════
# PRODUCTS
# ═══════════════════════════════════════════════════════════════════════════
def test_approving_a_product_lists_it_and_notifies_the_seller(
    admin_client_authed, product, photographer
):
    from apps.notifications.models import Notification, NotificationType

    product.is_approved = False
    product.save(update_fields=["is_approved"])

    response = admin_client_authed.post(f"{URL}products/{product.pk}/approve/")
    product.refresh_from_db()

    assert response.status_code == 200
    assert product.is_approved is True
    assert Notification.objects.filter(
        recipient=photographer.user,
        notification_type=NotificationType.PRODUCT_APPROVED,
    ).exists()


def test_removing_a_product_keeps_purchase_history(
    admin_client_authed, paid_order_item, product
):
    """
    A pulled listing must not revoke a licence somebody paid for.

    `OrderItem.product` is PROTECT, so the row survives; `is_approved=False`
    only takes it out of the shop.
    """
    admin_client_authed.post(
        f"{URL}products/{product.pk}/remove/",
        {"reason": "Copyright complaint received from the original photographer."},
        format="json",
    )
    product.refresh_from_db()
    paid_order_item.refresh_from_db()

    assert product.is_approved is False
    assert paid_order_item.product_id == product.pk
    assert AuditLog.objects.filter(action=AuditAction.PRODUCT_REMOVED).exists()


def test_the_product_queue_is_published_but_unapproved(
    admin_client_authed, product, second_product
):
    product.is_approved = False
    product.save(update_fields=["is_approved"])

    rows = admin_client_authed.get(URL + "products/").json()["data"]

    assert [row["id"] for row in rows] == [product.pk]


# ═══════════════════════════════════════════════════════════════════════════
# TOP-UPS
# ═══════════════════════════════════════════════════════════════════════════
@pytest.fixture
def pending_topup(buyer):
    from django.core.files.base import ContentFile

    from apps.profiles.models import TopUpRequest, Wallet

    Wallet.objects.get_or_create(user=buyer)
    topup = TopUpRequest(
        user=buyer, amount=Decimal("10000.00"), method="BANK",
        transaction_reference="TRX-99001",
    )
    topup.receipt_image.save("receipt.jpg", ContentFile(b"jpeg"), save=False)
    topup.save()
    return topup


def test_approving_a_topup_credits_the_wallet_and_audits(
    admin_client_authed, pending_topup, buyer
):
    from apps.profiles.selectors import wallet_balance

    response = admin_client_authed.post(
        f"{URL}topups/{pending_topup.pk}/approve/",
        {"note": "Receipt matches the bank statement."},
        format="json",
    )
    pending_topup.refresh_from_db()

    assert response.status_code == 200
    assert pending_topup.status == "APPROVED"
    assert wallet_balance(buyer) == Decimal("10000.00")
    assert AuditLog.objects.filter(action=AuditAction.TOPUP_APPROVED).exists()


def test_rejecting_a_topup_needs_a_note(admin_client_authed, pending_topup):
    response = admin_client_authed.post(
        f"{URL}topups/{pending_topup.pk}/reject/", {"note": ""}, format="json"
    )
    assert response.status_code == 400


def test_rejecting_a_topup_credits_nothing(admin_client_authed, pending_topup, buyer):
    from apps.profiles.selectors import wallet_balance

    admin_client_authed.post(
        f"{URL}topups/{pending_topup.pk}/reject/",
        {"note": "No transfer found against that reference."},
        format="json",
    )
    pending_topup.refresh_from_db()

    assert pending_topup.status == "REJECTED"
    assert wallet_balance(buyer) == Decimal("0.00")


def test_the_queue_exposes_the_receipt(admin_client_authed, pending_topup):
    """The whole point of the manual gate is that a human sees the receipt."""
    rows = admin_client_authed.get(URL + "topups/").json()["data"]

    assert rows[0]["receipt_url"] is not None
    assert rows[0]["transaction_reference"] == "TRX-99001"


# ═══════════════════════════════════════════════════════════════════════════
# BOOKINGS
# ═══════════════════════════════════════════════════════════════════════════
def test_force_cancel_goes_through_the_state_machine(admin_client_authed, booking):
    from apps.bookings.constants import BookingStatus
    from apps.bookings.models import BookingStatusHistory

    response = admin_client_authed.post(
        f"{URL}bookings/{booking.pk}/force-cancel/",
        {"reason": "Duplicate booking created by a client-side retry."},
        format="json",
    )
    booking.refresh_from_db()

    assert response.status_code == 200
    assert booking.status == BookingStatus.CANCELLED
    assert BookingStatusHistory.objects.filter(booking=booking).exists()
    assert AuditLog.objects.filter(
        action=AuditAction.BOOKING_FORCE_CANCELLED
    ).exists()


def test_force_cancel_needs_a_specific_reason(admin_client_authed, booking):
    response = admin_client_authed.post(
        f"{URL}bookings/{booking.pk}/force-cancel/", {"reason": "no"}, format="json"
    )
    assert response.status_code == 400


# ═══════════════════════════════════════════════════════════════════════════
# AUDIT LOG
# ═══════════════════════════════════════════════════════════════════════════
def test_the_audit_log_is_readable_and_filterable(admin_client_authed, buyer, admin_user):
    services.block_user(buyer, admin_user, reason="Fraudulent activity confirmed.")

    rows = admin_client_authed.get(
        f"{URL}audit/?action={AuditAction.USER_BLOCKED}"
    ).json()["data"]

    assert len(rows) == 1
    assert rows[0]["actor_name"] == admin_user.full_name
    assert rows[0]["target_label"].startswith(buyer.full_name)


def test_the_audit_log_has_no_write_endpoints(admin_client_authed):
    """
    An audit log an administrator can edit is not an audit log.

    Not 403 — the routes do not exist. POST on the collection is 405 (the
    viewset defines no `create`), and there is no detail route at all, so PATCH
    and DELETE are 404. Both are "there is no way in", which is the guarantee.
    """
    assert admin_client_authed.post(URL + "audit/", {}, format="json").status_code == 405

    entry = AuditLog.objects.create(action=AuditAction.USER_BLOCKED)
    assert admin_client_authed.delete(f"{URL}audit/{entry.pk}/").status_code == 404
    assert (
        admin_client_authed.patch(
            f"{URL}audit/{entry.pk}/", {"reason": "rewritten"}, format="json"
        ).status_code
        == 404
    )
    entry.refresh_from_db()
    assert entry.reason == ""


def test_a_system_actor_reads_as_system_not_blank(admin_client_authed):
    AuditLog.objects.create(action=AuditAction.MODEL_PROMOTED, actor=None)

    rows = admin_client_authed.get(URL + "audit/").json()["data"]

    assert rows[0]["actor_name"] == "System"


def test_the_audit_entry_captures_the_request_context(admin_client_authed, buyer):
    admin_client_authed.post(
        f"{URL}users/{buyer.pk}/block/",
        {"reason": "Verified fraudulent top-up receipts."},
        format="json",
    )

    entry = AuditLog.objects.get(action=AuditAction.USER_BLOCKED)
    assert entry.ip_address is not None


# ═══════════════════════════════════════════════════════════════════════════
# PLATFORM SETTINGS
# ═══════════════════════════════════════════════════════════════════════════
@pytest.fixture
def commission_setting():
    return PlatformSetting.objects.create(
        key="platform_commission_percent", value="10", value_type="FLOAT",
        label="Booking commission %", group="money",
    )


def test_changing_a_setting_audits_the_before_and_after(
    admin_client_authed, commission_setting
):
    response = admin_client_authed.patch(
        f"{URL}settings/{commission_setting.key}/", {"value": "12.5"}, format="json"
    )
    commission_setting.refresh_from_db()

    assert response.status_code == 200
    assert commission_setting.value == "12.5"
    entry = AuditLog.objects.get(action=AuditAction.SETTING_CHANGED)
    assert entry.changes["value"] == ["10", "12.5"]


def test_an_unknown_key_is_refused(admin_client_authed):
    """
    Settings are declared, not created ad hoc.

    A table that accepts arbitrary keys becomes a junk drawer where a typo
    silently creates a second setting nothing reads.
    """
    response = admin_client_authed.patch(
        f"{URL}settings/not_a_real_setting/", {"value": "1"}, format="json"
    )

    assert response.status_code == 400
    assert "Unknown setting" in str(response.data)


def test_a_value_the_type_cannot_parse_is_refused(
    admin_client_authed, commission_setting
):
    response = admin_client_authed.patch(
        f"{URL}settings/{commission_setting.key}/",
        {"value": "twelve point five"},
        format="json",
    )
    assert response.status_code == 400


def test_typed_reads(commission_setting):
    assert services.get_setting("platform_commission_percent") == 10.0
    assert services.get_setting("nothing_here", default=7) == 7


# ═══════════════════════════════════════════════════════════════════════════
# BROADCASTS
# ═══════════════════════════════════════════════════════════════════════════
def test_creating_a_broadcast_audits_and_queues_it(admin_client_authed):
    from apps.notifications.models import Broadcast

    response = admin_client_authed.post(
        URL + "broadcasts/",
        {
            "title": "Eid promotion",
            "body": "20% off all wedding presets this week.",
            "audience": "BUYERS",
        },
        format="json",
    )

    assert response.status_code == 201
    assert Broadcast.objects.filter(title="Eid promotion").exists()
    assert AuditLog.objects.filter(action=AuditAction.BROADCAST_SENT).exists()


def test_a_city_broadcast_must_name_the_city(admin_client_authed):
    response = admin_client_authed.post(
        URL + "broadcasts/",
        {"title": "Lahore meetup", "body": "Come along.", "audience": "CITY"},
        format="json",
    )

    assert response.status_code == 400
    assert "city_filter" in str(response.data)


def test_the_fan_out_respects_the_audience(admin_user, buyer, photographer):
    from apps.notifications.models import Broadcast, Notification
    from apps.notifications.tasks import send_broadcast

    broadcast = Broadcast.objects.create(
        title="Buyers only", body="Hello buyers.", audience="BUYERS",
        created_by=admin_user,
    )
    send_broadcast(broadcast.pk)

    assert Notification.objects.filter(recipient=buyer, title="Buyers only").exists()
    assert not Notification.objects.filter(
        recipient=photographer.user, title="Buyers only"
    ).exists()


# ═══════════════════════════════════════════════════════════════════════════
# SELECTORS
# ═══════════════════════════════════════════════════════════════════════════
def test_queue_counts_are_zero_on_a_clean_platform():
    counts = selectors.queue_counts()

    assert counts == {
        "pending_approvals": 0,
        "open_flags": 0,
        "pending_topups": 0,
        "products_awaiting_review": 0,
    }


def test_platform_totals_count_completed_bookings_only(completed_booking, booking):
    totals = selectors.platform_totals()

    assert totals["bookings_completed"] == 1
    # GMV counts completed shoots only — accepted work has not been earned yet.
    assert Decimal(totals["booking_gmv"]) == completed_booking.total_price
