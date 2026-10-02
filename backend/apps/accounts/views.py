"""
Authentication endpoints.

Views stay thin on purpose: authenticate, authorise, validate, delegate to
services, return. Any view growing past ~15 lines of logic means something
belongs in services.py instead.
"""

from django.conf import settings
from django.contrib.auth import get_user_model
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.generics import GenericAPIView
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from apps.accounts import services
from apps.accounts.models import OTPPurpose
from apps.accounts.serializers import (
    ChangePasswordSerializer,
    DeviceRegisterSerializer,
    LogoutSerializer,
    OTPVerifySerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    RegisterSerializer,
    ResendOTPSerializer,
    SnapSphereTokenObtainPairSerializer,
    UserSerializer,
    UserUpdateSerializer,
)
from apps.core.exceptions import BusinessRuleViolation

User = get_user_model()


# ═══════════════════════════════════════════════════════════════════════════
# REGISTER
# ═══════════════════════════════════════════════════════════════════════════
@extend_schema(tags=["Auth"], summary="Register a buyer or photographer account")
class RegisterView(GenericAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]
    throttle_classes = []

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = services.register_user(**serializer.validated_data)

        # Issue tokens immediately so the app can proceed to the "verify your
        # email" screen already authenticated, instead of asking them to log in.
        refresh = SnapSphereTokenObtainPairSerializer.get_token(user)
        response = Response(
            {
                "message": "Account created. We sent a verification code to your email.",
                "data": {
                    "user": UserSerializer(user, context={"request": request}).data,
                    "tokens": {
                        "access": str(refresh.access_token),
                        "refresh": str(refresh),
                    },
                },
            },
            status=status.HTTP_201_CREATED,
        )
        return response


# ═══════════════════════════════════════════════════════════════════════════
# LOGIN / TOKENS
# ═══════════════════════════════════════════════════════════════════════════
@extend_schema(tags=["Auth"], summary="Log in and obtain a token pair")
class LoginView(TokenObtainPairView):
    serializer_class = SnapSphereTokenObtainPairSerializer
    permission_classes = [AllowAny]
    throttle_classes = []

    def post(self, request, *args, **kwargs):
        email = str(request.data.get("email", "")).lower().strip()
        user = User.objects.filter(email=email).first()

        if user:
            services.assert_can_login(user)

        serializer = self.get_serializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
        except Exception:
            # Record the failure against the account so repeated guessing
            # eventually locks it, then re-raise the generic error.
            if user:
                user.register_failed_login()
            raise

        if user:
            user.reset_failed_logins(ip=services.client_ip(request))

        data = serializer.validated_data
        user_data = data.pop("user", None)
        return Response(
            {
                "message": "Logged in successfully",
                "data": {
                    "user": user_data,
                    "tokens": {"access": data["access"], "refresh": data["refresh"]},
                },
            }
        )


@extend_schema(tags=["Auth"], summary="Exchange a refresh token for a new pair")
class RefreshView(TokenRefreshView):
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        return Response({"message": "Token refreshed", "data": response.data})


@extend_schema(tags=["Auth"], summary="Log out (blacklist refresh token)")
class LogoutView(GenericAPIView):
    serializer_class = LogoutSerializer
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        if serializer.validated_data.get("all_devices"):
            services.logout_everywhere(request.user)
            return Response({"message": "Logged out from all devices", "data": None})

        try:
            RefreshToken(serializer.validated_data["refresh"]).blacklist()
        except TokenError:
            # Already expired or already blacklisted — the user's intent is
            # satisfied either way, so this is not an error worth surfacing.
            pass
        return Response({"message": "Logged out successfully", "data": None})


