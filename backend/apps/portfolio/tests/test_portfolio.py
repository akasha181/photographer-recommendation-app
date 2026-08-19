"""
Module 6 — portfolio upload.

The privacy property is the one worth pinning: a phone photo carries GPS in
its EXIF, and a portfolio publishes it to the world. Upload must strip it.
"""

import io

import pytest
from PIL import Image

from apps.core.exceptions import BusinessRuleViolation
from apps.portfolio.models import PortfolioAlbum, PortfolioImage
from apps.portfolio.services import (
    MAX_FEATURED_IMAGES,
    delete_album,
    toggle_featured,
    upload_image,
)

pytestmark = pytest.mark.django_db

URL = "/api/v1/portfolio/me/"


def make_upload(name="shot.jpg", size=(1200, 800), with_gps=True):
    """A JPEG carrying GPS EXIF, the way a phone camera produces one."""
    from django.core.files.uploadedfile import SimpleUploadedFile

    image = Image.new("RGB", size, (120, 90, 60))
    buffer = io.BytesIO()

    if with_gps:
        # 0x8825 is the GPS IFD pointer; Pillow writes it into the JPEG's APP1.
        exif = image.getexif()
        exif[0x8825] = {1: "N", 2: (33, 41, 0)}
        exif[0x010F] = "TestPhone"
        image.save(buffer, format="JPEG", exif=exif)
    else:
        image.save(buffer, format="JPEG")

    buffer.seek(0)
    return SimpleUploadedFile(name, buffer.read(), content_type="image/jpeg")


# ═══════════════════════════════════════════════════════════════════════════
# THE PRIVACY GUARANTEE
# ═══════════════════════════════════════════════════════════════════════════
def test_upload_strips_exif(photographer):
    """
    A newborn shoot at somebody's home embeds their coordinates. Publishing
    that is a privacy incident, not a missed optimisation.
    """
    row = upload_image(photographer, image=make_upload(with_gps=True))

    row.image.open()
    stored = Image.open(row.image)
    assert dict(stored.getexif()) == {}


def test_upload_generates_three_sizes(photographer):
    """
    The grid loads the thumbnail, the viewer loads large. Serving one size
    everywhere is the biggest cause of slow portfolio screens on 3G.
    """
    row = upload_image(photographer, image=make_upload(size=(2400, 1600)))

    assert row.image and row.thumbnail and row.image_large
    assert row.thumbnail.name != row.image.name != row.image_large.name

    row.thumbnail.open()
    assert max(Image.open(row.thumbnail).size) <= 320
    row.image_large.open()
    assert max(Image.open(row.image_large).size) <= 1600


def test_upload_records_the_original_dimensions(photographer):
    row = upload_image(photographer, image=make_upload(size=(1600, 900)))
    assert (row.width, row.height) == (1600, 900)
    assert row.aspect_ratio == round(1600 / 900, 3)


# ═══════════════════════════════════════════════════════════════════════════
# UPLOAD OVER HTTP
# ═══════════════════════════════════════════════════════════════════════════
def test_upload_over_http(photographer_client, photographer):
    response = photographer_client.post(
        URL,
        {"image": make_upload(), "caption": "Nikah at Serena"},
        format="multipart",
    )

    assert response.status_code == 201
    body = response.json()["data"]
    assert body["caption"] == "Nikah at Serena"
    assert body["thumbnail_url"] and body["image_large_url"]


def test_caption_becomes_the_alt_text_when_none_is_given(photographer_client):
    """An image with no alt text is invisible to a screen reader."""
    body = photographer_client.post(
        URL, {"image": make_upload(), "caption": "Bride at golden hour"},
        format="multipart",
    ).json()["data"]

    assert body["alt_text"] == "Bride at golden hour"


def test_a_non_image_is_refused(photographer_client):
    from django.core.files.uploadedfile import SimpleUploadedFile

    response = photographer_client.post(
        URL,
        {"image": SimpleUploadedFile("notes.txt", b"hello", content_type="text/plain")},
        format="multipart",
    )
    assert response.status_code == 400


def test_an_oversized_image_is_refused(photographer, settings):
    settings.MAX_IMAGE_SIZE_MB = 0.0001
    from apps.core.exceptions import FileTooLarge

    with pytest.raises(FileTooLarge, match="The limit is"):
        upload_image(photographer, image=make_upload())


def test_the_portfolio_cap(photographer, monkeypatch):
    from apps.portfolio import services as portfolio_services

    monkeypatch.setattr(portfolio_services, "MAX_IMAGES_PER_PHOTOGRAPHER", 2)
    upload_image(photographer, image=make_upload())
    upload_image(photographer, image=make_upload())

    with pytest.raises(BusinessRuleViolation, match="Remove some"):
        upload_image(photographer, image=make_upload())


# ═══════════════════════════════════════════════════════════════════════════
# FEATURING & ORDERING
# ═══════════════════════════════════════════════════════════════════════════
def test_feature_toggles(photographer_client, photographer):
    image = upload_image(photographer, image=make_upload())

    on = photographer_client.post(f"{URL}{image.pk}/feature/", {}, format="json")
    assert on.json()["data"]["is_featured"] is True

    off = photographer_client.post(f"{URL}{image.pk}/feature/", {}, format="json")
    assert off.json()["data"]["is_featured"] is False


def test_the_featured_cap(photographer):
    """"Everything is featured" means nothing is."""
    images = [
        upload_image(photographer, image=make_upload(), is_featured=True)
        for _ in range(MAX_FEATURED_IMAGES)
    ]
    assert all(i.is_featured for i in images)

    extra = upload_image(photographer, image=make_upload())
    with pytest.raises(BusinessRuleViolation, match="Unfeature one"):
        toggle_featured(extra)


