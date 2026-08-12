"""
Portfolio: the photographer's actual work.

WHY IMAGES AND VIDEOS ARE SEPARATE MODELS
-----------------------------------------
They share almost no columns that matter. An image has width/height and three
generated thumbnail sizes; a video has a duration, a poster frame and a
provider (uploaded vs YouTube/Vimeo embed). A single polymorphic `Media` table
would be half-empty in both directions and would force every query to filter
on a `type` column.
"""

from django.db import models

from apps.core.models import BaseModel, TimeStampedModel
from apps.core.utils import upload_to


class PortfolioAlbum(BaseModel):
    """A themed collection — "Ayesha & Hamza — Lahore Wedding"."""

    photographer = models.ForeignKey(
        "profiles.PhotographerProfile", on_delete=models.CASCADE, related_name="albums"
    )
    category = models.ForeignKey(
        "catalog.Category", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="albums",
    )

    title = models.CharField(max_length=140)
    description = models.TextField(blank=True, max_length=2000)
    cover_image = models.ImageField(
        upload_to=upload_to("albums"), null=True, blank=True
    )

    shoot_date = models.DateField(null=True, blank=True)
    location = models.CharField(max_length=140, blank=True)
    client_name = models.CharField(
        max_length=120, blank=True,
        help_text="Only shown if the client consented.",
    )

    is_public = models.BooleanField(default=True, db_index=True)
    is_featured = models.BooleanField(default=False)
    display_order = models.PositiveSmallIntegerField(default=0)

    image_count = models.PositiveIntegerField(default=0)
    view_count = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "portfolio_albums"
        ordering = ("display_order", "-created_at")
        indexes = [
            models.Index(
                fields=["photographer", "is_public"], name="idx_album_by_photog"
            ),
        ]

    def __str__(self) -> str:
        return self.title


class PortfolioImage(BaseModel):
    photographer = models.ForeignKey(
        "profiles.PhotographerProfile", on_delete=models.CASCADE,
        related_name="portfolio_images",
    )
    album = models.ForeignKey(
        PortfolioAlbum, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="images",
    )
    category = models.ForeignKey(
        "catalog.Category", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="portfolio_images",
    )

    # Three sizes are generated on upload. The mobile grid loads `thumbnail`
    # (≈20KB); the full-screen viewer loads `image_large` only when tapped.
    # Serving the original everywhere is the single biggest cause of slow
    # portfolio screens on 3G.
    image = models.ImageField(upload_to=upload_to("portfolio"))
    thumbnail = models.ImageField(
        upload_to=upload_to("portfolio/thumbs"), null=True, blank=True
    )
    image_large = models.ImageField(
        upload_to=upload_to("portfolio/large"), null=True, blank=True
    )

    caption = models.CharField(max_length=200, blank=True)
    alt_text = models.CharField(
        max_length=200, blank=True, help_text="Accessibility description."
    )

    width = models.PositiveSmallIntegerField(default=0)
    height = models.PositiveSmallIntegerField(default=0)
    file_size_kb = models.PositiveIntegerField(default=0)

    is_featured = models.BooleanField(default=False, db_index=True)
    display_order = models.PositiveSmallIntegerField(default=0)

    view_count = models.PositiveIntegerField(default=0)
    like_count = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "portfolio_images"
        ordering = ("display_order", "-created_at")
        indexes = [
            models.Index(
                fields=["photographer", "is_featured"], name="idx_image_featured"
            ),
            models.Index(fields=["album", "display_order"], name="idx_image_in_album"),
        ]

    def __str__(self) -> str:
        return self.caption or f"Image #{self.pk}"

    @property
    def aspect_ratio(self) -> float:
        return round(self.width / self.height, 3) if self.height else 1.0


class VideoProvider(models.TextChoices):
    UPLOADED = "UPLOADED", "Uploaded to SnapSphere"
    YOUTUBE = "YOUTUBE", "YouTube"
    VIMEO = "VIMEO", "Vimeo"


class PortfolioVideo(BaseModel):
    photographer = models.ForeignKey(
        "profiles.PhotographerProfile", on_delete=models.CASCADE,
        related_name="portfolio_videos",
    )
    album = models.ForeignKey(
        PortfolioAlbum, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="videos",
    )

    title = models.CharField(max_length=140)
    description = models.TextField(blank=True, max_length=1000)

    provider = models.CharField(
        max_length=16, choices=VideoProvider.choices, default=VideoProvider.UPLOADED
    )
    # Embeds keep 100MB files off our storage bill for photographers who
    # already host showreels elsewhere.
    video_file = models.FileField(
        upload_to=upload_to("videos"), null=True, blank=True
    )
    external_url = models.URLField(blank=True)
    poster_image = models.ImageField(
        upload_to=upload_to("videos/posters"), null=True, blank=True
    )

    duration_seconds = models.PositiveIntegerField(default=0)
    file_size_mb = models.DecimalField(
        max_digits=7, decimal_places=2, default=0, blank=True
    )

    is_featured = models.BooleanField(default=False)
    display_order = models.PositiveSmallIntegerField(default=0)
    view_count = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "portfolio_videos"
        ordering = ("display_order", "-created_at")
        constraints = [
            # Either an uploaded file or an external URL — never neither.
            models.CheckConstraint(
                check=(
                    models.Q(provider="UPLOADED", video_file__isnull=False)
                    | (~models.Q(provider="UPLOADED") & ~models.Q(external_url=""))
                ),
                name="ck_video_source_present",
            )
        ]

    def __str__(self) -> str:
        return self.title


class PortfolioImageLike(TimeStampedModel):
    """
    Lightweight engagement signal.

    Feeds `portfolio_score`, which is one of the ranking model's features —
    the equivalent of `Portfolio_Interactions` in the service_*.csv datasets.
    """

    image = models.ForeignKey(
        PortfolioImage, on_delete=models.CASCADE, related_name="likes"
    )
    user = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="liked_images"
    )

    class Meta:
        db_table = "portfolio_image_likes"
        constraints = [
            models.UniqueConstraint(
                fields=["image", "user"], name="uniq_like_per_user_image"
            )
        ]
