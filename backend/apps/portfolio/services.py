"""
Portfolio writes — Module 6.

WHAT UPLOAD ACTUALLY DOES
-------------------------
An uploaded phone photo is 4-8 MB and carries EXIF, including GPS. Storing it
as-is would mean a portfolio grid that downloads 200 MB on 3G, and — far worse
— publishing the exact coordinates of a newborn shoot at somebody's home.

`core.utils.process_image` re-encodes from raw pixel data (which discards every
metadata block) into WebP at three sizes. The grid loads `thumbnail` (~20 KB),
the full-screen viewer loads `image_large` only when tapped, and the original
is never served.
"""

import logging

from django.db import transaction
from django.db.models import F

from apps.core.exceptions import BusinessRuleViolation, FileTooLarge, UnsupportedMediaType
from apps.portfolio.models import PortfolioAlbum, PortfolioImage

logger = logging.getLogger("snapsphere")

#: Past this a grid is a dump, not a portfolio, and the profile screen's
#: prefetch starts costing real time.
MAX_IMAGES_PER_PHOTOGRAPHER = 200
MAX_FEATURED_IMAGES = 12


@transaction.atomic
def upload_image(
    photographer,
    *,
    image,
    caption: str = "",
    alt_text: str = "",
    album: PortfolioAlbum | None = None,
    category=None,
    is_featured: bool = False,
) -> PortfolioImage:
    """Validate, strip metadata, generate three sizes, store."""
    from django.conf import settings

    from apps.core.utils import process_image

    _assert_within_quota(photographer)
    _assert_acceptable(image, settings)

    if album is not None and album.photographer_id != photographer.pk:
        raise BusinessRuleViolation("That album is not yours.")

    # Read dimensions before processing — `process_image` rewinds and re-encodes.
    from PIL import Image as PILImage

    with PILImage.open(image) as probe:
        width, height = probe.size
    image.seek(0)

    row = PortfolioImage(
        photographer=photographer,
        album=album,
        category=category or (album.category if album else None),
        caption=caption.strip()[:200],
        alt_text=(alt_text or caption).strip()[:200],
        width=width,
        height=height,
        file_size_kb=int(getattr(image, "size", 0) / 1024),
        is_featured=is_featured and _featured_slots_left(photographer) > 0,
    )

    # Three renditions from one upload. Each call re-opens the source, so the
    # file is rewound between them.
    # NOTE the key is "thumb", not "thumbnail" — see THUMBNAIL_SIZES in
    # core/utils.py. The model field and the size key differ.
    for field, size_key in (
        ("image", "medium"),
        ("thumbnail", "thumb"),
        ("image_large", "large"),
    ):
        image.seek(0)
        processed = process_image(image, size_key=size_key)
        getattr(row, field).save(processed.name, processed, save=False)

    row.save()
    _sync_album_count(album)
    _refresh_portfolio_score(photographer)

    logger.info(
        "Portfolio image uploaded",
        extra={"photographer_id": photographer.pk, "image_id": row.pk},
    )
    return row


@transaction.atomic
def update_image(image: PortfolioImage, **data) -> PortfolioImage:
    album = data.get("album")
    if album is not None and album.photographer_id != image.photographer_id:
        raise BusinessRuleViolation("That album is not yours.")

    previous_album = image.album
    for field, value in data.items():
        setattr(image, field, value)
    image.save()

    if previous_album != image.album:
        _sync_album_count(previous_album)
        _sync_album_count(image.album)
    return image


@transaction.atomic
def toggle_featured(image: PortfolioImage) -> PortfolioImage:
    """
    Featured images are what the profile screen shows first.

    Capped, because "everything is featured" means nothing is — and the detail
    endpoint only prefetches the first twelve anyway.
    """
    if not image.is_featured and _featured_slots_left(image.photographer) <= 0:
        raise BusinessRuleViolation(
            f"You can feature up to {MAX_FEATURED_IMAGES} images. "
            f"Unfeature one to make room."
        )

    image.is_featured = not image.is_featured
    image.save(update_fields=["is_featured", "updated_at"])
    _refresh_portfolio_score(image.photographer)
    return image


@transaction.atomic
def delete_image(image: PortfolioImage) -> None:
    """
    Soft delete — `PortfolioImage` extends BaseModel, so `.delete()` flips the
    flag. Likes and album counts stay consistent because nothing is removed.
    """
    album, photographer = image.album, image.photographer
    image.delete()
    _sync_album_count(album)
    _refresh_portfolio_score(photographer)


