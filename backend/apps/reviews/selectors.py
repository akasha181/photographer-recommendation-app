"""
Review reads — Module 9.

TWO THINGS EVERY QUERY HERE GUARANTEES
--------------------------------------
1. **Hidden and deleted reviews never appear.** `Review.objects` is the
   soft-delete manager and `.visible()` adds the moderation filter, so both
   have to be present on any public path. They are applied here, once, rather
   than at each of the six call sites.
2. **No N+1.** Every list is `select_related` on buyer + photographer and
   `prefetch_related` on images + reply, because the review card renders all
   four. A list endpoint without this costs 4 queries per row.

WHAT "PENDING REVIEWS" IS FOR
-----------------------------
`pending_for_user()` answers "what can I review right now?" across BOTH domains
in two queries — completed bookings and paid order items that carry no review.
The app needs it for the prompt on the Reviews tab, and the nightly reminder
task needs exactly the same set. One definition, two consumers.
"""

from django.db.models import Avg, Count, Q

from apps.reviews.models import ProductReview, Review

#: The sorts the review list offers. `helpful` first is what makes a long list
#: usable — the review other buyers found useful is rarely the newest one.
SORTS = {
    "recent": ("-created_at",),
    "oldest": ("created_at",),
    "helpful": ("-helpful_count", "-created_at"),
    "highest": ("-rating", "-created_at"),
    "lowest": ("rating", "-created_at"),
}


def _base():
    return Review.objects.visible().with_details()


# ═══════════════════════════════════════════════════════════════════════════
# PUBLIC LISTS
# ═══════════════════════════════════════════════════════════════════════════
def photographer_reviews(
    photographer_id,
    *,
    rating: int | None = None,
    with_photos: bool = False,
    sort: str = "recent",
):
    """The public review list on a photographer's profile."""
    qs = _base().filter(photographer_id=photographer_id)

    if rating is not None:
        qs = qs.filter(rating=rating)
    if with_photos:
        # A buyer filtering for photos wants proof shots, so an EXISTS subquery
        # is the right shape — a JOIN would multiply rows per image.
        qs = qs.filter(images__isnull=False).distinct()

    return qs.order_by(*SORTS.get(sort, SORTS["recent"]))


def product_reviews(product_id, *, sort: str = "recent"):
    qs = (
        ProductReview.objects.filter(
            product_id=product_id, is_hidden=False, is_deleted=False
        )
        .select_related("buyer", "product")
    )
    return qs.order_by(*SORTS.get(sort, SORTS["recent"]))


def get_review(pk) -> Review | None:
    return _base().filter(pk=pk).first()


def get_product_review(pk) -> ProductReview | None:
    return (
        ProductReview.objects.filter(pk=pk, is_deleted=False)
        .select_related("buyer", "product", "product__seller", "order_item")
        .first()
    )


# ═══════════════════════════════════════════════════════════════════════════
# SUMMARIES
# ═══════════════════════════════════════════════════════════════════════════
def rating_breakdown(photographer_id) -> dict[str, int]:
    """
    Star histogram in ONE aggregate query, gap-filled to five keys.

    A 4.6 built from mostly 5s with two 1s tells a very different story from a
    4.6 built entirely from 4s and 5s, and buyers read the distribution before
    they read the number. Gap-filling matters because a star nobody gave must
    render as an empty bar, not be missing from the chart.
    """
    rows = (
        Review.objects.visible()
        .filter(photographer_id=photographer_id)
        .values("rating")
        .annotate(count=Count("id"))
    )
    breakdown = {str(star): 0 for star in range(1, 6)}
    for row in rows:
        breakdown[str(row["rating"])] = row["count"]
    return breakdown


def review_summary(photographer_id) -> dict:
    """
    Everything the "Reviews" header shows, in four queries.

    The five sub-rating averages are what make the headline actionable: a 3.9
    overall is not feedback, but "4.8 quality, 2.9 punctuality" names the thing
    to fix. They are averaged with `Avg` over a nullable column, so a
    photographer whose buyers never filled them in gets `None`, not 0 — which
    the app renders as "not rated yet" instead of as a damning zero.

    THE PHOTO COUNT IS A SEPARATE QUERY, ON PURPOSE. Putting
    `Count(filter=Q(images__isnull=False))` in the same `aggregate()` adds a
    LEFT JOIN to `review_images`, which duplicates a review row per image and
    silently corrupts every average beside it. A review with three photos would
    weigh three times in `average_rating`.
    """
    qs = Review.objects.visible().filter(photographer_id=photographer_id)

    agg = qs.aggregate(
        average=Avg("rating"),
        total=Count("id"),
        with_comment=Count("id", filter=~Q(comment="")),
        recommended=Count("id", filter=Q(rating__gte=4)),
        quality=Avg("rating_quality"),
        professionalism=Avg("rating_professionalism"),
        communication=Avg("rating_communication"),
        value=Avg("rating_value"),
        punctuality=Avg("rating_punctuality"),
    )
    with_photos = qs.filter(images__isnull=False).distinct().count()

    total = agg["total"] or 0
    return {
        "average_rating": round(float(agg["average"] or 0), 2),
        "total_reviews": total,
        "with_comment": agg["with_comment"] or 0,
        "with_photos": with_photos,
        # Share of reviewers who gave 4 or 5. Reported as a stored rate rather
        # than left to the client, for the same reason the analytics rollups
        # are: a client that divides by zero shows NaN on an empty profile.
        "recommend_percent": round(100 * (agg["recommended"] or 0) / total, 1)
        if total
        else 0.0,
        "breakdown": rating_breakdown(photographer_id),
        "sub_ratings": {
            "quality": _round_or_none(agg["quality"]),
            "professionalism": _round_or_none(agg["professionalism"]),
            "communication": _round_or_none(agg["communication"]),
            "value": _round_or_none(agg["value"]),
            "punctuality": _round_or_none(agg["punctuality"]),
        },
        "sentiment": sentiment_breakdown(photographer_id),
    }


