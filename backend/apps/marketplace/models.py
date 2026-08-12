"""
Digital marketplace — presets, LUTs, templates, stock photos.

THE SECURITY PROBLEM THIS SCHEMA SOLVES
---------------------------------------
A digital product is worthless the moment its file URL leaks. So the actual
file NEVER lives under MEDIA_ROOT and is never served by a guessable URL.
Instead:

    ProductFile.file  →  stored in PRIVATE_MEDIA_ROOT (outside the web root)
    DownloadToken     →  single-use, 15-minute, ownership-checked ticket
    Nginx X-Accel-Redirect  →  streams the bytes only after Django says yes

`download_count` and `max_downloads` then cap how often a purchase can be
redeemed, which limits the damage if a buyer shares their account.
"""

import uuid
from decimal import Decimal

from django.db import models
from django.utils import timezone
from django.utils.text import slugify

from apps.core.models import BaseModel, TimeStampedModel, UUIDModel
from apps.core.storage import private_storage
from apps.core.utils import upload_to


class ProductType(models.TextChoices):
    LIGHTROOM_PRESET = "LIGHTROOM_PRESET", "Lightroom Preset"
    PHOTOSHOP_TEMPLATE = "PHOTOSHOP_TEMPLATE", "Photoshop Template"
    ALBUM_TEMPLATE = "ALBUM_TEMPLATE", "Album Template"
    WEDDING_LUT = "WEDDING_LUT", "Wedding LUT"
    VIDEO_EFFECT = "VIDEO_EFFECT", "Video Effect"
    STOCK_PHOTO = "STOCK_PHOTO", "Stock Photo"
    OVERLAY = "OVERLAY", "Overlay Pack"
    OTHER = "OTHER", "Other"


class LicenseType(models.TextChoices):
    PERSONAL = "PERSONAL", "Personal use only"
    COMMERCIAL = "COMMERCIAL", "Commercial use"
    EXTENDED = "EXTENDED", "Extended commercial"


class DigitalProduct(UUIDModel, BaseModel):
    seller = models.ForeignKey(
        "profiles.PhotographerProfile", on_delete=models.CASCADE,
        related_name="products",
    )
    category = models.ForeignKey(
        "catalog.Category", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="products",
    )

    title = models.CharField(max_length=160)
    slug = models.SlugField(max_length=180, unique=True, db_index=True)
    description = models.TextField(max_length=5000, blank=True)
    product_type = models.CharField(
        max_length=32, choices=ProductType.choices, db_index=True
    )
    license_type = models.CharField(
        max_length=16, choices=LicenseType.choices, default=LicenseType.PERSONAL
    )

    # ─── Pricing ─────────────────────────────────────────────────────────────
    price = models.DecimalField(max_digits=10, decimal_places=2, db_index=True)
    compare_at_price = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text="Original price, shown struck through to display a discount.",
    )
    commission_percent = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("15.00")
    )

    # ─── Public preview assets (these ARE served publicly, by design) ────────
    thumbnail = models.ImageField(upload_to=upload_to("products/thumbs"))
    preview_images = models.JSONField(default=list, blank=True)
    preview_video_url = models.URLField(blank=True)

    # ─── Metadata ────────────────────────────────────────────────────────────
    file_count = models.PositiveSmallIntegerField(default=1)
    total_size_mb = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    compatible_with = models.JSONField(
        default=list, blank=True,
        help_text='e.g. ["Lightroom Classic 12+", "Lightroom Mobile"]',
    )
    tags = models.JSONField(default=list, blank=True)

    # ─── State ───────────────────────────────────────────────────────────────
    is_published = models.BooleanField(default=False, db_index=True)
    is_approved = models.BooleanField(
        default=False, db_index=True,
        help_text="Admin moderation gate — blocks copyright-infringing uploads.",
    )
    is_featured = models.BooleanField(default=False)
    published_at = models.DateTimeField(null=True, blank=True)

    # ─── Denormalised metrics ────────────────────────────────────────────────
    sales_count = models.PositiveIntegerField(default=0, db_index=True)
    view_count = models.PositiveIntegerField(default=0)
    wishlist_count = models.PositiveIntegerField(default=0)
    avg_rating = models.DecimalField(
        max_digits=3, decimal_places=2, default=Decimal("0.00")
    )
    reviews_count = models.PositiveIntegerField(default=0)
    total_revenue = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal("0.00")
    )

    class Meta:
        db_table = "digital_products"
        ordering = ("-created_at",)
        indexes = [
            models.Index(
                fields=["is_published", "is_approved", "-sales_count"],
                name="idx_product_browse",
            ),
            models.Index(fields=["product_type", "price"], name="idx_product_type_price"),
            models.Index(fields=["seller", "is_published"], name="idx_product_by_seller"),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(price__gte=0), name="ck_product_price_positive"
            ),
        ]

    def __str__(self) -> str:
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            # A timestamp suffix is NOT unique enough — two products created in
            # the same second (bulk import, a seller publishing a bundle)
            # collide on the unique index. A random suffix cannot.
            base = slugify(self.title)[:150]
            self.slug = f"{base}-{uuid.uuid4().hex[:8]}"
        super().save(*args, **kwargs)

    @property
    def is_purchasable(self) -> bool:
        return self.is_published and self.is_approved and not self.is_deleted

    @property
    def discount_percent(self) -> int:
        if not self.compare_at_price or self.compare_at_price <= self.price:
            return 0
        return int((1 - self.price / self.compare_at_price) * 100)


