"""
Review writes — Module 9.

THE ELIGIBILITY RULE IS THE WHOLE MODULE
---------------------------------------
"Only a buyer with a completed booking may review that photographer, once."

Everything else here — sentiment, replies, helpful votes, moderation — is
ornament around that sentence. It is enforced three times over (serializer,
this file, `Review.booking` OneToOne), and the reason for the redundancy is
that the database level is the only one an attacker cannot reach: to post N
fake reviews they must complete N real, paid bookings.

WHAT ELSE HAS TO HAPPEN INSIDE THE SAME TRANSACTION
---------------------------------------------------
A review changes four things that must never disagree:

    1. the `reviews` row
    2. `Booking.has_review`             — drives `is_reviewable` in the app
    3. `PhotographerProfile.avg_rating` — the headline number on every card
    4. `BuyerProfile.reviews_written`   — the buyer's own profile counter

If (3) were deferred to a Celery task, a profile would show "4.8 from 12
reviews" above a list of 13. So `create_review` does all four atomically and
`notify()` (which defers to `on_commit`) is the only thing that happens after.

WHY EDITING IS TIME-BOXED AND REPLY-BOXED
-----------------------------------------
A review can be corrected for `EDIT_WINDOW_HOURS`, and only while the
photographer has not replied. Once there is a reply, editing the review above
it would let a buyer rewrite the question a public answer was given to — the
photographer's words would stay, attached to something they never read.
"""

import logging
from datetime import timedelta

from django.db import transaction
from django.db.models import Avg, Count, F
from django.utils import timezone

from apps.core.exceptions import BusinessRuleViolation, ConflictError
from apps.reviews.models import (
    ProductReview,
    Review,
    ReviewHelpful,
    ReviewImage,
    ReviewReply,
)

logger = logging.getLogger("snapsphere")

#: A typo or a forgotten sentence is worth fixing; a review rewritten a month
#: later is a different review, posted under an old date.
EDIT_WINDOW_HOURS = 24

#: Photos are the strongest trust signal on a profile, but each one is three
#: renditions on disk and a row in the detail payload.
MAX_IMAGES_PER_REVIEW = 5

#: Sub-rating fields, in the order the app renders them.
SUB_RATING_FIELDS = (
    "rating_quality",
    "rating_professionalism",
    "rating_communication",
    "rating_value",
    "rating_punctuality",
)


# ═══════════════════════════════════════════════════════════════════════════
# PHOTOGRAPHER REVIEWS
# ═══════════════════════════════════════════════════════════════════════════
def create_review(
    booking,
    buyer,
    *,
    rating: int,
    title: str = "",
    comment: str = "",
    images: list | None = None,
    **sub_ratings,
) -> Review:
    """
    Write the one review this booking is entitled to.

    `buyer` is passed explicitly rather than read off the booking: the caller
    is asserting "this is who is acting", and comparing that against
    `booking.buyer_id` is the ownership check. Reading it off the booking would
    make the check tautological.
    """
    _assert_eligible(booking, buyer)

    review = _create_review_locked(
        booking, buyer, rating=rating, title=title, comment=comment,
        images=images or [], sub_ratings=sub_ratings,
    )

    _notify_photographer(review)
    return review


@transaction.atomic
def _create_review_locked(booking, buyer, *, rating, title, comment, images, sub_ratings):
    # Re-check under the lock. Two taps on Submit arrive as two requests; the
    # serializer check passed in both, and this is where the loser stops.
    locked = Review.all_objects.select_for_update().filter(booking=booking).first()
    if locked is not None:
        raise ConflictError("You have already reviewed this booking.")

    from apps.core.sentiment import classify

    sentiment, score = classify(comment)

    review = Review.objects.create(
        booking=booking,
        buyer=buyer,
        photographer=booking.photographer,
        rating=rating,
        title=title.strip()[:140],
        comment=comment.strip(),
        sentiment=sentiment or "",
        sentiment_score=score,
        **{f: sub_ratings.get(f) for f in SUB_RATING_FIELDS},
    )

    for image in images[:MAX_IMAGES_PER_REVIEW]:
        _attach_image(review, image)

    # `.update()` rather than `booking.save()`: the booking was fetched for
    # reading and may be stale in every other field. This writes exactly the
    # flag that changed.
    type(booking).objects.filter(pk=booking.pk).update(has_review=True)
    booking.has_review = True

    _refresh_ratings(review.photographer, buyer)

    logger.info(
        "Review created",
        extra={
            "review_id": review.pk,
            "booking_id": booking.pk,
            "rating": rating,
            "sentiment": sentiment,
        },
    )
    return review


