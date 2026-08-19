"""
Read-side queries for portfolios.

The public and owner paths are separate on purpose. `public_images` hides
albums a photographer marked private; `own_images` shows everything, because
the owner needs to see the drafts in order to publish them.
"""

from __future__ import annotations

from django.db.models import QuerySet

from apps.portfolio.models import PortfolioAlbum, PortfolioImage, PortfolioVideo


def public_images(photographer) -> QuerySet[PortfolioImage]:
    """
    What a buyer sees, featured first.

    An image in a private album is excluded; one with no album at all is
    public, because "loose" uploads are the common case and defaulting them to
    hidden would make a new photographer's grid look empty after they just
    filled it.
    """
    return (
        PortfolioImage.objects.filter(photographer=photographer, is_deleted=False)
        .exclude(album__is_public=False)
        .select_related("album", "category")
        .order_by("-is_featured", "display_order", "-created_at")
    )


def own_images(photographer) -> QuerySet[PortfolioImage]:
    return (
        PortfolioImage.objects.filter(photographer=photographer, is_deleted=False)
        .select_related("album", "category")
        .order_by("-is_featured", "display_order", "-created_at")
    )


def get_own_image(photographer, image_id: int) -> PortfolioImage | None:
    """Scoped to the owner — someone else's image is a 404, not a 403."""
    return own_images(photographer).filter(pk=image_id).first()


def own_albums(photographer) -> QuerySet[PortfolioAlbum]:
    return (
        PortfolioAlbum.objects.filter(photographer=photographer, is_deleted=False)
        .select_related("category")
        .order_by("display_order", "-created_at")
    )


def get_own_album(photographer, album_id: int) -> PortfolioAlbum | None:
    return own_albums(photographer).filter(pk=album_id).first()


def public_videos(photographer) -> QuerySet[PortfolioVideo]:
    return (
        PortfolioVideo.objects.filter(photographer=photographer, is_deleted=False)
        .exclude(album__is_public=False)
        .order_by("-is_featured", "display_order")
    )


def portfolio_summary(photographer) -> dict:
    """Counts for the tab header."""
    images = own_images(photographer)
    return {
        "images": images.count(),
        "featured": images.filter(is_featured=True).count(),
        "albums": own_albums(photographer).count(),
        "videos": PortfolioVideo.objects.filter(
            photographer=photographer, is_deleted=False
        ).count(),
    }
