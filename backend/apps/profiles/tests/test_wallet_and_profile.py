"""
Wallet, top-ups and the caller's own profile — Module 4.

THE INVARIANT THESE TESTS EXIST FOR
-----------------------------------
Every rupee that moves writes a ledger row recording the balance before and
after. If the running total ever disagrees with the sum of the rows, the bug
is provable rather than merely suspected — but only if nothing is allowed to
move a balance without going through `credit_wallet` / `debit_wallet`.
"""

from decimal import Decimal

import pytest

from apps.core.exceptions import BusinessRuleViolation, InsufficientBalance
from apps.profiles.models import (
    TopUpRequest,
    TopUpStatus,
    Wallet,
    WalletTransaction,
    WalletTransactionType,
)
from apps.profiles.services import (
    approve_topup,
    credit_wallet,
    debit_wallet,
    reject_topup,
    request_topup,
    update_buyer_profile,
    update_photographer_profile,
)

pytestmark = pytest.mark.django_db


def _receipt():
    """A 1x1 PNG — the smallest thing that survives ImageField validation."""
    import base64

    from django.core.files.uploadedfile import SimpleUploadedFile

    png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    )
    return SimpleUploadedFile("receipt.png", png, content_type="image/png")


# ═══════════════════════════════════════════════════════════════════════════
# THE LEDGER
# ═══════════════════════════════════════════════════════════════════════════
def test_credit_writes_a_ledger_row(buyer):
    credit_wallet(buyer, Decimal("5000.00"), txn_type=WalletTransactionType.TOPUP)
    row = WalletTransaction.objects.get(wallet__user=buyer)

    assert row.balance_before == Decimal("0.00")
    assert row.balance_after == Decimal("5000.00")
    assert Wallet.objects.get(user=buyer).balance == Decimal("5000.00")


def test_debit_writes_a_ledger_row(buyer):
    credit_wallet(buyer, Decimal("5000.00"), txn_type=WalletTransactionType.TOPUP)
    debit_wallet(buyer, Decimal("1200.00"), txn_type=WalletTransactionType.PURCHASE)

    row = WalletTransaction.objects.filter(txn_type="PURCHASE").get()
    assert row.balance_before == Decimal("5000.00")
    assert row.balance_after == Decimal("3800.00")


def test_the_ledger_reconciles_with_the_balance(buyer):
    """The whole point of a ledger: the two must always agree."""
    credit_wallet(buyer, Decimal("9000.00"), txn_type=WalletTransactionType.TOPUP)
    debit_wallet(buyer, Decimal("2500.00"), txn_type=WalletTransactionType.PURCHASE)
    credit_wallet(buyer, Decimal("400.00"), txn_type=WalletTransactionType.REFUND)

    wallet = Wallet.objects.get(user=buyer)
    running = Decimal("0.00")
    for row in WalletTransaction.objects.filter(wallet=wallet).order_by("created_at", "id"):
        assert row.balance_before == running
        running = row.balance_after

    assert running == wallet.balance
    assert wallet.total_credited - wallet.total_debited == wallet.balance


def test_cannot_overdraw(buyer):
    credit_wallet(buyer, Decimal("100.00"), txn_type=WalletTransactionType.TOPUP)

    with pytest.raises(InsufficientBalance, match="Please top up"):
        debit_wallet(buyer, Decimal("500.00"), txn_type=WalletTransactionType.PURCHASE)

    assert Wallet.objects.get(user=buyer).balance == Decimal("100.00")


def test_zero_and_negative_amounts_are_refused(buyer):
    for amount in (Decimal("0.00"), Decimal("-50.00")):
        with pytest.raises(BusinessRuleViolation):
            credit_wallet(buyer, amount, txn_type=WalletTransactionType.TOPUP)