def test_reorder(photographer_client, photographer):
    images = [upload_image(photographer, image=make_upload()) for _ in range(3)]
    reversed_ids = [i.pk for i in reversed(images)]

    response = photographer_client.post(
        f"{URL}reorder/", {"image_ids": reversed_ids}, format="json"
    )

    assert response.status_code == 200
    for position, image_id in enumerate(reversed_ids):
        assert PortfolioImage.objects.get(pk=image_id).display_order == position


def test_reorder_ignores_ids_that_are_not_yours(
    photographer, other_photographer
):
    """A stale client must not lose the whole reordering over one bad id."""
    from apps.portfolio.services import reorder_images

    mine = upload_image(photographer, image=make_upload())
    theirs = upload_image(other_photographer, image=make_upload())

    updated = reorder_images(photographer, [theirs.pk, mine.pk])
    theirs.refresh_from_db()

    assert updated == 1
    assert theirs.display_order == 0  # untouched


# ═══════════════════════════════════════════════════════════════════════════
# ALBUMS
# ═══════════════════════════════════════════════════════════════════════════
def test_create_an_album(photographer_client):
    response = photographer_client.post(
        f"{URL}albums/create/",
        {"title": "Ayesha & Hamza — Lahore", "location": "Lahore", "is_public": True},
        format="json",
    )
    assert response.status_code == 201
    assert response.json()["data"]["title"] == "Ayesha & Hamza — Lahore"


def test_album_image_count_stays_in_sync(photographer, photographer_client):
    album = PortfolioAlbum.objects.create(photographer=photographer, title="Wedding")
    upload_image(photographer, image=make_upload(), album=album)
    upload_image(photographer, image=make_upload(), album=album)

    album.refresh_from_db()
    assert album.image_count == 2


def test_deleting_an_album_keeps_its_images(photographer):
    """
    There is no undo on this screen. Losing an evening's uploads because a
    folder was tidied away would be the wrong default.
    """
    album = PortfolioAlbum.objects.create(photographer=photographer, title="Wedding")
    image = upload_image(photographer, image=make_upload(), album=album)

    delete_album(album)
    image.refresh_from_db()

    assert PortfolioImage.objects.filter(pk=image.pk, is_deleted=False).exists()
    assert image.album_id is None


def test_uploading_into_someone_elses_album_is_refused(
    photographer, other_photographer
):
    album = PortfolioAlbum.objects.create(
        photographer=other_photographer, title="Not yours"
    )
    with pytest.raises(BusinessRuleViolation, match="not yours"):
        upload_image(photographer, image=make_upload(), album=album)


# ═══════════════════════════════════════════════════════════════════════════
# VISIBILITY & SCOPING
# ═══════════════════════════════════════════════════════════════════════════
def test_private_album_images_are_hidden_from_buyers(api_client, photographer):
    private = PortfolioAlbum.objects.create(
        photographer=photographer, title="Client only", is_public=False
    )
    upload_image(photographer, image=make_upload(), album=private)
    upload_image(photographer, image=make_upload())  # loose, so public

    rows = api_client.get(
        f"/api/v1/portfolio/photographers/{photographer.pk}/images/"
    ).json()["data"]

    assert len(rows) == 1


def test_deleting_an_image_removes_it_from_the_public_grid(
    api_client, photographer_client, photographer
):
    image = upload_image(photographer, image=make_upload())
    photographer_client.delete(f"{URL}{image.pk}/")

    rows = api_client.get(
        f"/api/v1/portfolio/photographers/{photographer.pk}/images/"
    ).json()["data"]
    assert rows == []


def test_a_photographer_cannot_touch_another_portfolio(
    photographer_client, other_photographer
):
    theirs = upload_image(other_photographer, image=make_upload())

    assert photographer_client.patch(
        f"{URL}{theirs.pk}/", {"caption": "mine now"}, format="json"
    ).status_code == 404
    assert photographer_client.delete(f"{URL}{theirs.pk}/").status_code == 404
    assert photographer_client.post(
        f"{URL}{theirs.pk}/feature/", {}, format="json"
    ).status_code == 404


def test_summary_counts(photographer_client, photographer):
    upload_image(photographer, image=make_upload(), is_featured=True)
    upload_image(photographer, image=make_upload())
    PortfolioAlbum.objects.create(photographer=photographer, title="Album")

    body = photographer_client.get(f"{URL}summary/").json()["data"]
    assert body == {"images": 2, "featured": 1, "albums": 1, "videos": 0}


def test_portfolio_score_follows_uploads(photographer):
    before = photographer.portfolio_score
    upload_image(photographer, image=make_upload())
    photographer.refresh_from_db()

    assert photographer.portfolio_score > before


def test_liking_an_image(buyer_client, photographer, buyer):
    image = upload_image(photographer, image=make_upload())
    path = f"/api/v1/portfolio/photographers/images/{image.pk}/like/"

    liked = buyer_client.post(path, {}, format="json").json()["data"]
    assert liked == {"is_liked": True, "like_count": 1}

    unliked = buyer_client.post(path, {}, format="json").json()["data"]
    assert unliked == {"is_liked": False, "like_count": 0}


def test_a_buyer_has_no_portfolio_editor(buyer_client):
    assert buyer_client.get(URL).status_code == 403


def test_anonymous_is_refused(api_client):
    assert api_client.get(URL).status_code == 401
