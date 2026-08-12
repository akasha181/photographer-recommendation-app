"""
Recommendation engine persistence — the feature store, the model registry and
the event log.

WHY A FEATURE STORE TABLE EXISTS
--------------------------------
Scoring 40 candidate photographers needs 12 numbers each. Computing those with
live aggregate queries would mean ~12 JOINs per request. `PhotographerFeature`
holds them pre-computed and pre-scaled, refreshed nightly, so the scoring path
is one indexed SELECT plus a NumPy matrix multiply.

WHY MODEL VERSIONS ARE TRACKED IN THE DATABASE
----------------------------------------------
When recommendation quality drops after a retrain, you need to answer "what
changed and how do I roll back" in seconds. ModelVersion records the metrics
of every trained artifact and which one is live, so rollback is an UPDATE.

WHY EVERY RECOMMENDATION IS LOGGED
----------------------------------
You cannot evaluate what you did not record. RecommendationEvent captures what
was shown, in what position, and whether it was clicked or booked — which is
what makes offline CTR and Precision@K measurable rather than guessed.
"""

from decimal import Decimal

from django.db import models

from apps.core.models import TimeStampedModel


class PhotographerFeature(TimeStampedModel):
    """
    One row per photographer: the exact feature vector the ranker consumes.

    Column names deliberately mirror photographer_profiles.csv so the CSV can
    be loaded straight into this table for training and demonstration.
    """

    photographer = models.OneToOneField(
        "profiles.PhotographerProfile", on_delete=models.CASCADE,
        related_name="features",
    )

    # ─── Raw features ────────────────────────────────────────────────────────
    avg_rating = models.FloatField(default=0.0)
    bayesian_rating = models.FloatField(default=0.0)
    reviews_count = models.IntegerField(default=0)
    years_experience = models.IntegerField(default=0)
    bookings_success_rate = models.FloatField(default=0.0)
    response_time_hours = models.FloatField(default=24.0)
    portfolio_score = models.IntegerField(default=0)
    base_price = models.FloatField(default=0.0)

    completed_bookings = models.IntegerField(default=0)
    total_bookings = models.IntegerField(default=0)
    profile_views = models.IntegerField(default=0)
    portfolio_image_count = models.IntegerField(default=0)

    # ─── Engineered features ─────────────────────────────────────────────────
    response_speed_score = models.FloatField(
        default=0.0,
        help_text="1 / (1 + hours). INVERTED because low response time is good "
                  "— feeding raw hours would train the model to prefer slow "
                  "photographers.",
    )
    popularity_score = models.FloatField(
        default=0.0, help_text="log1p(completed_bookings) normalised 0-1."
    )
    engagement_rate = models.FloatField(
        default=0.0, help_text="bookings / profile_views."
    )
    recency_score = models.FloatField(
        default=0.0, help_text="Decays with days since last completed booking."
    )
    price_percentile = models.FloatField(
        default=0.5, help_text="Where this price sits among all photographers."
    )
    sentiment_score = models.FloatField(
        default=0.5, help_text="Mean predicted sentiment across their reviews."
    )
    is_new_photographer = models.BooleanField(
        default=False,
        help_text="< 30 days old. Qualifies for a guaranteed exploration slot.",
    )

    # ─── Composite ───────────────────────────────────────────────────────────
    quality_score = models.FloatField(default=0.0, db_index=True)

    last_computed_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "photographer_features"
        indexes = [
            models.Index(fields=["-quality_score"], name="idx_feature_quality"),
        ]

    def __str__(self) -> str:
        return f"Features for photographer {self.photographer_id}"

    def as_vector(self) -> list[float]:
        """Order must match ml/pipelines/features.py FEATURE_ORDER exactly."""
        return [
            self.bayesian_rating,
            float(self.reviews_count),
            float(self.years_experience),
            self.bookings_success_rate,
            self.response_speed_score,
            float(self.portfolio_score),
            self.popularity_score,
            self.engagement_rate,
            self.recency_score,
            self.price_percentile,
            self.sentiment_score,
            float(self.portfolio_image_count),
        ]


class SeasonalDemand(TimeStampedModel):
    """
    Loaded from seasonal_demand.csv (12 months × 5 categories).

    Gives the ranker a "this photographer specialises in what is in demand
    right now" signal, and powers the admin's demand-forecast chart.
    """

    month = models.PositiveSmallIntegerField(db_index=True)  # 1-12
    category = models.ForeignKey(
        "catalog.Category", on_delete=models.CASCADE, related_name="seasonal_demand"
    )
    avg_bookings = models.IntegerField(default=0)
    avg_price = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    demand_score = models.IntegerField(
        default=50, help_text="0-100 relative demand index."
    )

    class Meta:
        db_table = "seasonal_demand"
        constraints = [
            models.UniqueConstraint(
                fields=["month", "category"], name="uniq_seasonal_month_category"
            )
        ]
        ordering = ("month",)

    def __str__(self) -> str:
        return f"{self.category_id} in month {self.month}: {self.demand_score}"


class BuyerInteractionType(models.TextChoices):
    VIEW = "VIEW", "Profile view"
    CLICK = "CLICK", "Card click"
    PORTFOLIO = "PORTFOLIO", "Portfolio interaction"
    SEARCH = "SEARCH", "Appeared in search"
    INQUIRY = "INQUIRY", "Message sent"
    WISHLIST = "WISHLIST", "Added to wishlist"
    BOOKING = "BOOKING", "Booking created"
    COMPLETED = "COMPLETED", "Booking completed"


