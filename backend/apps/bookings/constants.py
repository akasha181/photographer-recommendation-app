"""
The booking state machine.

Defining the legal transitions as DATA rather than as scattered if-statements
means there is exactly one place to look when asking "can this booking move
from X to Y?", and exactly one place to change when the rules evolve.

        ┌──────────┐
        │ PENDING  │ ── photographer accepts ──►┌──────────┐
        │          │                            │ ACCEPTED │
        │          │ ── photographer rejects ──►┌──────────┐
        └────┬─────┘                            │ REJECTED │ (terminal)
             │                                  └──────────┘
             │ ── buyer cancels ──────────────►┌───────────┐
             │                                 │ CANCELLED │ (terminal)
             │ ── 48h no response ────────────►┌──────────┐
             │                                 │ EXPIRED  │ (terminal)
             ▼
        ┌──────────┐
        │ ACCEPTED │ ── either party cancels ──► CANCELLED
        │          │ ── shoot done ───────────►┌───────────┐
        └──────────┘                           │ COMPLETED │ (terminal)
                                               └───────────┘
"""

from django.db import models


class BookingStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    ACCEPTED = "ACCEPTED", "Accepted"
    REJECTED = "REJECTED", "Rejected"
    CANCELLED = "CANCELLED", "Cancelled"
    COMPLETED = "COMPLETED", "Completed"
    EXPIRED = "EXPIRED", "Expired"


#: status -> set of statuses it may legally move to
ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    BookingStatus.PENDING: {
        BookingStatus.ACCEPTED,
        BookingStatus.REJECTED,
        BookingStatus.CANCELLED,
        BookingStatus.EXPIRED,
    },
    BookingStatus.ACCEPTED: {
        BookingStatus.COMPLETED,
        BookingStatus.CANCELLED,
    },
    # Terminal states — nothing follows them.
    BookingStatus.REJECTED: set(),
    BookingStatus.CANCELLED: set(),
    BookingStatus.COMPLETED: set(),
    BookingStatus.EXPIRED: set(),
}

#: Which role is permitted to trigger each transition.
TRANSITION_ACTORS: dict[tuple[str, str], set[str]] = {
    (BookingStatus.PENDING, BookingStatus.ACCEPTED): {"PHOTOGRAPHER", "ADMIN"},
    (BookingStatus.PENDING, BookingStatus.REJECTED): {"PHOTOGRAPHER", "ADMIN"},
    (BookingStatus.PENDING, BookingStatus.CANCELLED): {"BUYER", "ADMIN"},
    (BookingStatus.PENDING, BookingStatus.EXPIRED): {"SYSTEM", "ADMIN"},
    (BookingStatus.ACCEPTED, BookingStatus.CANCELLED): {"BUYER", "PHOTOGRAPHER", "ADMIN"},
    (BookingStatus.ACCEPTED, BookingStatus.COMPLETED): {
        "PHOTOGRAPHER", "BUYER", "SYSTEM", "ADMIN",
    },
}

#: Statuses that occupy a calendar slot and therefore block double booking.
BLOCKING_STATUSES = [BookingStatus.PENDING, BookingStatus.ACCEPTED]

#: Statuses a buyer may review after.
REVIEWABLE_STATUSES = [BookingStatus.COMPLETED]


def can_transition(current: str, target: str, actor_role: str = "ADMIN") -> bool:
    """Single source of truth for transition legality."""
    if target not in ALLOWED_TRANSITIONS.get(current, set()):
        return False
    actors = TRANSITION_ACTORS.get((current, target), set())
    return actor_role in actors or "ADMIN" == actor_role


class CancellationReason(models.TextChoices):
    BUYER_CHANGED_PLANS = "BUYER_CHANGED_PLANS", "Buyer changed plans"
    BUYER_FOUND_ALTERNATIVE = "BUYER_FOUND_ALTERNATIVE", "Buyer found an alternative"
    PHOTOGRAPHER_UNAVAILABLE = "PHOTOGRAPHER_UNAVAILABLE", "Photographer unavailable"
    PRICE_DISAGREEMENT = "PRICE_DISAGREEMENT", "Could not agree on price"
    EVENT_CANCELLED = "EVENT_CANCELLED", "The event itself was cancelled"
    PHOTOGRAPHER_SUSPENDED = "PHOTOGRAPHER_SUSPENDED", "Photographer suspended by admin"
    WEATHER = "WEATHER", "Weather"
    OTHER = "OTHER", "Other"


class PaymentMethod(models.TextChoices):
    CASH = "CASH", "Cash on the day"
    BANK_TRANSFER = "BANK_TRANSFER", "Bank transfer"
    EASYPAISA = "EASYPAISA", "Easypaisa"
    JAZZCASH = "JAZZCASH", "JazzCash"


class PaymentStatus(models.TextChoices):
    UNPAID = "UNPAID", "Unpaid"
    ADVANCE_PAID = "ADVANCE_PAID", "Advance paid"
    FULLY_PAID = "FULLY_PAID", "Fully paid"
    REFUNDED = "REFUNDED", "Refunded"
