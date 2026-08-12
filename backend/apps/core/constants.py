"""Platform-wide enumerations and canonical error codes."""

from django.db import models


class UserRole(models.TextChoices):
    BUYER = "BUYER", "Buyer"
    PHOTOGRAPHER = "PHOTOGRAPHER", "Photographer"
    ADMIN = "ADMIN", "Admin"


class ErrorCode:
    """
    Stable, machine-readable error identifiers.

    The mobile app branches on these strings, so they are part of the public
    API contract — never rename one without bumping the API version.
    """

    VALIDATION_ERROR = "VALIDATION_ERROR"
    BUSINESS_RULE_VIOLATION = "BUSINESS_RULE_VIOLATION"
    AUTHENTICATION_FAILED = "AUTHENTICATION_FAILED"
    TOKEN_EXPIRED = "TOKEN_EXPIRED"
    TOKEN_INVALID = "TOKEN_INVALID"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    ACCOUNT_BLOCKED = "ACCOUNT_BLOCKED"
    ACCOUNT_NOT_APPROVED = "ACCOUNT_NOT_APPROVED"
    EMAIL_NOT_VERIFIED = "EMAIL_NOT_VERIFIED"
    NOT_FOUND = "NOT_FOUND"
    CONFLICT = "CONFLICT"
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    UNSUPPORTED_MEDIA_TYPE = "UNSUPPORTED_MEDIA_TYPE"
    INSUFFICIENT_BALANCE = "INSUFFICIENT_BALANCE"
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
    GONE = "GONE"


# The five event categories every dataset in ml/data/raw agrees on.
# These seed the Category table; nothing else may be treated as a top-level
# category, because the recommendation models are trained on exactly these.
CANONICAL_CATEGORIES = [
    ("wedding", "Wedding"),
    ("corporate", "Corporate"),
    ("fashion", "Fashion"),
    ("birthday", "Birthday"),
    ("graduation", "Graduation"),
]

PAKISTAN_CITIES = [
    ("Islamabad", 33.6844, 73.0479),
    ("Rawalpindi", 33.5651, 73.0169),
    ("Lahore", 31.5204, 74.3587),
    ("Karachi", 24.8607, 67.0011),
    ("Faisalabad", 31.4504, 73.1350),
    ("Multan", 30.1575, 71.5249),
    ("Peshawar", 34.0151, 71.5249),
    ("Quetta", 30.1798, 66.9750),
    ("Sialkot", 32.4945, 74.5229),
    ("Hyderabad", 25.3960, 68.3578),
]
