"""Shared helpers: geo maths, image processing, ratings, upload paths."""

import math
import uuid
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from io import BytesIO

from django.core.files.uploadedfile import InMemoryUploadedFile
from django.utils.deconstruct import deconstructible
from PIL import Image

EARTH_RADIUS_KM = 6371.0


# ═══════════════════════════════════════════════════════════════════════════
# GEO
# ═══════════════════════════════════════════════════════════════════════════
def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two points in kilometres."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def bounding_box(lat: float, lon: float, radius_km: float):
    """
    Rectangle that fully contains the radius circle.

    Used as a cheap, index-friendly pre-filter: MySQL can use a B-tree index on
    (latitude, longitude) for a BETWEEN range, but not for a trigonometric
    distance formula. We narrow with the box in SQL, then compute the exact
    Haversine distance in Python on the handful of rows that survive.
    """
    lat_delta = radius_km / 111.0
    # Longitude degrees shrink as you move away from the equator.
    lon_delta = radius_km / (111.0 * max(math.cos(math.radians(lat)), 0.01))
    return (lat - lat_delta, lat + lat_delta, lon - lon_delta, lon + lon_delta)


# ═══════════════════════════════════════════════════════════════════════════
# RATINGS
# ═══════════════════════════════════════════════════════════════════════════
def bayesian_average(rating: float, count: int, prior_count: int = 10,
                     prior_rating: float = 4.0) -> float:
    """
    Smoothed rating that stops a single 5-star review outranking 200 reviews
    averaging 4.8.

        score = (n / (n + m)) * R  +  (m / (n + m)) * C

    n = review count, R = raw average, m = prior weight, C = prior mean.
    This is the same formula the SnapSphere prototype already used.
    """
    if count <= 0:
        return prior_rating
    n, m = float(count), float(prior_count)
    return (n / (n + m)) * float(rating) + (m / (n + m)) * prior_rating


def money(value) -> Decimal:
    """Coerce to 2-decimal-place Decimal. Never use float for currency."""
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# ═══════════════════════════════════════════════════════════════════════════
# IMAGES
# ═══════════════════════════════════════════════════════════════════════════
THUMBNAIL_SIZES = {"thumb": (320, 320), "medium": (800, 800), "large": (1600, 1600)}


def process_image(uploaded_file, size_key: str = "medium", quality: int = 85):
    """
    Resize, strip metadata and re-encode as WebP.

    Stripping EXIF is a privacy requirement, not an optimisation: phone photos
    embed GPS coordinates, and a photographer's portfolio would otherwise
    publish the exact home address of a newborn shoot.
    """
    img = Image.open(uploaded_file)

    if img.mode in ("RGBA", "LA", "P"):
        background = Image.new("RGB", img.size, (255, 255, 255))
        img = img.convert("RGBA")
        background.paste(img, mask=img.split()[-1])
        img = background
    else:
        img = img.convert("RGB")

    # Re-creating the image from raw pixel data discards every metadata block.
    clean = Image.new("RGB", img.size)
    clean.putdata(list(img.getdata()))

    clean.thumbnail(THUMBNAIL_SIZES[size_key], Image.Resampling.LANCZOS)

    buffer = BytesIO()
    clean.save(buffer, format="WEBP", quality=quality, method=4)
    buffer.seek(0)

    name = f"{uuid.uuid4().hex}.webp"
    return InMemoryUploadedFile(
        buffer, "ImageField", name, "image/webp", buffer.getbuffer().nbytes, None
    )


# ═══════════════════════════════════════════════════════════════════════════
# UPLOAD PATHS
# ═══════════════════════════════════════════════════════════════════════════
@deconstructible
class UploadTo:
    """
    Date-partitioned, collision-free upload paths.

        avatars/2026/07/3f9a1c....webp

    Date partitioning keeps directories small enough for the filesystem to
    stay fast, and makes "delete everything older than X" trivial.

    This is a @deconstructible CLASS rather than a closure because Django has
    to write the callable into a migration file. A closure cannot be
    serialised — `deconstruct()` tells Django to emit
    `UploadTo('avatars')` instead, which it can re-import later.
    """

    def __init__(self, folder: str):
        self.folder = folder

    def __call__(self, instance, filename: str) -> str:
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
        today = date.today()
        return f"{self.folder}/{today:%Y/%m}/{uuid.uuid4().hex}.{ext}"

    def __eq__(self, other) -> bool:
        # Without this, Django sees every UploadTo instance as different and
        # generates a pointless migration on every makemigrations run.
        return isinstance(other, UploadTo) and self.folder == other.folder

    def __hash__(self) -> int:
        return hash(("UploadTo", self.folder))


def upload_to(folder: str) -> UploadTo:
    """Ergonomic wrapper so model definitions read `upload_to("avatars")`."""
    return UploadTo(folder)
