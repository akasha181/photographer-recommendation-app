"""
Account business logic — the ONLY place account state is changed.

Every function here is transactional and returns domain objects, never HTTP
responses. That separation is what lets the same logic be reused by a
management command, a Celery task and an API view without duplication.
"""

import logging
import secrets
import threading
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password, make_password
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Device, OTPCode, OTPPurpose
from apps.core.constants import UserRole
from apps.core.exceptions import AccountBlocked, BusinessRuleViolation

User = get_user_model()
logger = logging.getLogger("snapsphere")

OTP_TTL_MINUTES = 15
OTP_LENGTH = 6
MAX_OTP_ATTEMPTS = 10


# ═══════════════════════════════════════════════════════════════════════════
# OTP
# ═══════════════════════════════════════════════════════════════════════════
def _generate_otp() -> str:
    """Cryptographically secure 6-digit code (secrets, not random)."""
    return "".join(secrets.choice("0123456789") for _ in range(OTP_LENGTH))


@transaction.atomic
def issue_otp(user, purpose: str) -> str:
    """
    Create a fresh OTP, deleting any outstanding ones for the same purpose.
    """
    OTPCode.objects.filter(user=user, purpose=purpose).delete()

    code = _generate_otp()
    OTPCode.objects.create(
        user=user,
        code_hash=make_password(code),
        purpose=purpose,
        expires_at=timezone.now() + timedelta(minutes=OTP_TTL_MINUTES),
    )
    logger.info("OTP issued", extra={"user_id": user.id, "purpose": purpose})
    return code


@transaction.atomic
def verify_otp(user, code: str, purpose: str) -> bool:
    """
    Check a submitted code.
    Matches against any valid unexpired OTP created for this user and purpose.
    """
    clean_code = str(code).strip().replace(" ", "")
    if not clean_code:
        raise BusinessRuleViolation("Please enter the 6-digit code.")

    valid_otps = (
        OTPCode.objects.select_for_update()
        .filter(
            user=user,
            purpose=purpose,
            expires_at__gt=timezone.now(),
        )
        .order_by("-created_at")
    )

    if not valid_otps.exists():
        raise BusinessRuleViolation("No active verification code was found. Please request a new code.")

    for otp_obj in valid_otps:
        if otp_obj.attempts >= MAX_OTP_ATTEMPTS:
            continue
        if check_password(clean_code, otp_obj.code_hash):
            otp_obj.used_at = timezone.now()
            otp_obj.save(update_fields=["used_at", "updated_at"])
            valid_otps.exclude(id=otp_obj.id).update(used_at=timezone.now())
            return True

    # If no match, increment attempt counter on the newest OTP
    newest = valid_otps.first()
    if newest:
        newest.attempts += 1
        newest.save(update_fields=["attempts", "updated_at"])
        remaining = max(0, MAX_OTP_ATTEMPTS - newest.attempts)
        if remaining == 0:
            raise BusinessRuleViolation("Too many incorrect attempts. Please request a new code.")
        raise BusinessRuleViolation(
            f"Incorrect code. {remaining} attempt{'s' if remaining != 1 else ''} remaining."
        )

    raise BusinessRuleViolation("Invalid or expired code. Please request a new code.")


# ═══════════════════════════════════════════════════════════════════════════
# REGISTRATION
# ═══════════════════════════════════════════════════════════════════════════
@transaction.atomic
def register_user(
    *, email: str, full_name: str, password: str, role: str = UserRole.BUYER,
    phone: str = "", city: str = "",
):
    """
    Create a user plus its role-specific profile.

    Wrapped in a transaction because a User without its profile is a broken
    record that would crash every later request — either both rows exist or
    neither does.
    """
    from apps.profiles.services import create_buyer_profile, create_photographer_profile

    if role == UserRole.ADMIN:
        # Defence in depth: the serializer already excludes ADMIN from choices.
        raise BusinessRuleViolation("Admin accounts cannot be created through registration.")

    user = User.objects.create_user(
        email=email,
        password=password,
        full_name=full_name,
        role=role,
        phone=phone or "",
        city=city or "",
    )

    if role == UserRole.PHOTOGRAPHER:
        create_photographer_profile(user)
    else:
        create_buyer_profile(user)

    code = issue_otp(user, OTPPurpose.EMAIL_VERIFICATION)

    # Sent after commit so we never email a code for a rolled-back signup.
    transaction.on_commit(
        lambda: _send_verification_email(user.id, user.email, user.full_name, code)
    )

    logger.info("User registered", extra={"user_id": user.id, "role": role})
    return user


def _send_verification_email(user_id: int, email: str, name: str, code: str) -> None:
    from apps.accounts.tasks import send_verification_email

    threading.Thread(
        target=lambda: send_verification_email(user_id, email, name, code),
        daemon=True,
    ).start()


@transaction.atomic
def verify_email(user, code: str):
    verify_otp(user, code, OTPPurpose.EMAIL_VERIFICATION)
    user.is_email_verified = True
    user.save(update_fields=["is_email_verified", "updated_at"])
    return user