@transaction.atomic
def update_review(review: Review, **data) -> Review:
    """Correct a review inside the edit window, before any reply exists."""
    _assert_editable(review)

    images = data.pop("images", None)
    for field, value in data.items():
        if field in ("title", "comment"):
            value = (value or "").strip()
        setattr(review, field, value)

    if "comment" in data:
        from apps.core.sentiment import classify

        sentiment, score = classify(review.comment)
        review.sentiment = sentiment or ""
        review.sentiment_score = score

    review.save()

    if images:
        room = MAX_IMAGES_PER_REVIEW - review.images.count()
        if room <= 0:
            raise BusinessRuleViolation(
                f"A review can carry {MAX_IMAGES_PER_REVIEW} photos."
            )
        for image in images[:room]:
            _attach_image(review, image)

    if "rating" in data:
        _refresh_ratings(review.photographer, review.buyer)
    return review


@transaction.atomic
def delete_review(review: Review) -> None:
    """
    Soft delete, then recompute.

    The row survives because `Booking.review` is PROTECT and because a deleted
    review is still evidence in a dispute. `Review.objects.visible()` excludes
    it, so it leaves the public average the moment this returns — but the
    booking stays flagged as reviewed, deliberately: the entitlement was spent.
    """
    review.delete()  # SoftDeleteModel — flips is_deleted
    _refresh_ratings(review.photographer, review.buyer)
    logger.info("Review deleted", extra={"review_id": review.pk})


def _assert_eligible(booking, buyer) -> None:
    """The four conditions, each with the sentence the buyer should read."""
    from apps.bookings.constants import REVIEWABLE_STATUSES

    if booking.buyer_id != buyer.id:
        raise BusinessRuleViolation("You can only review your own bookings.")
    if booking.status not in REVIEWABLE_STATUSES:
        raise BusinessRuleViolation(
            "You can review a shoot once it is marked completed."
        )
    if Review.all_objects.filter(booking=booking).exists():
        raise ConflictError("You have already reviewed this booking.")


def _assert_editable(review: Review) -> None:
    if hasattr(review, "reply"):
        raise BusinessRuleViolation(
            "This review has a public reply, so it can no longer be edited. "
            "Contact support if it needs correcting."
        )
    deadline = review.created_at + timedelta(hours=EDIT_WINDOW_HOURS)
    if timezone.now() > deadline:
        raise BusinessRuleViolation(
            f"Reviews can be edited for {EDIT_WINDOW_HOURS} hours after posting."
        )


def _attach_image(review: Review, image) -> ReviewImage:
    """
    Store a buyer's photo at two sizes, with EXIF stripped.

    Same privacy requirement as the portfolio: an uploaded phone photo of a
    wedding venue carries its GPS coordinates. `process_image` re-encodes from
    raw pixel data, which discards every metadata block.
    """
    from apps.core.utils import process_image

    row = ReviewImage(review=review, caption="")
    for field, size_key in (("image", "medium"), ("thumbnail", "thumb")):
        image.seek(0)
        processed = process_image(image, size_key=size_key)
        getattr(row, field).save(processed.name, processed, save=False)
    row.save()
    return row


# ═══════════════════════════════════════════════════════════════════════════
# REPLIES
# ═══════════════════════════════════════════════════════════════════════════
@transaction.atomic
def reply_to_review(review: Review, photographer, comment: str) -> ReviewReply:
    """
    The photographer's one public response.

    OneToOne by design (see models.py): a review is not a comment thread.
    Editing is allowed indefinitely — unlike the review, a reply has no
    counterparty whose words depend on it, and a photographer who worded a
    reply badly under pressure should be able to improve it.
    """
    if review.photographer_id != photographer.pk:
        raise BusinessRuleViolation("You can only reply to your own reviews.")
    if review.is_deleted:
        raise BusinessRuleViolation("This review is no longer available.")

    existing = ReviewReply.objects.filter(review=review).first()
    if existing is not None:
        raise ConflictError(
            "You have already replied to this review. Edit that reply instead."
        )

    reply = ReviewReply.objects.create(
        review=review, photographer=photographer, comment=comment.strip()
    )
    _notify_buyer_of_reply(reply)
    return reply


