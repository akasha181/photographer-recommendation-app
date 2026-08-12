"""Auth routes — mounted at /api/v1/auth/"""

from django.urls import path

from apps.accounts import views

app_name = "accounts"

urlpatterns = [
    # ─── Registration & session ──────────────────────────────────────────────
    path("register/", views.RegisterView.as_view(), name="register"),
    path("login/", views.LoginView.as_view(), name="login"),
    path("refresh/", views.RefreshView.as_view(), name="token-refresh"),
    path("logout/", views.LogoutView.as_view(), name="logout"),

    # ─── Current user ────────────────────────────────────────────────────────
    path("me/", views.MeView.as_view(), name="me"),
    path("me/delete/", views.DeleteAccountView.as_view(), name="delete-account"),

    # ─── Verification ────────────────────────────────────────────────────────
    path("verify-email/", views.VerifyEmailView.as_view(), name="verify-email"),
    path("resend-otp/", views.ResendOTPView.as_view(), name="resend-otp"),

    # ─── Password ────────────────────────────────────────────────────────────
    path("change-password/", views.ChangePasswordView.as_view(), name="change-password"),
    path(
        "password-reset/",
        views.PasswordResetRequestView.as_view(),
        name="password-reset-request",
    ),
    path(
        "password-reset/confirm/",
        views.PasswordResetConfirmView.as_view(),
        name="password-reset-confirm",
    ),

    # ─── Devices ─────────────────────────────────────────────────────────────
    path("devices/", views.DeviceRegisterView.as_view(), name="device-register"),
]