# ═══════════════════════════════════════════════════════════════════════════
# CURRENT USER
# ═══════════════════════════════════════════════════════════════════════════
@extend_schema(tags=["Auth"], summary="Get or update the signed-in user")
class MeView(GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = UserSerializer
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get(self, request):
        return Response(
            {
                "message": "Profile retrieved",
                "data": UserSerializer(request.user, context={"request": request}).data,
            }
        )

    def patch(self, request):
        serializer = UserUpdateSerializer(
            request.user, data=request.data, partial=True, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(
            {
                "message": "Profile updated",
                "data": UserSerializer(user, context={"request": request}).data,
            }
        )


# ═══════════════════════════════════════════════════════════════════════════
# EMAIL VERIFICATION
# ═══════════════════════════════════════════════════════════════════════════
@extend_schema(tags=["Auth"], summary="Verify email with the 6-digit code")
class VerifyEmailView(GenericAPIView):
    serializer_class = OTPVerifySerializer
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        if request.user.is_email_verified:
            raise BusinessRuleViolation("Your email is already verified.")

        user = services.verify_email(request.user, serializer.validated_data["code"])
        return Response(
            {
                "message": "Email verified successfully",
                "data": UserSerializer(user, context={"request": request}).data,
            }
        )


@extend_schema(tags=["Auth"], summary="Resend a verification code")
class ResendOTPView(GenericAPIView):
    serializer_class = ResendOTPSerializer
    permission_classes = [IsAuthenticated]
    throttle_classes = []

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        purpose = serializer.validated_data["purpose"]

        if purpose == OTPPurpose.EMAIL_VERIFICATION and request.user.is_email_verified:
            raise BusinessRuleViolation("Your email is already verified.")

        code = services.issue_otp(request.user, purpose)
        from apps.accounts.tasks import send_verification_email

        send_verification_email.delay(
            request.user.id, request.user.email, request.user.full_name, code
        )
        return Response({"message": "A new code has been sent.", "data": None})


# ═══════════════════════════════════════════════════════════════════════════
# PASSWORD
# ═══════════════════════════════════════════════════════════════════════════
@extend_schema(tags=["Auth"], summary="Change password while signed in")
class ChangePasswordView(GenericAPIView):
    serializer_class = ChangePasswordSerializer
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = services.change_password(
            request.user, serializer.validated_data["new_password"]
        )
        # token_version changed, so the caller's current tokens are now dead —
        # hand back a fresh pair so they are not logged out of this device.
        refresh = SnapSphereTokenObtainPairSerializer.get_token(user)
        return Response(
            {
                "message": "Password changed. Other devices have been signed out.",
                "data": {
                    "tokens": {
                        "access": str(refresh.access_token),
                        "refresh": str(refresh),
                    }
                },
            }
        )


@extend_schema(
    tags=["Auth"],
    summary="Request a password-reset code",
    responses={200: OpenApiResponse(description="Always 200, even for unknown emails")},
)
class PasswordResetRequestView(GenericAPIView):
    serializer_class = PasswordResetRequestSerializer
    permission_classes = [AllowAny]
    throttle_classes = []

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.request_password_reset(serializer.validated_data["email"])
        return Response(
            {
                "message": "If an account exists for that email, a reset code has been sent.",
                "data": None,
            }
        )


@extend_schema(tags=["Auth"], summary="Confirm a password reset with the code")
class PasswordResetConfirmView(GenericAPIView):
    serializer_class = PasswordResetConfirmSerializer
    permission_classes = [AllowAny]
    throttle_classes = []

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.confirm_password_reset(**serializer.validated_data)
        return Response(
            {"message": "Password reset successfully. Please log in.", "data": None}
        )


# ═══════════════════════════════════════════════════════════════════════════
# DEVICES
# ═══════════════════════════════════════════════════════════════════════════
@extend_schema(tags=["Auth"], summary="Register this device for push notifications")
class DeviceRegisterView(GenericAPIView):
    serializer_class = DeviceRegisterSerializer
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.register_device(request.user, **serializer.validated_data)
        return Response({"message": "Device registered", "data": None})


@extend_schema(tags=["Auth"], summary="Permanently delete the signed-in account")
class DeleteAccountView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request):
        services.delete_account(request.user, reason=request.data.get("reason", ""))
        return Response(
            {"message": "Account successfully deleted", "data": {"deleted": True}},
            status=status.HTTP_200_OK,
        )
