"""
Serializers for authentication and account management.

Serializers validate and shape data. They never write to the database beyond
their own model — all multi-step logic lives in services.py.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from apps.core.constants import UserRole
from apps.core.exceptions import AccountBlocked
from apps.core.validators import validate_pakistani_phone

User = get_user_model()


# ═══════════════════════════════════════════════════════════════════════════
# TOKENS
# ═══════════════════════════════════════════════════════════════════════════
class SnapSphereTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Adds custom claims so the mobile app can route to the right navigator
    without an extra /me request on every cold start.
    """

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["role"] = user.role
        token["full_name"] = user.full_name
        token["token_version"] = user.token_version
        token["is_email_verified"] = user.is_email_verified
        profile = getattr(user, "photographer_profile", None)
        token["is_approved"] = bool(profile.is_approved) if profile else True
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        user = self.user
        if user.is_blocked:
            raise AccountBlocked(user.blocked_reason or AccountBlocked.default_detail)
        data["user"] = UserSerializer(user, context=self.context).data
        return data


# ═══════════════════════════════════════════════════════════════════════════
# USER
# ═══════════════════════════════════════════════════════════════════════════
class UserSerializer(serializers.ModelSerializer):
    """
    The shape returned by /auth/me/ and embedded in the login response.

    Entirely read-only — every field is either a model field DRF marks
    read-only via Meta, or a computed method field. Writes go through
    UserUpdateSerializer, which exposes a deliberately narrower set.
    """

    avatar_url = serializers.SerializerMethodField()
    is_approved = serializers.SerializerMethodField()
    date_joined = serializers.DateTimeField(source="created_at", read_only=True)

    class Meta:
        model = User
        fields = (
            "id", "email", "full_name", "phone", "role",
            "avatar_url", "city", "latitude", "longitude",
            "is_email_verified", "is_phone_verified", "is_approved",
            "date_joined",
        )
        read_only_fields = (
            "id", "email", "full_name", "phone", "role",
            "city", "latitude", "longitude",
            "is_email_verified", "is_phone_verified",
        )

    def get_avatar_url(self, obj) -> str | None:
        if not obj.avatar:
            return None
        request = self.context.get("request")
        url = obj.avatar.url
        return request.build_absolute_uri(url) if request else url

    def get_is_approved(self, obj) -> bool:
        profile = getattr(obj, "photographer_profile", None)
        return bool(profile.is_approved) if profile else True


class UserUpdateSerializer(serializers.ModelSerializer):
    """
    Writable subset of the user record.

    `role`, `is_blocked`, `is_email_verified` and friends are deliberately
    absent: including them would let a client escalate its own privileges by
    adding one line to the request body.
    """

    class Meta:
        model = User
        fields = ("full_name", "phone", "city", "latitude", "longitude", "avatar")

    def validate_phone(self, value):
        return validate_pakistani_phone(value) if value else value

    def validate_full_name(self, value):
        value = value.strip()
        if len(value) < 3:
            raise serializers.ValidationError("Please enter your full name.")
        return value


# ═══════════════════════════════════════════════════════════════════════════
# REGISTRATION
# ═══════════════════════════════════════════════════════════════════════════
class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField()
    full_name = serializers.CharField(max_length=120)
    password = serializers.CharField(write_only=True, min_length=8, max_length=128)
    password_confirm = serializers.CharField(write_only=True)
    phone = serializers.CharField(max_length=20, required=False, allow_blank=True)
    city = serializers.CharField(max_length=80, required=False, allow_blank=True)
    role = serializers.ChoiceField(
        choices=[UserRole.BUYER, UserRole.PHOTOGRAPHER],  # ADMIN is not selectable
        default=UserRole.BUYER,
    )

    def validate_email(self, value):
        value = value.lower().strip()
        if User.all_objects.filter(email=value).exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return value

    def validate_phone(self, value):
        return validate_pakistani_phone(value) if value else value

    def validate_full_name(self, value):
        value = value.strip()
        if len(value) < 3:
            raise serializers.ValidationError("Please enter your full name.")
        return value

    def validate(self, attrs):
        if attrs["password"] != attrs.pop("password_confirm"):
            raise serializers.ValidationError({"password_confirm": "Passwords do not match."})
        # Run Django's configured validators (length, common-password list, ...)
        validate_password(attrs["password"])
        return attrs


# ═══════════════════════════════════════════════════════════════════════════
# PASSWORD
# ═══════════════════════════════════════════════════════════════════════════
class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=8)
    new_password_confirm = serializers.CharField(write_only=True)

    def validate_current_password(self, value):
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("Your current password is incorrect.")
        return value

    def validate(self, attrs):
        if attrs["new_password"] != attrs.pop("new_password_confirm"):
            raise serializers.ValidationError(
                {"new_password_confirm": "Passwords do not match."}
            )
        if attrs["new_password"] == attrs["current_password"]:
            raise serializers.ValidationError(
                {"new_password": "New password must be different from the current one."}
            )
        validate_password(attrs["new_password"], self.context["request"].user)
        return attrs


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value):
        # Deliberately NOT checking whether the account exists — a different
        # response here would let an attacker enumerate registered emails.
        return value.lower().strip()


class PasswordResetConfirmSerializer(serializers.Serializer):
    email = serializers.EmailField()
    code = serializers.CharField(max_length=6, min_length=6)
    new_password = serializers.CharField(write_only=True, min_length=8)
    new_password_confirm = serializers.CharField(write_only=True)

    def validate(self, attrs):
        if attrs["new_password"] != attrs.pop("new_password_confirm"):
            raise serializers.ValidationError(
                {"new_password_confirm": "Passwords do not match."}
            )
        validate_password(attrs["new_password"])
        attrs["email"] = attrs["email"].lower().strip()
        return attrs


# ═══════════════════════════════════════════════════════════════════════════
# VERIFICATION
# ═══════════════════════════════════════════════════════════════════════════
class OTPVerifySerializer(serializers.Serializer):
    code = serializers.CharField(max_length=6, min_length=6)


class ResendOTPSerializer(serializers.Serializer):
    purpose = serializers.ChoiceField(
        choices=["EMAIL_VERIFICATION", "PHONE_VERIFICATION"],
        default="EMAIL_VERIFICATION",
    )


# ═══════════════════════════════════════════════════════════════════════════
# DEVICES / LOGOUT
# ═══════════════════════════════════════════════════════════════════════════
class DeviceRegisterSerializer(serializers.Serializer):
    device_id = serializers.CharField(max_length=255)
    platform = serializers.ChoiceField(choices=["IOS", "ANDROID", "WEB"])
    push_token = serializers.CharField(max_length=512, required=False, allow_blank=True)
    app_version = serializers.CharField(max_length=32, required=False, allow_blank=True)


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField(
        help_text=_("The refresh token to blacklist.")
    )
    all_devices = serializers.BooleanField(
        default=False,
        help_text=_("Bump token_version, invalidating every session everywhere."),
    )