class ProductFile(TimeStampedModel):
    """
    The deliverable itself.

    `file` is bound to `private_storage`, which writes under
    PRIVATE_MEDIA_ROOT and has no `base_url` — calling `.url` on it raises
    rather than handing out a public link. Anything that wants these bytes
    must go through the download-token flow.
    """

    product = models.ForeignKey(
        DigitalProduct, on_delete=models.CASCADE, related_name="files"
    )
    name = models.CharField(max_length=200)
    file = models.FileField(upload_to="products/%Y/%m/", storage=private_storage)
    file_size_mb = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    checksum = models.CharField(
        max_length=64, blank=True,
        help_text="SHA-256, so corrupted downloads can be detected.",
    )
    display_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = "product_files"
        ordering = ("display_order",)

    def __str__(self) -> str:
        return self.name


class OrderStatus(models.TextChoices):
    PENDING = "PENDING", "Pending payment"
    PAID = "PAID", "Paid"
    FAILED = "FAILED", "Failed"
    REFUNDED = "REFUNDED", "Refunded"
    CANCELLED = "CANCELLED", "Cancelled"


class Order(UUIDModel, TimeStampedModel):
    """A basket checkout. One order, many items, one wallet debit."""

    buyer = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, related_name="orders"
    )
    order_number = models.CharField(max_length=32, unique=True, db_index=True)

    subtotal = models.DecimalField(max_digits=12, decimal_places=2)
    discount = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0.00")
    )
    total = models.DecimalField(max_digits=12, decimal_places=2)

    status = models.CharField(
        max_length=16, choices=OrderStatus.choices,
        default=OrderStatus.PENDING, db_index=True,
    )
    payment_method = models.CharField(max_length=20, default="WALLET")
    paid_at = models.DateTimeField(null=True, blank=True)

    # Guards against a double-tap on Checkout creating two identical orders.
    idempotency_key = models.CharField(
        max_length=64, blank=True, db_index=True
    )

    class Meta:
        db_table = "orders"
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["buyer", "status"], name="idx_order_buyer_status"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["buyer", "idempotency_key"],
                condition=~models.Q(idempotency_key=""),
                name="uniq_order_idempotency",
            ),
        ]

    def __str__(self) -> str:
        return self.order_number

    def save(self, *args, **kwargs):
        if not self.order_number:
            # A whole-second timestamp is NOT unique enough — two buyers
            # checking out in the same second collide on the unique index and
            # the second one gets a 500. The random suffix is the same fix
            # DigitalProduct.save() already applies to its slug.
            self.order_number = f"ORD-{timezone.now():%Y%m%d}-{uuid.uuid4().hex[:10].upper()}"
        super().save(*args, **kwargs)


class OrderItem(TimeStampedModel):
    """
    One purchased product.

    Title and price are copied here: an order is a receipt, and a receipt that
    changes when the seller edits their listing is not a receipt.
    """

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(
        DigitalProduct, on_delete=models.PROTECT, related_name="order_items"
    )
    seller = models.ForeignKey(
        "profiles.PhotographerProfile", on_delete=models.PROTECT,
        related_name="sales",
    )

    product_title = models.CharField(max_length=160)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    commission_amount = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0.00")
    )
    seller_earning = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0.00")
    )

    download_count = models.PositiveSmallIntegerField(default=0)
    max_downloads = models.PositiveSmallIntegerField(default=5)
    has_review = models.BooleanField(default=False)

    class Meta:
        db_table = "order_items"
        constraints = [
            # A buyer must not be able to purchase the same product twice in
            # one order — the UI prevents it, the database enforces it.
            models.UniqueConstraint(
                fields=["order", "product"], name="uniq_product_per_order"
            ),
        ]
        indexes = [
            models.Index(fields=["seller", "-created_at"], name="idx_orderitem_seller"),
        ]

    def __str__(self) -> str:
        return f"{self.product_title} in {self.order.order_number}"

    @property
    def downloads_remaining(self) -> int:
        return max(self.max_downloads - self.download_count, 0)


class DownloadToken(TimeStampedModel):
    """
    A single-use ticket authorising one download of one file.

    Short-lived by design: even if the URL is copied out of a browser's
    history or a proxy log, it is dead within 15 minutes and dead immediately
    after first use.
    """

    order_item = models.ForeignKey(
        OrderItem, on_delete=models.CASCADE, related_name="download_tokens"
    )
    product_file = models.ForeignKey(
        ProductFile, on_delete=models.CASCADE, related_name="download_tokens"
    )
    user = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="download_tokens"
    )

    token = models.CharField(max_length=64, unique=True, db_index=True)
    expires_at = models.DateTimeField(db_index=True)
    used_at = models.DateTimeField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        db_table = "download_tokens"
        indexes = [
            models.Index(fields=["token", "expires_at"], name="idx_dl_token_lookup"),
        ]

    def __str__(self) -> str:
        return f"Token for order item {self.order_item_id}"

    @property
    def is_valid(self) -> bool:
        return self.used_at is None and timezone.now() < self.expires_at


class CartItem(TimeStampedModel):
    """Server-side cart, so a basket survives reinstalling the app."""

    user = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="cart_items"
    )
    product = models.ForeignKey(
        DigitalProduct, on_delete=models.CASCADE, related_name="in_carts"
    )

    class Meta:
        db_table = "cart_items"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "product"], name="uniq_cart_item_per_user"
            )
        ]

    def __str__(self) -> str:
        return f"{self.product.title} in {self.user.email}'s cart"