def _round_or_none(value) -> float | None:
    """None means "nobody filled this in", which is not the same as zero."""
    return round(float(value), 2) if value is not None else None


def sentiment_breakdown(photographer_id) -> dict[str, int]:
    """
    How the model read the prose, for the photographer's own dashboard.

    Deliberately not shown to buyers: a machine label on somebody else's words
    is not evidence, and a buyer reading "NEGATIVE" beside a 4-star review
    would trust the platform less, not more.
    """
    rows = (
        Review.objects.visible()
        .filter(photographer_id=photographer_id)
        .exclude(sentiment="")
        .values("sentiment")
        .annotate(count=Count("id"))
    )
    out = {"POSITIVE": 0, "NEUTRAL": 0, "NEGATIVE": 0}
    for row in rows:
        out[row["sentiment"]] = row["count"]
    return out


def product_review_summary(product_id) -> dict:
    agg = ProductReview.objects.filter(
        product_id=product_id, is_hidden=False, is_deleted=False
    ).aggregate(average=Avg("rating"), total=Count("id"))
    rows = (
        ProductReview.objects.filter(
            product_id=product_id, is_hidden=False, is_deleted=False
        )
        .values("rating")
        .annotate(count=Count("id"))
    )
    breakdown = {str(star): 0 for star in range(1, 6)}
    for row in rows:
        breakdown[str(row["rating"])] = row["count"]
    return {
        "average_rating": round(float(agg["average"] or 0), 2),
        "total_reviews": agg["total"] or 0,
        "breakdown": breakdown,
    }


# ═══════════════════════════════════════════════════════════════════════════
# PER-USER LISTS
# ═══════════════════════════════════════════════════════════════════════════
def reviews_written_by(user):
    """A buyer's own reviews — editable ones included, hidden ones too."""
    return (
        Review.objects.filter(buyer=user, is_deleted=False)
        .with_details()
        .order_by("-created_at")
    )


def product_reviews_written_by(user):
    return (
        ProductReview.objects.filter(buyer=user, is_deleted=False)
        .select_related("product")
        .order_by("-created_at")
    )


def reviews_received_by(photographer, *, unanswered_only: bool = False):
    """
    A photographer's inbox of reviews.

    Includes hidden ones: their own moderated review is information they are
    entitled to, and hiding it from them too would make the hidden_reason
    unexplainable.
    """
    qs = (
        Review.objects.filter(photographer=photographer, is_deleted=False)
        .with_details()
        .order_by("-created_at")
    )
    if unanswered_only:
        qs = qs.filter(reply__isnull=True)
    return qs


def unanswered_count(photographer) -> int:
    """Badge for the photographer's Reviews tab."""
    return Review.objects.visible().filter(
        photographer=photographer, reply__isnull=True
    ).count()


def pending_for_user(user) -> dict:
    """
    What this buyer is entitled to review right now.

    Two queries, both indexed: completed bookings with `has_review=False`, and
    paid order items with `has_review=False`. `has_review` is a denormalised
    flag rather than a NOT EXISTS subquery precisely so this stays cheap enough
    to call on every visit to the Reviews tab.
    """
    from apps.bookings.constants import BookingStatus
    from apps.bookings.models import Booking
    from apps.marketplace.models import OrderItem, OrderStatus

    bookings = (
        Booking.objects.filter(
            buyer=user, status=BookingStatus.COMPLETED, has_review=False
        )
        .select_related("photographer", "photographer__user", "service")
        .order_by("-event_date")
    )
    items = (
        OrderItem.objects.filter(
            order__buyer=user, order__status=OrderStatus.PAID, has_review=False
        )
        .select_related("product", "order")
        .order_by("-created_at")
    )
    return {"bookings": bookings, "order_items": items}