@transaction.atomic
def update_reply(reply: ReviewReply, comment: str) -> ReviewReply:
    reply.comment = comment.strip()
    reply.is_edited = True
    reply.save(update_fields=["comment", "is_edited", "updated_at"])
    return reply


@transaction.atomic
def delete_reply(reply: ReviewReply) -> None:
    reply.delete()


# ═══════════════════════════════════════════════════════════════════════════
# HELPFUL VOTES
# ═══════════════════════════════════════════════════════════════════════════
@transaction.atomic
def toggle_helpful(review: Review, user) -> tuple[bool, int]:
    """
    Mark or unmark a review as helpful. Returns (is_marked, new_count).

    One endpoint that returns the state it left behind, for the same reason the
    wishlist heart works this way: the UI is one toggle, and separate add /
    remove endpoints make the client guess which state the server is in.

    `helpful_count` is maintained with `F()` rather than a COUNT() so the
    review list does not need a subquery per row — and, more importantly, so
    two people voting at once cannot read-modify-write over each other.
    """
    if review.buyer_id == user.id:
        raise BusinessRuleViolation("You cannot mark your own review as helpful.")

    vote = ReviewHelpful.objects.filter(review=review, user=user).first()
    if vote is not None:
        vote.delete()
        Review.objects.filter(pk=review.pk, helpful_count__gt=0).update(
            helpful_count=F("helpful_count") - 1
        )
        marked = False
    else:
        ReviewHelpful.objects.create(review=review, user=user)
        Review.objects.filter(pk=review.pk).update(
            helpful_count=F("helpful_count") + 1
        )
        marked = True

    review.refresh_from_db(fields=["helpful_count"])
    return marked, review.helpful_count


# ═══════════════════════════════════════════════════════════════════════════
# REPORTING
# ═══════════════════════════════════════════════════════════════════════════
@transaction.atomic
def flag_review(review: Review, reporter, *, reason: str, detail: str = ""):
    """
    Raise a moderation report against a review.

    The report goes to the single admin queue in `administration`
    (`ModerationFlag`), imported lazily so `reviews` keeps no module-level
    dependency on an app that sits above it in the graph. The counter here is
    denormalised so a review that is being mass-reported is visible in the
    review list itself, not only in the admin queue.

    Flagging does NOT hide the review. Auto-hiding on a threshold hands anyone
    with three accounts an eraser for honest criticism; a human decides.
    """
    from apps.administration.services import report_content

    if review.buyer_id == reporter.id:
        raise BusinessRuleViolation(
            "This is your own review — you can edit or delete it instead."
        )

    flag = report_content(
        reporter=reporter,
        content_type="REVIEW",
        object_id=review.pk,
        reason=reason,
        detail=detail,
    )
    Review.objects.filter(pk=review.pk).update(
        is_flagged=True, flag_count=F("flag_count") + 1
    )
    return flag


@transaction.atomic
def set_hidden(review: Review, *, hidden: bool, reason: str = "") -> Review:
    """
    Admin moderation: take a review out of (or back into) the public average.

    Called by `administration.services`, which writes the audit entry. Kept
    here rather than there because recomputing the photographer's rating
    afterwards is this app's business and must happen in the same transaction.
    """
    review.is_hidden = hidden
    review.hidden_reason = reason[:200] if hidden else ""
    review.save(update_fields=["is_hidden", "hidden_reason", "updated_at"])
    _refresh_ratings(review.photographer, review.buyer)
    return review


# ═══════════════════════════════════════════════════════════════════════════
# PRODUCT REVIEWS
# ═══════════════════════════════════════════════════════════════════════════
def create_product_review(
    order_item, buyer, *, rating: int, title: str = "", comment: str = ""
) -> ProductReview:
    """
    Review a purchased product.

    The eligibility proof is an `OrderItem` on a PAID order, which is why this
    is a separate model from `Review` rather than a polymorphic one: the proof,
    the sub-rating dimensions and the reply workflow all differ.
    """
    _assert_product_eligible(order_item, buyer)
    return _create_product_review_locked(
        order_item, buyer, rating=rating, title=title, comment=comment
    )


@transaction.atomic
def _create_product_review_locked(order_item, buyer, *, rating, title, comment):
    locked = (
        ProductReview.all_objects.select_for_update()
        .filter(order_item=order_item)
        .first()
    )
    if locked is not None:
        raise ConflictError("You have already reviewed this product.")

    from apps.core.sentiment import classify

    _, score = classify(comment)

    review = ProductReview.objects.create(
        order_item=order_item,
        product=order_item.product,
        buyer=buyer,
        rating=rating,
        title=title.strip()[:140],
        comment=comment.strip(),
    )
    type(order_item).objects.filter(pk=order_item.pk).update(has_review=True)
    order_item.has_review = True

    refresh_product_rating(order_item.product)
    _notify_seller(review, confidence=score)
    return review


