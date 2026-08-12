"""
Reusable validators.

File validation checks *magic bytes*, not the filename extension. Renaming
`payload.exe` to `photo.jpg` defeats extension checks completely; it cannot
defeat a signature check.
"""

import re

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone

# ─── File signatures (first bytes of the file) ───────────────────────────────
MAGIC_SIGNATURES = {
    b"\xff\xd8\xff": "image/jpeg",
    b"\x89PNG\r\n\x1a\n": "image/png",
    b"RIFF": "image/webp",          # bytes 8-12 must also be "WEBP"
    b"GIF87a": "image/gif",
    b"GIF89a": "image/gif",
    b"\x00\x00\x00\x18ftyp": "video/mp4",
    b"\x00\x00\x00\x20ftyp": "video/mp4",
    b"PK\x03\x04": "application/zip",
}

PHONE_RE = re.compile(r"^(\+92|0)?3\d{9}$")  # Pakistani mobile numbers


def detect_mime(uploaded_file) -> str | None:
    """Read the leading bytes and return the real MIME type, or None."""
    pos = uploaded_file.tell()
    uploaded_file.seek(0)
    header = uploaded_file.read(16)
    uploaded_file.seek(pos)

    for signature, mime in MAGIC_SIGNATURES.items():
        if header.startswith(signature):
            if mime == "image/webp" and header[8:12] != b"WEBP":
                continue
            return mime
    # MP4 variants place "ftyp" at offset 4 with a variable size prefix.
    if header[4:8] == b"ftyp":
        return "video/mp4"
    return None


def _validate_upload(uploaded_file, allowed_mimes, max_mb, kind):
    size_mb = uploaded_file.size / (1024 * 1024)
    if size_mb > max_mb:
        raise ValidationError(
            f"{kind} must be {max_mb}MB or smaller (yours is {size_mb:.1f}MB)."
        )
    mime = detect_mime(uploaded_file)
    if mime is None:
        raise ValidationError(f"Could not identify this file as a valid {kind.lower()}.")
    if mime not in allowed_mimes:
        readable = ", ".join(m.split("/")[-1].upper() for m in allowed_mimes)
        raise ValidationError(f"Unsupported format. Allowed: {readable}.")
    return mime


def validate_image_file(uploaded_file):
    return _validate_upload(
        uploaded_file,
        settings.ALLOWED_IMAGE_TYPES,
        settings.MAX_IMAGE_SIZE_MB,
        "Image",
    )


def validate_video_file(uploaded_file):
    return _validate_upload(
        uploaded_file,
        settings.ALLOWED_VIDEO_TYPES,
        settings.MAX_VIDEO_SIZE_MB,
        "Video",
    )


def validate_product_file(uploaded_file):
    return _validate_upload(
        uploaded_file,
        ["application/zip", "image/jpeg", "image/png"],
        settings.MAX_PRODUCT_FILE_SIZE_MB,
        "Product file",
    )


def validate_pakistani_phone(value: str):
    cleaned = value.replace(" ", "").replace("-", "")
    if not PHONE_RE.match(cleaned):
        raise ValidationError(
            "Enter a valid Pakistani mobile number, e.g. 03001234567 or +923001234567."
        )
    return cleaned


def validate_future_date(value):
    if value < timezone.localdate():
        raise ValidationError("This date cannot be in the past.")
    return value


def validate_rating(value):
    if not 1 <= value <= 5:
        raise ValidationError("Rating must be between 1 and 5.")
    return value