#: Implicit-feedback weights. A completed booking is far stronger evidence of
#: preference than a profile view, and the CF matrix must reflect that.
INTERACTION_WEIGHTS = {
    BuyerInteractionType.VIEW: 1.0,
    BuyerInteractionType.CLICK: 2.0,
    BuyerInteractionType.PORTFOLIO: 3.0,
    BuyerInteractionType.SEARCH: 0.5,
    BuyerInteractionType.INQUIRY: 5.0,
    BuyerInteractionType.WISHLIST: 6.0,
    BuyerInteractionType.BOOKING: 8.0,
    BuyerInteractionType.COMPLETED: 10.0,
}


class BuyerInteraction(TimeStampedModel):
    """
    The implicit-feedback log — the training data for collaborative filtering.

    Mirrors buyer_interactions.csv, so the 500 historical rows in that file
    seed a working CF model on day one instead of waiting for real traffic.
    """

    buyer = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="interactions"
    )
    photographer = models.ForeignKey(
        "profiles.PhotographerProfile", on_delete=models.CASCADE,
        related_name="buyer_interactions",
    )
    interaction_type = models.CharField(
        max_length=16, choices=BuyerInteractionType.choices, db_index=True
    )
    weight = models.FloatField(default=1.0)

    search_keyword = models.CharField(max_length=120, blank=True)
    category = models.ForeignKey(
        "catalog.Category", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="interactions",
    )
    session_id = models.CharField(max_length=64, blank=True, db_index=True)

    class Meta:
        db_table = "buyer_interactions"
        indexes = [
            models.Index(
                fields=["buyer", "photographer"], name="idx_interaction_pair"
            ),
            models.Index(fields=["-created_at"], name="idx_interaction_recent"),
        ]

    def __str__(self) -> str:
        return f"{self.buyer_id} {self.interaction_type} {self.photographer_id}"

    def save(self, *args, **kwargs):
        if self.weight == 1.0:
            self.weight = INTERACTION_WEIGHTS.get(self.interaction_type, 1.0)
        super().save(*args, **kwargs)


class ModelVersion(TimeStampedModel):
    """Registry of trained artifacts — makes rollback an UPDATE statement."""

    name = models.CharField(
        max_length=40,
        choices=[
            ("ranker", "Content ranker"),
            ("cf", "Collaborative filter"),
            ("sentiment", "Sentiment classifier"),
            ("product_ranker", "Product ranker"),
        ],
        db_index=True,
    )
    version = models.PositiveIntegerField()
    algorithm = models.CharField(max_length=80, blank=True)

    artifact_path = models.CharField(max_length=300)
    feature_order = models.JSONField(default=list, blank=True)
    hyperparameters = models.JSONField(default=dict, blank=True)

    # ─── Evaluation metrics ──────────────────────────────────────────────────
    metrics = models.JSONField(
        default=dict, blank=True,
        help_text='e.g. {"rmse": 0.41, "mae": 0.32, "precision_at_10": 0.68}',
    )
    training_rows = models.IntegerField(default=0)
    training_duration_seconds = models.FloatField(default=0.0)

    is_active = models.BooleanField(default=False, db_index=True)
    activated_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        db_table = "model_versions"
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=["name", "version"], name="uniq_model_version"
            ),
            # Exactly one live model per name — prevents the ambiguity of two
            # rankers both claiming to be active.
            models.UniqueConstraint(
                fields=["name"],
                condition=models.Q(is_active=True),
                name="uniq_active_model_per_name",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} v{self.version}{' (active)' if self.is_active else ''}"


class RecommendationEvent(TimeStampedModel):
    """
    What was shown, where, and what happened next.

    This is the entire basis of offline evaluation. Without it, "our
    recommendations are good" is an opinion.
    """

    buyer = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="recommendation_events",
    )
    photographer = models.ForeignKey(
        "profiles.PhotographerProfile", on_delete=models.CASCADE,
        related_name="recommendation_events",
    )

    position = models.PositiveSmallIntegerField(help_text="1-based rank shown.")
    score = models.FloatField()
    content_score = models.FloatField(default=0.0)
    collab_score = models.FloatField(default=0.0)
    business_score = models.FloatField(default=0.0)

    strategy = models.CharField(
        max_length=24,
        choices=[
            ("HYBRID", "Hybrid"), ("CONTENT", "Content-based"),
            ("COLLABORATIVE", "Collaborative"), ("POPULARITY", "Popularity fallback"),
            ("EXPLORATION", "Exploration slot"),
        ],
        default="HYBRID", db_index=True,
    )
    model_version = models.ForeignKey(
        ModelVersion, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="events",
    )
    filters_applied = models.JSONField(default=dict, blank=True)
    reason = models.CharField(
        max_length=200, blank=True,
        help_text="Human-readable explanation shown in the app.",
    )

    # ─── Outcomes (updated later, drive CTR / conversion) ────────────────────
    was_clicked = models.BooleanField(default=False, db_index=True)
    clicked_at = models.DateTimeField(null=True, blank=True)
    led_to_booking = models.BooleanField(default=False, db_index=True)
    booking = models.ForeignKey(
        "bookings.Booking", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="+",
    )

    class Meta:
        db_table = "recommendation_events"
        indexes = [
            models.Index(fields=["buyer", "-created_at"], name="idx_recevent_by_buyer"),
            models.Index(
                fields=["strategy", "was_clicked"], name="idx_recevent_ctr"
            ),
            models.Index(fields=["-created_at"], name="idx_recevent_recent"),
        ]

    def __str__(self) -> str:
        return f"Rec #{self.position} score={self.score:.3f}"