# ═══════════════════════════════════════════════════════════════════════════
# TOP-UPS — the only way money enters the platform
# ═══════════════════════════════════════════════════════════════════════════
def test_requesting_a_topup_credits_nothing(buyer):
    """
    The manual gate exists precisely so a claimed transfer is never taken on
    trust. Submitting a receipt must not move the balance by a single rupee.
    """
    topup = request_topup(
        buyer,
        amount=Decimal("10000.00"),
        method="BANK",
        transaction_reference="TRX-99887766",
        receipt_image=_receipt(),
    )

    assert topup.status == TopUpStatus.PENDING
    assert Wallet.objects.get(user=buyer).balance == Decimal("0.00")
    assert WalletTransaction.objects.count() == 0


def test_admin_approval_credits_the_wallet(buyer, admin_user):
    topup = request_topup(
        buyer,
        amount=Decimal("10000.00"),
        method="BANK",
        transaction_reference="TRX-11223344",
        receipt_image=_receipt(),
    )
    approve_topup(topup, admin_user)

    assert Wallet.objects.get(user=buyer).balance == Decimal("10000.00")
    row = WalletTransaction.objects.get(txn_type="TOPUP")
    assert row.performed_by_id == admin_user.id


def test_rejection_credits_nothing(buyer, admin_user):
    topup = request_topup(
        buyer,
        amount=Decimal("10000.00"),
        method="BANK",
        transaction_reference="TRX-55667788",
        receipt_image=_receipt(),
    )
    reject_topup(topup, admin_user, "Receipt is unreadable.")

    topup.refresh_from_db()
    assert topup.status == TopUpStatus.REJECTED
    assert Wallet.objects.get(user=buyer).balance == Decimal("0.00")


def test_a_reference_cannot_be_credited_twice(buyer, other_buyer, admin_user):
    """
    The same bank transfer must not fund two wallets — including someone
    else's. `uniq_approved_txn_reference` backs this in the database.
    """
    first = request_topup(
        buyer,
        amount=Decimal("5000.00"),
        method="BANK",
        transaction_reference="TRX-DUPLICATE",
        receipt_image=_receipt(),
    )
    approve_topup(first, admin_user)

    with pytest.raises(BusinessRuleViolation, match="already been credited"):
        request_topup(
            other_buyer,
            amount=Decimal("5000.00"),
            method="BANK",
            transaction_reference="trx-duplicate",
            receipt_image=_receipt(),
        )


def test_the_same_pending_reference_is_not_resubmitted(buyer):
    request_topup(
        buyer,
        amount=Decimal("5000.00"),
        method="BANK",
        transaction_reference="TRX-PENDING",
        receipt_image=_receipt(),
    )

    with pytest.raises(BusinessRuleViolation, match="awaiting review"):
        request_topup(
            buyer,
            amount=Decimal("5000.00"),
            method="BANK",
            transaction_reference="TRX-PENDING",
            receipt_image=_receipt(),
        )


def test_a_topup_cannot_be_approved_twice(buyer, admin_user):
    topup = request_topup(
        buyer,
        amount=Decimal("7000.00"),
        method="BANK",
        transaction_reference="TRX-ONCE",
        receipt_image=_receipt(),
    )
    approve_topup(topup, admin_user)

    with pytest.raises(BusinessRuleViolation, match="already been"):
        approve_topup(topup, admin_user)

    assert Wallet.objects.get(user=buyer).balance == Decimal("7000.00")


# ═══════════════════════════════════════════════════════════════════════════
# PROFILE
# ═══════════════════════════════════════════════════════════════════════════
def test_buyer_updates_preferences(buyer, category):
    profile = update_buyer_profile(
        buyer,
        preferred_categories=[category],
        budget_min=Decimal("20000.00"),
        budget_max=Decimal("90000.00"),
    )

    assert list(profile.preferred_categories.all()) == [category]
    assert profile.budget_max == Decimal("90000.00")


def test_photographer_can_pause_bookings(photographer):
    """
    Module 7 reads this on every booking attempt. A photographer with no way
    to pause has to decline by hand, and declines count against them.
    """
    update_photographer_profile(photographer, is_accepting_bookings=False)
    photographer.refresh_from_db()
    assert photographer.is_accepting_bookings is False


