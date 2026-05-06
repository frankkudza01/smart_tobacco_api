import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import OTPChallengeLog
from apps.accounts.otp_serializers import (
    LogoutSerializer,
    RequestOTPSerializer,
    ResendOTPSerializer,
    VerifyOTPSerializer,
)
from apps.accounts import otp_service
from apps.audit.services import log_audit
from apps.common.enums import UserRole
from apps.common.utils import normalize_phone_number

User = get_user_model()
logger = logging.getLogger(__name__)

OTP_ELIGIBLE_ROLES = {UserRole.SMALLHOLDER_FARMER, UserRole.BUYER_CONTRACTOR}


class RequestOTPView(APIView):
    """
    POST /api/v1/auth/request-otp/
    Accepts a phone number, validates the user exists and is eligible,
    generates OTP, stores in Redis, enqueues WhatsApp delivery via Celery.
    """

    permission_classes = [AllowAny]
    authentication_classes = []
    serializer_class = RequestOTPSerializer

    def post(self, request):
        serializer = RequestOTPSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        raw_phone = serializer.validated_data["phone_number"]
        phone = normalize_phone_number(raw_phone)
        if not phone:
            return Response(
                {"detail": "Invalid phone number format. Use international format e.g. +263771234567."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = User.objects.filter(
            phone_number=phone, is_active=True, role__in=OTP_ELIGIBLE_ROLES,
        ).first()

        if not user:
            return Response(
                {"detail": "No active Farmer or Buyer account found for this phone number."},
                status=status.HTTP_404_NOT_FOUND,
            )

        code, error = otp_service.generate_otp(phone)
        if error:
            return Response({"detail": error}, status=status.HTTP_429_TOO_MANY_REQUESTS)

        OTPChallengeLog.objects.create(
            phone_number=phone,
            user=user,
            purpose="LOGIN",
            status="PENDING",
            delivery_channel="whatsapp",
            expires_at=timezone.now() + timezone.timedelta(seconds=settings.OTP_TTL_SECONDS),
            ip_address=_get_ip(request),
        )

        from apps.whatsapp.tasks import send_otp_via_whatsapp_task
        send_otp_via_whatsapp_task.delay(
            phone=phone,
            otp_code=code,
            user_id=str(user.id),
        )

        log_audit(
            actor=user, action="otp_requested", resource_type="auth",
            resource_id=str(user.id), description=f"OTP requested for {phone}",
            request=request,
        )

        return Response({
            "detail": "OTP sent to your WhatsApp. Check your messages.",
            "expires_in": settings.OTP_TTL_SECONDS,
        }, status=status.HTTP_200_OK)


class VerifyOTPView(APIView):
    """
    POST /api/v1/auth/verify-otp/
    Verifies OTP and issues JWT tokens on success.
    """

    permission_classes = [AllowAny]
    authentication_classes = []
    serializer_class = VerifyOTPSerializer

    def post(self, request):
        serializer = VerifyOTPSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        raw_phone = serializer.validated_data["phone_number"]
        code = serializer.validated_data["code"]

        phone = normalize_phone_number(raw_phone)
        if not phone:
            return Response(
                {"detail": "Invalid phone number format."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        success, error_msg = otp_service.verify_otp(phone, code)

        challenge = OTPChallengeLog.objects.filter(
            phone_number=phone, status="PENDING",
        ).order_by("-created_at").first()

        if not success:
            if challenge:
                challenge.attempts += 1
                if "Maximum" in error_msg:
                    challenge.status = "MAX_ATTEMPTS"
                challenge.save(update_fields=["attempts", "status", "updated_at"])

            return Response({"detail": error_msg}, status=status.HTTP_400_BAD_REQUEST)

        user = User.objects.filter(
            phone_number=phone, is_active=True, role__in=OTP_ELIGIBLE_ROLES,
        ).first()

        if not user:
            return Response(
                {"detail": "Account not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if challenge:
            challenge.status = "VERIFIED"
            challenge.verified_at = timezone.now()
            challenge.save(update_fields=["status", "verified_at", "updated_at"])

        refresh = RefreshToken.for_user(user)

        log_audit(
            actor=user, action="otp_verified", resource_type="auth",
            resource_id=str(user.id), description=f"OTP login success for {phone}",
            request=request,
        )

        return Response({
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "user_id": str(user.id),
            "role": user.role,
        }, status=status.HTTP_200_OK)


class ResendOTPView(APIView):
    """
    POST /api/v1/auth/resend-otp/
    Resend OTP if cooldown has elapsed.
    """

    permission_classes = [AllowAny]
    authentication_classes = []
    serializer_class = ResendOTPSerializer

    def post(self, request):
        serializer = ResendOTPSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        raw_phone = serializer.validated_data["phone_number"]
        phone = normalize_phone_number(raw_phone)
        if not phone:
            return Response(
                {"detail": "Invalid phone number format."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = User.objects.filter(
            phone_number=phone, is_active=True, role__in=OTP_ELIGIBLE_ROLES,
        ).first()
        if not user:
            return Response(
                {"detail": "No active account found for this phone number."},
                status=status.HTTP_404_NOT_FOUND,
            )

        code, error = otp_service.generate_otp(phone)
        if error:
            return Response({"detail": error}, status=status.HTTP_429_TOO_MANY_REQUESTS)

        OTPChallengeLog.objects.create(
            phone_number=phone,
            user=user,
            purpose="LOGIN",
            status="PENDING",
            delivery_channel="whatsapp",
            expires_at=timezone.now() + timezone.timedelta(seconds=settings.OTP_TTL_SECONDS),
            ip_address=_get_ip(request),
        )

        from apps.whatsapp.tasks import send_otp_via_whatsapp_task
        send_otp_via_whatsapp_task.delay(
            phone=phone,
            otp_code=code,
            user_id=str(user.id),
        )

        log_audit(
            actor=user, action="otp_resent", resource_type="auth",
            resource_id=str(user.id), description=f"OTP resent to {phone}",
            request=request,
        )

        return Response({
            "detail": "OTP resent to your WhatsApp.",
            "expires_in": settings.OTP_TTL_SECONDS,
        }, status=status.HTTP_200_OK)


class LogoutView(APIView):
    """
    POST /api/v1/auth/logout/
    Blacklists the refresh token so it can no longer be used.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = LogoutSerializer

    def post(self, request):
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            token = RefreshToken(serializer.validated_data["refresh"])
            token.blacklist()
        except Exception:
            return Response(
                {"detail": "Invalid or already blacklisted token."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        log_audit(
            actor=request.user, action="logout", resource_type="auth",
            resource_id=str(request.user.id), description="User logged out",
            request=request,
        )

        return Response({"detail": "Successfully logged out."}, status=status.HTTP_200_OK)


def _get_ip(request):
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")