# ═══════════════════════════════════════════════════════════════════════════
# LOGIN SUPPORT
# ═══════════════════════════════════════════════════════════════════════════
def assert_can_login(user) -> None:
    """Gate checks that run before tokens are issued."""
    if user.is_blocked:
        raise AccountBlocked(user.blocked_reason or AccountBlocked.default_detail)
    if user.is_locked_out:
        minutes = int((user.locked_until - timezone.now()).total_seconds() // 60) + 1
        raise BusinessRuleViolation(
            f"Account temporarily locked after too many failed attempts. "
            f"Try again in {minutes} minute{'s' if minutes != 1 else ''}."
        )
    if not user.is_active:
        raise BusinessRuleViolation("This account has been deactivated.")


def client_ip(request) -> str | None:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


# ═══════════════════════════════════════════════════════════════════════════
# PASSWORD
# ═══════════════════════════════════════════════════════════════════════════
@transaction.atomic
def change_password(user, new_password: str):
    """
    Change the password and log every other session out.

    Bumping token_version is the point: a user who changes their password
    because they think they were compromised expects the attacker's session
    to die, and a stateless JWT would otherwise survive until it expired.
    """
    user.set_password(new_password)
    user.token_version += 1
    user.save(update_fields=["password", "token_version", "updated_at"])
    logger.info("Password changed", extra={"user_id": user.id})
    return user


@transaction.atomic
def request_password_reset(email: str) -> str | None:
    """
    Always succeeds from the caller's point of view.

    If the email is not registered we do nothing but still return normally, so
    the response is byte-identical either way and cannot be used to discover
    which addresses have accounts.
    """
    user = User.objects.filter(email=email, is_blocked=False).first()
    if user is None:
        logger.info("Password reset requested for unknown email")
        return None

    code = issue_otp(user, OTPPurpose.PASSWORD_RESET)
    transaction.on_commit(
        lambda: _send_reset_email(user.id, user.email, user.full_name, code)
    )
    return code


def _send_reset_email(user_id: int, email: str, name: str, code: str) -> None:
    from apps.accounts.tasks import send_password_reset_email

    threading.Thread(
        target=lambda: send_password_reset_email(user_id, email, name, code),
        daemon=True,
    ).start()


@transaction.atomic
def confirm_password_reset(email: str, code: str, new_password: str):
    clean_email = email.lower().strip()
    user = User.objects.filter(email__iexact=clean_email, is_blocked=False).first()
    if user is None:
        # Same generic message as a wrong code — no enumeration signal.
        raise BusinessRuleViolation("Invalid or expired reset code.")

    verify_otp(user, code, OTPPurpose.PASSWORD_RESET)

    user.set_password(new_password)
    user.token_version += 1
    user.failed_login_attempts = 0
    user.locked_until = None
    user.save(
        update_fields=[
            "password", "token_version", "failed_login_attempts",
            "locked_until", "updated_at",
        ]
    )
    logger.info("Password reset completed", extra={"user_id": user.id})
    return user


# ═══════════════════════════════════════════════════════════════════════════
# DEVICES
# ═══════════════════════════════════════════════════════════════════════════
def register_device(user, *, device_id: str, platform: str,
                    push_token: str = "", app_version: str = ""):
    device, _created = Device.objects.update_or_create(
        user=user,
        device_id=device_id,
        defaults={
            "platform": platform,
            "push_token": push_token,
            "app_version": app_version,
            "last_seen_at": timezone.now(),
            "is_active": True,
        },
    )
    return device


def deactivate_device(user, device_id: str) -> None:
    Device.objects.filter(user=user, device_id=device_id).update(is_active=False)


@transaction.atomic
def logout_everywhere(user):
    """Invalidate all JWTs and mark every device inactive."""
    user.invalidate_tokens()
    Device.objects.filter(user=user).update(is_active=False)
    return user


# ═══════════════════════════════════════════════════════════════════════════
# ACCOUNT DELETION (GDPR-style right to erasure)
# ═══════════════════════════════════════════════════════════════════════════
@transaction.atomic
def delete_account(user, reason: str = ""):
    """
    Soft-delete and anonymise.

    Financial and booking records must survive for accounting and for the
    other party's history, so we scrub personal data in place rather than
    cascading a hard delete through the whole schema.
    """
    from apps.bookings.models import Booking, BookingStatus

    active = Booking.objects.filter(
        status__in=[BookingStatus.PENDING, BookingStatus.ACCEPTED]
    ).filter(models_q_for_user(user))
    if active.exists():
        raise BusinessRuleViolation(
            "You have active bookings. Please complete or cancel them before "
            "deleting your account."
        )

    anon = f"deleted-user-{user.pk}@snapsphere.invalid"
    user.email = anon
    user.full_name = "Deleted User"
    user.phone = ""
    user.avatar = None
    user.is_active = False
    user.token_version += 1
    user.delete()  # soft delete
    user.save(
        update_fields=[
            "email", "full_name", "phone", "avatar",
            "is_active", "token_version", "updated_at",
        ]
    )
    logger.info("Account deleted", extra={"user_id": user.pk, "reason": reason})


def models_q_for_user(user):
    """Q object matching bookings on whichever side this user sits."""
    from django.db.models import Q

    if user.role == UserRole.PHOTOGRAPHER:
        return Q(photographer__user=user)
    return Q(buyer=user)