def test_a_suspended_photographer_cannot_re_enable_bookings(photographer):
    photographer.is_approved = False
    photographer.save(update_fields=["is_approved"])

    with pytest.raises(BusinessRuleViolation, match="not active"):
        update_photographer_profile(photographer, is_accepting_bookings=True)


# ═══════════════════════════════════════════════════════════════════════════
# API
# ═══════════════════════════════════════════════════════════════════════════
ME = "/api/v1/profiles/me/"


def test_buyer_reads_their_own_profile(buyer_client):
    body = buyer_client.get(ME).json()["data"]
    assert body["full_name"] == "Ayesha Khan"
    assert body["wallet_balance"] == "0.00"


def test_photographer_reads_their_own_profile(photographer_client, photographer):
    body = photographer_client.get(ME).json()["data"]

    assert body["business_name"] == "Hamza Studio"
    # Only the owner sees these two.
    assert "total_earnings" in body
    assert body["is_approved"] is True


def test_photographer_cannot_approve_themselves(photographer_client, photographer):
    """
    The writable serializer omits `is_approved` entirely, so the field is
    ignored rather than honoured.
    """
    photographer.is_approved = False
    photographer.save(update_fields=["is_approved"])

    response = photographer_client.patch(
        f"{ME}update/",
        {"is_approved": True, "is_featured": True, "tagline": "Weddings, done right"},
        format="json",
    )

    photographer.refresh_from_db()
    assert response.status_code == 200
    assert photographer.is_approved is False
    assert photographer.is_featured is False
    assert photographer.tagline == "Weddings, done right"


def test_wallet_endpoint(buyer_client, buyer):
    credit_wallet(buyer, Decimal("2500.00"), txn_type=WalletTransactionType.TOPUP)
    body = buyer_client.get(f"{ME}wallet/").json()["data"]

    assert body["balance"] == "2500.00"
    assert len(body["recent_transactions"]) == 1
    assert body["recent_transactions"][0]["direction"] == "in"


def test_transactions_are_directional(buyer_client, buyer):
    credit_wallet(buyer, Decimal("2500.00"), txn_type=WalletTransactionType.TOPUP)
    debit_wallet(buyer, Decimal("500.00"), txn_type=WalletTransactionType.PURCHASE)

    rows = buyer_client.get(f"{ME}wallet/transactions/").json()["data"]
    assert {r["direction"] for r in rows} == {"in", "out"}


def test_topup_request_over_http(buyer_client, buyer):
    response = buyer_client.post(
        f"{ME}wallet/topups/request/",
        {
            "amount": "15000.00",
            "method": "EASYPAISA",
            "transaction_reference": "EP-4455667788",
            "receipt_image": _receipt(),
        },
        format="multipart",
    )

    assert response.status_code == 201
    assert response.json()["data"]["status"] == "PENDING"
    assert Wallet.objects.get(user=buyer).balance == Decimal("0.00")


def test_a_tiny_topup_is_refused(buyer_client):
    response = buyer_client.post(
        f"{ME}wallet/topups/request/",
        {
            "amount": "50.00",
            "method": "BANK",
            "transaction_reference": "TRX-SMALL",
            "receipt_image": _receipt(),
        },
        format="multipart",
    )
    assert response.status_code == 400
    assert "minimum" in response.json()["message"].lower()


def test_wallet_is_private(other_buyer_client, buyer):
    credit_wallet(buyer, Decimal("2500.00"), txn_type=WalletTransactionType.TOPUP)
    body = other_buyer_client.get(f"{ME}wallet/").json()["data"]

    assert body["balance"] == "0.00"


def test_anonymous_cannot_read_a_profile(api_client):
    assert api_client.get(ME).status_code == 401
    assert api_client.get(f"{ME}wallet/").status_code == 401
