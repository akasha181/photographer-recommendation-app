"""
Custom JWT authentication.

WHY THE DEFAULT IS NOT ENOUGH
-----------------------------
`rest_framework_simplejwt.authentication.JWTAuthentication` validates the
signature and the expiry, then loads the user. That is all. It does NOT look
at custom claims, and it does NOT re-check account state.

Which means, with the stock class:

  * An admin blocks a user  →  their access token keeps working for 30 minutes.
  * A user changes their password after a breach  →  the attacker's stolen
    access token keeps working for 30 minutes.
  * A photographer is suspended mid-shoot  →  they can still accept bookings.

Thirty minutes is a long time when the whole point of blocking someone is that
they are doing damage right now.

This subclass closes that window by re-validating on every request:

  1. token_version in the JWT must equal the user's current token_version.
     Bumping the column (block, password change, "log out everywhere")
     invalidates every token ever issued to that user, instantly.
  2. The account must still be active and not blocked.

COST: one extra comparison against a user row we were already fetching, so
there is no additional query. The stateless-JWT performance story is intact;
we have simply stopped trusting a claim we already had in hand.
"""

from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication

from apps.core.constants import ErrorCode


class SnapSphereJWTAuthentication(JWTAuthentication):
    def get_user(self, validated_token):
        # Imported lazily: this module is loaded by DRF while it is still
        # initialising its settings, and apps.core.exceptions imports
        # rest_framework.views — a module-level import here is a circular
        # import that crashes the whole application at startup.
        from apps.core.exceptions import AccountBlocked

        user = super().get_user(validated_token)

        if user.is_blocked:
            raise AccountBlocked(
                user.blocked_reason or "Your account has been blocked. Contact support."
            )

        if not user.is_active:
            raise AuthenticationFailed(
                "This account has been deactivated.", code=ErrorCode.TOKEN_INVALID
            )

        # The kill switch. A token minted before the bump carries the old
        # version and is refused here.
        token_version = validated_token.get("token_version")
        if token_version is not None and token_version != user.token_version:
            raise AuthenticationFailed(
                "Your session has ended. Please log in again.",
                code=ErrorCode.TOKEN_INVALID,
            )

        return user
