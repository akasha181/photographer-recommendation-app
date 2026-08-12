"""
The download flow, and the storage guarantee it depends on.

A digital product is worthless the moment its file URL leaks, so these tests
are less about happy paths than about proving the four things that must never
happen: a public URL, a reused token, an expired token, and downloading
something you did not buy.
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.core.exceptions import BusinessRuleViolation, ResourceGone
from apps.marketplace.models import DownloadToken
from apps.marketplace.services import (
    add_to_cart,
    checkout,
    issue_download_token,
    redeem_download_token,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def purchase(funded_buyer, product):
    add_to_cart(funded_buyer, product)
    order = checkout(funded_buyer)
    return order.items.first()


# ═══════════════════════════════════════════════════════════════════════════
# THE STORAGE GUARANTEE
# ═══════════════════════════════════════════════════════════════════════════
def test_product_files_live_outside_public_media(product):
    """
    The bug this pins: `ProductFile.file` was a plain FileField, so paid
    assets landed in MEDIA_ROOT and were served at a guessable URL, and the
    whole token flow guarded a door with no wall beside it.
    """
    from django.conf import settings

    product_file = product.files.first()
    stored = product_file.file.storage.path(product_file.file.name)

    assert str(settings.PRIVATE_MEDIA_ROOT) in stored
    assert str(settings.MEDIA_ROOT) not in stored


def test_asking_a_private_file_for_a_url_raises(product):
    """
    Returning a dead `/media/…` path would be worse than raising: it looks
    valid in a JSON response and ships.
    """
    with pytest.raises(ValueError, match="no public URL"):
        product.files.first().file.url


def test_the_api_never_serialises_a_file_path(buyer_client, product):
    response = buyer_client.get(f"/api/v1/marketplace/products/{product.slug}/")
    body = response.json()["data"]

    assert response.status_code == 200
    assert body["files"], "the manifest should list the files"
    for entry in body["files"]:
        assert set(entry) == {"id", "name", "file_size_mb", "display_order"}
        assert "file" not in entry and "url" not in entry


# ═══════════════════════════════════════════════════════════════════════════
# ISSUING
# ═══════════════════════════════════════════════════════════════════════════
def test_issues_a_token_for_an_owned_file(funded_buyer, purchase, product):
    token = issue_download_token(funded_buyer, purchase, product.files.first())

    assert token.is_valid
    assert token.used_at is None
    assert token.expires_at > timezone.now()


def test_issuing_consumes_a_download(funded_buyer, purchase, product):
    """
    The counter moves when the ticket is issued, not when the bytes finish.
    Counting on completion sounds fairer but is unenforceable — a client that
    disconnects at 99% still has the file.
    """
    before = purchase.downloads_remaining
    issue_download_token(funded_buyer, purchase, product.files.first())
    purchase.refresh_from_db()

    assert purchase.download_count == 1
    assert purchase.downloads_remaining == before - 1


def test_download_cap_is_enforced(funded_buyer, purchase, product):
    from django.conf import settings

    product_file = product.files.first()
    for _ in range(settings.MAX_DOWNLOADS_PER_PURCHASE):
        issue_download_token(funded_buyer, purchase, product_file)

    purchase.refresh_from_db()
    with pytest.raises(BusinessRuleViolation, match="used all"):
        issue_download_token(funded_buyer, purchase, product_file)


def test_cannot_download_someone_elses_purchase(other_buyer, purchase, product):
    with pytest.raises(BusinessRuleViolation, match="not yours"):
        issue_download_token(other_buyer, purchase, product.files.first())


def test_cannot_download_a_file_from_another_product(
    funded_buyer, purchase, second_product, photographer
):
    from django.core.files.base import ContentFile

    from apps.marketplace.models import ProductFile

    foreign = ProductFile(product=second_product, name="other.cube")
    foreign.file.save("other.cube", ContentFile(b"x"), save=False)
    foreign.save()

    with pytest.raises(BusinessRuleViolation, match="not part of this purchase"):
        issue_download_token(funded_buyer, purchase, foreign)


# ═══════════════════════════════════════════════════════════════════════════
# REDEEMING
# ═══════════════════════════════════════════════════════════════════════════
def test_a_token_works_exactly_once(funded_buyer, purchase, product):
    token = issue_download_token(funded_buyer, purchase, product.files.first())

    redeemed = redeem_download_token(token.token, ip_address="127.0.0.1")
    assert redeemed.used_at is not None
    assert redeemed.ip_address == "127.0.0.1"

    with pytest.raises(ResourceGone, match="already been used"):
        redeem_download_token(token.token)


def test_an_expired_token_is_refused(funded_buyer, purchase, product):
    token = issue_download_token(funded_buyer, purchase, product.files.first())
    token.expires_at = timezone.now() - timedelta(seconds=1)
    token.save(update_fields=["expires_at"])

    with pytest.raises(ResourceGone, match="expired"):
        redeem_download_token(token.token)


def test_an_unknown_token_is_refused():
    with pytest.raises(ResourceGone, match="not valid"):
        redeem_download_token("this-was-never-issued")


# ═══════════════════════════════════════════════════════════════════════════
# OVER HTTP
# ═══════════════════════════════════════════════════════════════════════════
URL = "/api/v1/marketplace/"


def test_download_endpoint_returns_the_bytes(buyer_client, funded_buyer, purchase):
    response = buyer_client.post(
        f"{URL}orders/items/{purchase.pk}/download/", {}, format="json"
    )
    assert response.status_code == 200

    link = response.json()["data"]["download_url"]
    path = link.split("/api/v1")[1]

    streamed = buyer_client.get(f"/api/v1{path}")
    assert streamed.status_code == 200
    assert b"".join(streamed.streaming_content) == b"sample"


def test_the_download_link_dies_after_one_use(buyer_client, purchase):
    link = buyer_client.post(
        f"{URL}orders/items/{purchase.pk}/download/", {}, format="json"
    ).json()["data"]["download_url"]
    path = "/api/v1" + link.split("/api/v1")[1]

    assert buyer_client.get(path).status_code == 200
    assert buyer_client.get(path).status_code == 410


def test_nginx_handoff_when_x_accel_is_enabled(buyer_client, purchase, settings):
    """
    The production path. Gated on its own setting rather than `not DEBUG`,
    because a deployment without a reverse proxy would otherwise return an
    empty body — a failure invisible until a real buyer clicks download.
    """
    settings.PRIVATE_MEDIA_X_ACCEL = True

    link = buyer_client.post(
        f"{URL}orders/items/{purchase.pk}/download/", {}, format="json"
    ).json()["data"]["download_url"]
    path = "/api/v1" + link.split("/api/v1")[1]

    response = buyer_client.get(path)
    assert response.status_code == 200
    assert response["X-Accel-Redirect"].startswith("/protected/")
    assert "attachment" in response["Content-Disposition"]


def test_a_stranger_cannot_request_a_link(other_buyer_client, purchase):
    response = other_buyer_client.post(
        f"{URL}orders/items/{purchase.pk}/download/", {}, format="json"
    )
    assert response.status_code == 404


def test_purchases_endpoint_lists_what_is_owned(buyer_client, purchase, product):
    body = buyer_client.get(f"{URL}orders/purchases/").json()["data"]

    assert [row["product_title"] for row in body] == [product.title]
    assert body[0]["downloads_remaining"] == body[0]["max_downloads"]
    assert len(body[0]["files"]) == 2


def test_download_token_rows_are_kept_for_audit(funded_buyer, purchase, product):
    """Tokens are evidence of who downloaded what, so they are not deleted."""
    token = issue_download_token(funded_buyer, purchase, product.files.first())
    redeem_download_token(token.token)

    assert DownloadToken.objects.filter(pk=token.pk).exists()