@transaction.atomic
def update_product_review(review: ProductReview, **data) -> ProductReview:
    deadline = review.created_at + timedelta(hours=EDIT_WINDOW_HOURS)
    if timezone.now() > deadline:
        raise BusinessRuleViolation(
            f"Reviews can be edited for {EDIT_WINDOW_HOURS} hours after posting."
        )
    for field, value in data.items():
        setattr(review, field, (value or "").strip() if field in ("title", "comment") else value)
    review.save()
    if "rating" in data:
        refresh_product_rating(review.product)
    return review


@transaction.atomic
def delete_product_review(review: ProductReview) -> None:
    review.delete()
    refresh_product_rating(review.product)


def _assert_product_eligible(order_item, buyer) -> None:
    from apps.marketplace.models import OrderStatus

    if order_item.order.buyer_id != buyer.id:
        raise BusinessRuleViolation("You can only review products you bought.")
    if order_item.order.status != OrderStatus.PAID:
        raise BusinessRuleViolation("This order has not been paid for.")
    if ProductReview.all_objects.filter(order_item=order_item).exists():
        raise ConflictError("You have already reviewed this product.")


def refresh_product_rating(product) -> None:
    """
    Recompute `avg_rating` / `reviews_count` on the product.

    Denormalised because the shop grid sorts on rating: computing it per row
    would be an aggregate subquery on a screen that shows twenty cards.
    """
    agg = ProductReview.objects.filter(product=product, is_hidden=False).aggregate(
        avg=Avg("rating"), count=Count("id")
    )
    from decimal import Decimal

    type(product).objects.filter(pk=product.pk).update(
        avg_rating=Decimal(f"{agg['avg'] or 0:.2f}"),
        reviews_count=agg["count"] or 0,
    )


# ═══════════════════════════════════════════════════════════════════════════
# DENORMALISED METRICS
# ═══════════════════════════════════════════════════════════════════════════
def _refresh_ratings(photographer, buyer) -> None:
    """Photographer average + Bayesian score, and the buyer's own counter."""
    from apps.profiles.models import BuyerProfile
    from apps.profiles.services import refresh_photographer_rating

    refresh_photographer_rating(photographer)

    written = Review.objects.visible().filter(buyer=buyer).count()
    BuyerProfile.objects.filter(user=buyer).update(reviews_written=written)


# ═══════════════════════════════════════════════════════════════════════════
# NOTIFICATIONS
# ═══════════════════════════════════════════════════════════════════════════
def _notify_photographer(review: Review) -> None:
    from apps.notifications.models import NotificationType
    from apps.notifications.services import notify

    notify(
        review.photographer.user,
        NotificationType.REVIEW_RECEIVED,
        title=f"{review.rating}★ review from {review.buyer.full_name}",
        # The rating is in the title; the body carries the words, because that
        # is what decides whether the photographer opens it now or later.
        body=(review.comment[:140] or review.title or "No comment left."),
        action_screen="ReviewDetail",
        action_id=str(review.pk),
        actor=review.buyer,
        payload={"review_id": review.pk, "rating": review.rating},
    )


def _notify_buyer_of_reply(reply: ReviewReply) -> None:
    from apps.notifications.models import NotificationType
    from apps.notifications.services import notify

    notify(
        reply.review.buyer,
        NotificationType.REVIEW_REPLIED,
        title=f"{reply.photographer.display_name} replied to your review",
        body=reply.comment[:140],
        action_screen="ReviewDetail",
        action_id=str(reply.review_id),
        actor=reply.photographer.user,
        payload={"review_id": reply.review_id},
    )


def _notify_seller(review: ProductReview, confidence=None) -> None:
    from apps.notifications.models import NotificationType
    from apps.notifications.services import notify

    notify(
        review.product.seller.user,
        NotificationType.REVIEW_RECEIVED,
        title=f"{review.rating}★ on {review.product.title}",
        body=(review.comment[:140] or review.title or "No comment left."),
        action_screen="ProductDetail",
        action_id=review.product.slug,
        actor=review.buyer,
        payload={"product_review_id": review.pk, "rating": review.rating},
    )
