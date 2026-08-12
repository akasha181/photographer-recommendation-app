"""
Identity models.

Design decisions worth defending in a viva:

1. EMAIL IS THE USERNAME. A separate username field is dead weight for a
   marketplace — users forget them, they collide, and they add a second
   uniqueness constraint for no benefit.

2. ROLE IS A COLUMN, NOT A GROUP. Django's Groups are flexible but require a
   join to answer "is this user a buyer?", which happens on literally every
   request. A single indexed CharField makes that check free, and the three
   roles here are genuinely fixed by the product.

3. TOKEN_VERSION EXISTS. JWTs are stateless, so a stolen access token normally
   stays valid until it expires. Bumping token_version invalidates every token
   ever issued to that user, instantly. It is the platform's kill switch.
"""

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.constants import UserRole
from apps.core.models import SoftDeleteModel, TimeStampedModel
from apps.core.utils import upload_to


class UserManager(BaseUserManager):
    """Manager for the email-based user model."""

    use_in_migrations = True

    def _create_user(self, email: str, password: str | None, **extra):
        if not email:
            raise ValueError("An email address is required.")
        email = self.normalize_email(email).lower()
        user = self.model(email=email, **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra):
        extra.setdefault("role", UserRole.BUYER)
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra)

    def create_photographer(self, email, password=None, **extra):
        extra["role"] = UserRole.PHOTOGRAPHER
        return self._create_user(email, password, **extra)

    def create_superuser(self, email, password=None, **extra):
        extra.setdefault("role", UserRole.ADMIN)
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        extra.setdefault("is_email_verified", True)
        if extra["is_staff"] is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra["is_superuser"] is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        return self._create_user(email, password, **extra)

    # ─── Query helpers ───────────────────────────────────────────────────────
    def buyers(self):
        return self.filter(role=UserRole.BUYER)

    def photographers(self):
        return self.filter(role=UserRole.PHOTOGRAPHER)

    def admins(self):
        return self.filter(role=UserRole.ADMIN)


