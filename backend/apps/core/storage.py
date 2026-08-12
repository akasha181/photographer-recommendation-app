"""
Storage backends.

THE BUG THIS FILE FIXES
-----------------------
`marketplace/models.py` documents that digital-product files live outside
MEDIA_ROOT and are reachable only through a signed, single-use download
token. `PRIVATE_MEDIA_ROOT` was defined in settings to hold them — but
`ProductFile.file` was a plain `FileField`, which uses `default_storage`.
Default storage is MEDIA_ROOT, which Django serves directly in DEBUG and
Nginx serves in production.

The result was that every paid product sat at a guessable public URL
(`/media/private/products/2026/07/<name>`), and the whole token flow guarded
a door that had no wall next to it. Declaring the setting is not the same as
using it.

`private_storage` below is the wall.
"""

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.utils.deconstruct import deconstructible


@deconstructible
class PrivateMediaStorage(FileSystemStorage):
    """
    Files that must never be served by a URL.

    `url()` raises rather than returning a link. Passing `base_url=None` to
    FileSystemStorage is NOT enough — its `base_url` property falls back to
    `settings.MEDIA_URL`, so `.url` would return `/media/products/…`: a path
    that 404s (the bytes are in PRIVATE_MEDIA_ROOT, not MEDIA_ROOT) but looks
    perfectly valid in a JSON response. A misleading URL is worse than an
    error, because it gets shipped. Overriding `url()` makes a serializer that
    tries to expose a paid file fail loudly in development instead.

    Must be `@deconstructible` — `makemigrations` cannot serialise a storage
    instance otherwise. The same rule bit `upload_to` earlier in this project.
    """

    def __init__(self, **kwargs):
        kwargs.setdefault("location", settings.PRIVATE_MEDIA_ROOT)
        super().__init__(**kwargs)

    def url(self, name):
        raise ValueError(
            "Private media has no public URL. Issue a DownloadToken instead — "
            "see apps/marketplace/services.issue_download_token."
        )

    def __eq__(self, other):
        # Django compares storage instances when deciding whether a field
        # changed. Without this every `makemigrations` run emits a spurious
        # AlterField for the same storage.
        return isinstance(other, PrivateMediaStorage)

    def __hash__(self):
        return hash(PrivateMediaStorage)


private_storage = PrivateMediaStorage()