@transaction.atomic
def reorder_images(photographer, ordered_ids: list[int]) -> int:
    """
    Apply a drag-and-drop order in one request.

    Ids that are not this photographer's are ignored rather than rejected: a
    stale client sending one id it should not have must not lose the user's
    whole reordering.
    """
    owned = set(
        PortfolioImage.objects.filter(
            photographer=photographer, pk__in=ordered_ids, is_deleted=False
        ).values_list("pk", flat=True)
    )
    updated = 0
    for position, image_id in enumerate(ordered_ids):
        if image_id in owned:
            PortfolioImage.objects.filter(pk=image_id).update(display_order=position)
            updated += 1
    return updated


# ═══════════════════════════════════════════════════════════════════════════
# ALBUMS
# ═══════════════════════════════════════════════════════════════════════════
@transaction.atomic
def create_album(photographer, **data) -> PortfolioAlbum:
    return PortfolioAlbum.objects.create(photographer=photographer, **data)


@transaction.atomic
def update_album(album: PortfolioAlbum, **data) -> PortfolioAlbum:
    for field, value in data.items():
        setattr(album, field, value)
    album.save()
    return album


@transaction.atomic
def delete_album(album: PortfolioAlbum) -> None:
    """
    Deleting an album does NOT delete its images.

    `PortfolioImage.album` is `SET_NULL`, so the photos survive as loose
    uploads. Losing an evening's work because a folder was tidied away would
    be the wrong default, and there is no undo on this screen.
    """
    album.images.update(album=None)
    album.delete()


# ═══════════════════════════════════════════════════════════════════════════
# INTERNALS
# ═══════════════════════════════════════════════════════════════════════════
def _assert_within_quota(photographer) -> None:
    count = PortfolioImage.objects.filter(
        photographer=photographer, is_deleted=False
    ).count()
    if count >= MAX_IMAGES_PER_PHOTOGRAPHER:
        raise BusinessRuleViolation(
            f"Your portfolio holds {MAX_IMAGES_PER_PHOTOGRAPHER} images. "
            f"Remove some to upload more."
        )


def _assert_acceptable(upload, settings) -> None:
    content_type = getattr(upload, "content_type", "") or ""
    if content_type not in settings.ALLOWED_IMAGE_TYPES:
        raise UnsupportedMediaType(
            f"Upload a JPEG, PNG or WebP image. That file is {content_type or 'unknown'}."
        )

    size_mb = getattr(upload, "size", 0) / (1024 * 1024)
    if size_mb > settings.MAX_IMAGE_SIZE_MB:
        raise FileTooLarge(
            f"That image is {size_mb:.1f} MB. The limit is "
            f"{settings.MAX_IMAGE_SIZE_MB} MB — most phones can export smaller."
        )


def _featured_slots_left(photographer) -> int:
    used = PortfolioImage.objects.filter(
        photographer=photographer, is_featured=True, is_deleted=False
    ).count()
    return MAX_FEATURED_IMAGES - used


def _sync_album_count(album: PortfolioAlbum | None) -> None:
    if album is None:
        return
    PortfolioAlbum.objects.filter(pk=album.pk).update(
        image_count=PortfolioImage.objects.filter(
            album=album, is_deleted=False
        ).count()
    )


def _refresh_portfolio_score(photographer) -> None:
    """
    `portfolio_score` is a ranking feature (0-999).

    Composed from volume and engagement rather than stored raw, so a
    photographer with 3 stunning images is not permanently outranked by one
    who uploaded 200 snapshots — the like count carries more weight per item.
    """
    from django.db.models import Sum

    agg = PortfolioImage.objects.filter(
        photographer=photographer, is_deleted=False
    ).aggregate(total=Sum("like_count"), views=Sum("view_count"))

    count = PortfolioImage.objects.filter(
        photographer=photographer, is_deleted=False
    ).count()

    score = min(999, count * 3 + (agg["total"] or 0) * 5 + (agg["views"] or 0) // 10)
    photographer.portfolio_score = score
    photographer.save(update_fields=["portfolio_score", "updated_at"])


@transaction.atomic
def toggle_like(user, image: PortfolioImage) -> bool:
    """Engagement signal feeding `portfolio_score`. Returns the new state."""
    from apps.portfolio.models import PortfolioImageLike

    existing = PortfolioImageLike.objects.filter(image=image, user=user).first()
    if existing is not None:
        existing.delete()
        PortfolioImage.objects.filter(pk=image.pk, like_count__gt=0).update(
            like_count=F("like_count") - 1
        )
        _refresh_portfolio_score(image.photographer)
        return False

    PortfolioImageLike.objects.create(image=image, user=user)
    PortfolioImage.objects.filter(pk=image.pk).update(like_count=F("like_count") + 1)
    _refresh_portfolio_score(image.photographer)
    return True
