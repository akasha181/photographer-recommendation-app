"""Background jobs for the accounts app."""

import logging

from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

logger = logging.getLogger("snapsphere")


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_verification_email(self, user_id: int, email: str, name: str, code: str):
    """Email delivery is slow and can fail — it never blocks the HTTP request."""
    try:
        send_mail(
            subject="Verify your SnapSphere account",
            message=(
                f"Hi {name},\n\n"
                f"Your SnapSphere verification code is: {code}\n\n"
                f"It expires in 15 minutes.\n\n"
                f"If you didn't create an account, you can ignore this email.\n\n"
                f"— The SnapSphere team"
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[email],
            fail_silently=False,
        )
        logger.info("Verification email sent", extra={"user_id": user_id})
    except Exception as exc:  # noqa: BLE001
        logger.warning("Verification email failed: %s", exc, extra={"user_id": user_id})
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_password_reset_email(self, user_id: int, email: str, name: str, code: str):
    try:
        send_mail(
            subject="Reset your SnapSphere password",
            message=(
                f"Hi {name},\n\n"
                f"Your password reset code is: {code}\n\n"
                f"It expires in 15 minutes.\n\n"
                f"If you didn't request this, no action is needed — your "
                f"password has not changed.\n\n"
                f"— The SnapSphere team"
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[email],
            fail_silently=False,
        )
        logger.info("Password reset email sent", extra={"user_id": user_id})
    except Exception as exc:  # noqa: BLE001
        raise self.retry(exc=exc)


@shared_task
def cleanup_expired_tokens():
    """
    Nightly hygiene.

    The JWT blacklist table grows with every refresh-token rotation. Rows for
    tokens that have already expired can never be presented again, so keeping
    them only slows down the blacklist lookup on every request.
    """
    from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

    from apps.accounts.models import OTPCode

    now = timezone.now()

    expired_tokens = OutstandingToken.objects.filter(expires_at__lt=now)
    blacklisted = BlacklistedToken.objects.filter(token__in=expired_tokens).delete()[0]
    outstanding = expired_tokens.delete()[0]
    otps = OTPCode.objects.filter(expires_at__lt=now).delete()[0]

    logger.info(
        "Token cleanup: %s blacklisted, %s outstanding, %s otps removed",
        blacklisted, outstanding, otps,
    )
    return {"blacklisted": blacklisted, "outstanding": outstanding, "otps": otps}