class User(AbstractBaseUser, PermissionsMixin, TimeStampedModel, SoftDeleteModel):
    # ─── Identity ────────────────────────────────────────────────────────────
    email = models.EmailField(_("email address"), unique=True, db_index=True)
    full_name = models.CharField(max_length=120)
    phone = models.CharField(max_length=20, blank=True, db_index=True)
    role = models.CharField(
        max_length=20, choices=UserRole.choices, default=UserRole.BUYER, db_index=True
    )
    avatar = models.ImageField(upload_to=upload_to("avatars"), null=True, blank=True)

    # ─── Location (drives the distance filter and location-based matching) ───
    city = models.CharField(max_length=80, blank=True, db_index=True)
    latitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True
    )
    longitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True
    )

    # ─── Account state ───────────────────────────────────────────────────────
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    is_email_verified = models.BooleanField(default=False)
    is_phone_verified = models.BooleanField(default=False)

    is_blocked = models.BooleanField(default=False, db_index=True)
    blocked_reason = models.TextField(blank=True)
    blocked_at = models.DateTimeField(null=True, blank=True)
    blocked_by = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="blocked_users",
    )

    # ─── Security ────────────────────────────────────────────────────────────
    token_version = models.PositiveIntegerField(
        default=1,
        help_text="Bumped on password change or ban; invalidates all issued JWTs.",
    )
    failed_login_attempts = models.PositiveSmallIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)
    last_login_ip = models.GenericIPAddressField(null=True, blank=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["full_name"]

    objects = UserManager()

    class Meta:
        db_table = "users"
        verbose_name = "User"
        verbose_name_plural = "Users"
        indexes = [
            models.Index(fields=["role", "is_active"], name="idx_user_role_active"),
            models.Index(fields=["city", "role"], name="idx_user_city_role"),
            models.Index(fields=["is_blocked", "role"], name="idx_user_blocked_role"),
        ]

    def __str__(self) -> str:
        return f"{self.full_name} <{self.email}>"

    # ─── Role shortcuts (readability at call sites) ──────────────────────────
    @property
    def is_buyer(self) -> bool:
        return self.role == UserRole.BUYER

    @property
    def is_photographer(self) -> bool:
        return self.role == UserRole.PHOTOGRAPHER

    @property
    def is_admin_user(self) -> bool:
        return self.role == UserRole.ADMIN

    @property
    def is_locked_out(self) -> bool:
        return bool(self.locked_until and self.locked_until > timezone.now())

    @property
    def first_name_only(self) -> str:
        return self.full_name.split(" ")[0] if self.full_name else ""

    # ─── Security operations ─────────────────────────────────────────────────
    def invalidate_tokens(self) -> None:
        """Kill every JWT issued to this user, right now."""
        self.token_version += 1
        self.save(update_fields=["token_version", "updated_at"])

    def register_failed_login(self, max_attempts: int = 10, lock_minutes: int = 30):
        from datetime import timedelta

        self.failed_login_attempts += 1
        fields = ["failed_login_attempts", "updated_at"]
        if self.failed_login_attempts >= max_attempts:
            self.locked_until = timezone.now() + timedelta(minutes=lock_minutes)
            fields.append("locked_until")
        self.save(update_fields=fields)

    def reset_failed_logins(self, ip: str | None = None):
        self.failed_login_attempts = 0
        self.locked_until = None
        fields = ["failed_login_attempts", "locked_until", "updated_at"]
        if ip:
            self.last_login_ip = ip
            fields.append("last_login_ip")
        self.save(update_fields=fields)

    def block(self, reason: str, by=None):
        self.is_blocked = True
        self.is_active = False
        self.blocked_reason = reason
        self.blocked_at = timezone.now()
        self.blocked_by = by
        self.token_version += 1  # boot them out of every open session
        self.save(
            update_fields=[
                "is_blocked", "is_active", "blocked_reason",
                "blocked_at", "blocked_by", "token_version", "updated_at",
            ]
        )

    def unblock(self):
        self.is_blocked = False
        self.is_active = True
        self.blocked_reason = ""
        self.blocked_at = None
        self.blocked_by = None
        self.save(
            update_fields=[
                "is_blocked", "is_active", "blocked_reason",
                "blocked_at", "blocked_by", "updated_at",
            ]
        )


class OTPPurpose(models.TextChoices):
    EMAIL_VERIFICATION = "EMAIL_VERIFICATION", "Email verification"
    PHONE_VERIFICATION = "PHONE_VERIFICATION", "Phone verification"
    PASSWORD_RESET = "PASSWORD_RESET", "Password reset"
    LOGIN_2FA = "LOGIN_2FA", "Two-factor login"


class OTPCode(TimeStampedModel):
    """
    Short-lived numeric codes.

    The code is stored hashed, exactly like a password. A leaked database
    otherwise hands an attacker every live password-reset code.
    """

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="otp_codes")
    code_hash = models.CharField(max_length=128)
    purpose = models.CharField(max_length=32, choices=OTPPurpose.choices, db_index=True)
    expires_at = models.DateTimeField(db_index=True)
    used_at = models.DateTimeField(null=True, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = "otp_codes"
        indexes = [
            models.Index(fields=["user", "purpose", "used_at"], name="idx_otp_lookup"),
        ]

    def __str__(self) -> str:
        return f"OTP({self.purpose}) for {self.user_id}"

    @property
    def is_expired(self) -> bool:
        return timezone.now() > self.expires_at

    @property
    def is_usable(self) -> bool:
        return self.used_at is None and not self.is_expired and self.attempts < 5


class DevicePlatform(models.TextChoices):
    IOS = "IOS", "iOS"
    ANDROID = "ANDROID", "Android"
    WEB = "WEB", "Web"


class Device(TimeStampedModel):
    """
    A logged-in device. Powers push notifications and "log out everywhere".
    """

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="devices")
    device_id = models.CharField(max_length=255, db_index=True)
    platform = models.CharField(max_length=16, choices=DevicePlatform.choices)
    push_token = models.CharField(max_length=512, blank=True)
    app_version = models.CharField(max_length=32, blank=True)
    last_seen_at = models.DateTimeField(default=timezone.now)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "devices"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "device_id"], name="uniq_user_device"
            )
        ]

    def __str__(self) -> str:
        return f"{self.platform} device for {self.user_id}"
