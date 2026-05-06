"""
Full test suite for OTP request/verify/resend flow, rate limiting, and brute-force protection.
"""
import pytest
from unittest.mock import patch, MagicMock
from django.core.cache import cache
from django.urls import reverse
from rest_framework import status

from apps.accounts.models import User, OTPChallengeLog
from apps.accounts import otp_service
from apps.common.enums import UserRole


@pytest.fixture
def farmer_with_phone(db):
    user = User.objects.create_user(
        email="otpfarmer@test.com",
        password="testpass123",
        first_name="OTP",
        last_name="Farmer",
        role=UserRole.SMALLHOLDER_FARMER,
        phone_number="+263771234567",
    )
    return user


@pytest.fixture
def buyer_with_phone(db):
    return User.objects.create_user(
        email="otpbuyer@test.com",
        password="testpass123",
        first_name="OTP",
        last_name="Buyer",
        role=UserRole.BUYER_CONTRACTOR,
        phone_number="+263772345678",
    )


@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.mark.django_db
class TestRequestOTP:
    @patch("apps.whatsapp.tasks.send_otp_via_whatsapp_task.delay")
    def test_request_otp_success(self, mock_send, api_client, farmer_with_phone):
        url = reverse("auth-request-otp")
        resp = api_client.post(url, {"phone_number": "+263771234567"})
        assert resp.status_code == status.HTTP_200_OK
        assert "expires_in" in resp.data
        mock_send.assert_called_once()
        assert OTPChallengeLog.objects.filter(phone_number="+263771234567").exists()

    def test_request_otp_invalid_phone(self, api_client):
        url = reverse("auth-request-otp")
        resp = api_client.post(url, {"phone_number": "not-a-phone"})
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_request_otp_no_account(self, api_client):
        url = reverse("auth-request-otp")
        resp = api_client.post(url, {"phone_number": "+263779999999"})
        assert resp.status_code == status.HTTP_404_NOT_FOUND

    @patch("apps.whatsapp.tasks.send_otp_via_whatsapp_task.delay")
    def test_request_otp_cooldown(self, mock_send, api_client, farmer_with_phone):
        url = reverse("auth-request-otp")
        api_client.post(url, {"phone_number": "+263771234567"})
        resp2 = api_client.post(url, {"phone_number": "+263771234567"})
        assert resp2.status_code == status.HTTP_429_TOO_MANY_REQUESTS

    def test_request_otp_auditor_ineligible(self, api_client, db):
        User.objects.create_user(
            email="auditor@test.com", password="pass",
            first_name="A", last_name="B",
            role=UserRole.REGULATOR_AUDITOR,
            phone_number="+263773456789",
        )
        url = reverse("auth-request-otp")
        resp = api_client.post(url, {"phone_number": "+263773456789"})
        assert resp.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
class TestVerifyOTP:
    @patch("apps.whatsapp.tasks.send_otp_via_whatsapp_task.delay")
    def test_verify_otp_success(self, mock_send, api_client, farmer_with_phone):
        phone = "+263771234567"
        code, _ = otp_service.generate_otp(phone)
        OTPChallengeLog.objects.create(
            phone_number=phone, user=farmer_with_phone, purpose="LOGIN",
            status="PENDING", delivery_channel="whatsapp",
            expires_at="2099-01-01T00:00:00Z",
        )

        url = reverse("auth-verify-otp")
        resp = api_client.post(url, {"phone_number": phone, "code": code})
        assert resp.status_code == status.HTTP_200_OK
        assert "access" in resp.data
        assert "refresh" in resp.data
        assert resp.data["user_id"] == str(farmer_with_phone.id)
        assert resp.data["role"] == UserRole.SMALLHOLDER_FARMER

    def test_verify_otp_wrong_code(self, api_client, farmer_with_phone):
        phone = "+263771234567"
        otp_service.generate_otp(phone)
        OTPChallengeLog.objects.create(
            phone_number=phone, user=farmer_with_phone, purpose="LOGIN",
            status="PENDING", delivery_channel="whatsapp",
            expires_at="2099-01-01T00:00:00Z",
        )

        url = reverse("auth-verify-otp")
        resp = api_client.post(url, {"phone_number": phone, "code": "000000"})
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert "Invalid OTP" in resp.data["detail"]

    def test_verify_otp_expired(self, api_client, farmer_with_phone):
        phone = "+263771234567"
        url = reverse("auth-verify-otp")
        resp = api_client.post(url, {"phone_number": phone, "code": "123456"})
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert "expired" in resp.data["detail"].lower()

    def test_verify_otp_max_attempts(self, api_client, farmer_with_phone):
        phone = "+263771234567"
        otp_service.generate_otp(phone)
        OTPChallengeLog.objects.create(
            phone_number=phone, user=farmer_with_phone, purpose="LOGIN",
            status="PENDING", delivery_channel="whatsapp",
            expires_at="2099-01-01T00:00:00Z",
        )

        url = reverse("auth-verify-otp")
        for i in range(5):
            api_client.post(url, {"phone_number": phone, "code": "000000"})

        resp = api_client.post(url, {"phone_number": phone, "code": "000000"})
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert "expired" in resp.data["detail"].lower() or "Maximum" in resp.data["detail"]


@pytest.mark.django_db
class TestResendOTP:
    @patch("apps.whatsapp.tasks.send_otp_via_whatsapp_task.delay")
    def test_resend_after_cooldown(self, mock_send, api_client, farmer_with_phone):
        phone = "+263771234567"
        otp_service.generate_otp(phone)
        cache.delete(f"otp:{phone}:cooldown")

        url = reverse("auth-resend-otp")
        resp = api_client.post(url, {"phone_number": phone})
        assert resp.status_code == status.HTTP_200_OK
        assert mock_send.called

    @patch("apps.whatsapp.tasks.send_otp_via_whatsapp_task.delay")
    def test_resend_during_cooldown(self, mock_send, api_client, farmer_with_phone):
        phone = "+263771234567"
        otp_service.generate_otp(phone)

        url = reverse("auth-resend-otp")
        resp = api_client.post(url, {"phone_number": phone})
        assert resp.status_code == status.HTTP_429_TOO_MANY_REQUESTS
