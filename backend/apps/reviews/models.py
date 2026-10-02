"""
Reviews and ratings.

THE INTEGRITY RULE, ENFORCED AT THREE LEVELS
--------------------------------------------
"Only a buyer with a completed booking may review that photographer."

  1. Serializer  — checks the booking exists, is COMPLETED, belongs to the
                   caller, and has no review yet. Gives a friendly error.
  2. Service     — re-checks inside the transaction. Catches races.
  3. Database    — OneToOneField on `booking` makes a second review for the
                   same booking physically impossible.

Level 3 is what makes review-bombing infeasible rather than merely discouraged:
to post N fake reviews an attacker must complete N real, paid bookings.
"""

from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.core.models import BaseModel, TimeStampedModel
from apps.core.utils import upload_to


class ReviewQuerySet(models.QuerySet):
    def visible(self):
        """Hidden reviews stay in the table but leave the public average."""
        return self.filter(is_hidden=False, is_deleted=False)

    def for_photographer(self, photographer_id):
        return self.visible().filter(photographer_id=photographer_id)

    def with_details(self):
        return self.select_related("buyer", "photographer", "booking").prefetch_related(
            "images", "reply"
        )


class Review(BaseModel):
    # ─── The proof of eligibility ────────────────────────────────────────────
    booking = models.OneToOneField(
        "bookings.Booking", on_delete=models.SET_NULL, related_name="review",
        null=True, blank=True,
        help_text="One review per completed booking, or null for direct reviews.",
    )
    buyer = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, related_name="reviews_written"
    )
    photographer = models.ForeignKey(
        "profiles.PhotographerProfile", on_delete=models.CASCADE,
        related_name="reviews",
    )

    # ─── Ratings ─────────────────────────────────────────────────────────────
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)], db_index=True
    )
    # Sub-ratings make the average actionable: a 3-star average is useless
    # feedback, but "5 for quality, 2 for punctuality" tells the photographer
    # exactly what to fix.
    rating_quality = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    rating_professionalism = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    rating_communication = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    rating_value = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    rating_punctuality = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(5)]
    )

    # ─── Content ─────────────────────────────────────────────────────────────
    title = models.CharField(max_length=140, blank=True)
    comment = models.TextField(max_length=3000, blank=True)

    # ─── AI-derived (Module 10) ──────────────────────────────────────────────
    sentiment = models.CharField(
        max_length=16, blank=True, db_index=True,
        choices=[("POSITIVE", "Positive"), ("NEUTRAL", "Neutral"), ("NEGATIVE", "Negative")],
        help_text="Predicted by the TF-IDF + LogisticRegression model trained "
                  "on yelp.csv. The labels in reviews_feedback.csv are noise "
                  "and are deliberately not used.",
    )
    sentiment_score = models.DecimalField(
        max_digits=4, decimal_places=3, null=True, blank=True,
        help_text="Model confidence 0.000-1.000.",
    )

    # ─── Moderation ──────────────────────────────────────────────────────────
    is_hidden = models.BooleanField(default=False, db_index=True)
    hidden_reason = models.CharField(max_length=200, blank=True)
    is_flagged = models.BooleanField(default=False)
    flag_count = models.PositiveSmallIntegerField(default=0)

    # ─── Engagement ──────────────────────────────────────────────────────────
    helpful_count = models.PositiveIntegerField(default=0)

    objects = ReviewQuerySet.as_manager()

    class Meta:
        db_table = "reviews"
        ordering = ("-created_at",)
        indexes = [
            models.Index(
                fields=["photographer", "is_hidden", "-created_at"],
                name="idx_review_public_list",
            ),
            models.Index(
                fields=["photographer", "-rating"], name="idx_review_by_rating"
            ),
            models.Index(fields=["buyer", "-created_at"], name="idx_review_by_buyer"),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(rating__gte=1) & models.Q(rating__lte=5),
                name="ck_review_rating_range",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.rating}★ for {self.photographer_id} by {self.buyer_id}"

    @property
    def has_reply(self) -> bool:
        return hasattr(self, "reply")

    @property
    def sub_rating_average(self) -> Decimal | None:
        subs = [
            self.rating_quality, self.rating_professionalism,
            self.rating_communication, self.rating_value, self.rating_punctuality,
        ]
        given = [s for s in subs if s is not None]
        if not given:
            return None
        return Decimal(f"{sum(given) / len(given):.2f}")


class ReviewImage(TimeStampedModel):
    """Buyer-uploaded proof shots — the strongest trust signal on a profile."""

    review = models.ForeignKey(Review, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to=upload_to("reviews"))
    thumbnail = models.ImageField(
        upload_to=upload_to("reviews/thumbs"), null=True, blank=True
    )
    caption = models.CharField(max_length=200, blank=True)

    class Meta:
        db_table = "review_images"


class ReviewReply(TimeStampedModel):
    """
    The photographer's public response.

    OneToOne, not ForeignKey: a review is not a comment thread. Allowing an
    unbounded back-and-forth in public turns disputes into spectacles — the
    chat module exists for the conversation.
    """

    review = models.OneToOneField(Review, on_delete=models.CASCADE, related_name="reply")
    photographer = models.ForeignKey(
        "profiles.PhotographerProfile", on_delete=models.CASCADE,
        related_name="review_replies",
    )
    comment = models.TextField(max_length=2000)
    is_edited = models.BooleanField(default=False)

    class Meta:
        db_table = "review_replies"

    def __str__(self) -> str:
        return f"Reply to review #{self.review_id}"


class ReviewHelpful(TimeStampedModel):
    """"Was this review helpful?" — one vote per user, enforced by the DB."""

    review = models.ForeignKey(
        Review, on_delete=models.CASCADE, related_name="helpful_votes"
    )
    user = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="helpful_votes"
    )

    class Meta:
        db_table = "review_helpful_votes"
        constraints = [
            models.UniqueConstraint(
                fields=["review", "user"], name="uniq_helpful_vote_per_user"
            )
        ]


class ProductReview(BaseModel):
    """
    Review of a marketplace product.

    Kept separate from `Review` rather than made generic: the eligibility
    proof is different (an OrderItem, not a Booking), there is no reply
    workflow, and the sub-rating dimensions make no sense for a file download.
    A shared polymorphic table would be mostly NULL columns and constant
    type-checking.
    """

    order_item = models.OneToOneField(
        "marketplace.OrderItem", on_delete=models.PROTECT, related_name="review"
    )
    product = models.ForeignKey(
        "marketplace.DigitalProduct", on_delete=models.CASCADE, related_name="reviews"
    )
    buyer = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, related_name="product_reviews"
    )

    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    title = models.CharField(max_length=140, blank=True)
    comment = models.TextField(max_length=2000, blank=True)

    is_hidden = models.BooleanField(default=False)
    helpful_count = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "product_reviews"
        ordering = ("-created_at",)
        indexes = [
            models.Index(
                fields=["product", "is_hidden", "-created_at"],
                name="idx_prodreview_list",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.rating}★ for product {self.product_id}"
