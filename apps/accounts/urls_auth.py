from django.urls import path

from apps.accounts.views import (
    ChangePasswordView,
    LoginView,
    MeView,
    RegisterView,
    TokenRefreshAPIView,
    FarmerProfileView,
    BuyerProfileView,
)
from apps.accounts.otp_views import (
    LogoutView,
    RequestOTPView,
    ResendOTPView,
    VerifyOTPView,
)

urlpatterns = [
    path("register/", RegisterView.as_view(), name="auth-register"),
    path("login/", LoginView.as_view(), name="auth-login"),
    path("refresh/", TokenRefreshAPIView.as_view(), name="auth-refresh"),
    path("me/", MeView.as_view(), name="auth-me"),
    path("change-password/", ChangePasswordView.as_view(), name="auth-change-password"),
    path("profile/farmer/", FarmerProfileView.as_view(), name="auth-farmer-profile"),
    path("profile/buyer/", BuyerProfileView.as_view(), name="auth-buyer-profile"),
    # OTP endpoints
    path("request-otp/", RequestOTPView.as_view(), name="auth-request-otp"),
    path("verify-otp/", VerifyOTPView.as_view(), name="auth-verify-otp"),
    path("resend-otp/", ResendOTPView.as_view(), name="auth-resend-otp"),
    # Logout
    path("logout/", LogoutView.as_view(), name="auth-logout"),
]
