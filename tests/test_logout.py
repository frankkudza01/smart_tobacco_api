"""
Test suite for JWT logout / token blacklisting.
"""
import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import User
from apps.common.enums import UserRole


@pytest.mark.django_db
class TestLogout:
    def test_logout_success(self, api_client):
        user = User.objects.create_user(
            email="logouttest@test.com", password="pass12345",
            first_name="Logout", last_name="User",
            role=UserRole.SMALLHOLDER_FARMER,
        )
        refresh = RefreshToken.for_user(user)
        api_client.force_authenticate(user=user)

        url = reverse("auth-logout")
        resp = api_client.post(url, {"refresh": str(refresh)})
        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["detail"] == "Successfully logged out."

    def test_logout_blacklisted_token_cannot_refresh(self, api_client):
        user = User.objects.create_user(
            email="logoutrefresh@test.com", password="pass12345",
            first_name="LR", last_name="User",
            role=UserRole.SMALLHOLDER_FARMER,
        )
        refresh = RefreshToken.for_user(user)
        api_client.force_authenticate(user=user)

        api_client.post(reverse("auth-logout"), {"refresh": str(refresh)})

        api_client.force_authenticate(user=None)
        resp = api_client.post(reverse("auth-refresh"), {"refresh": str(refresh)})
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED

    def test_logout_invalid_token(self, api_client):
        user = User.objects.create_user(
            email="logoutbad@test.com", password="pass12345",
            first_name="Bad", last_name="Token",
            role=UserRole.SMALLHOLDER_FARMER,
        )
        api_client.force_authenticate(user=user)

        url = reverse("auth-logout")
        resp = api_client.post(url, {"refresh": "invalid-token-string"})
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_logout_requires_authentication(self, api_client):
        url = reverse("auth-logout")
        resp = api_client.post(url, {"refresh": "some-token"})
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED

    def test_double_logout_fails_gracefully(self, api_client):
        user = User.objects.create_user(
            email="doublelogout@test.com", password="pass12345",
            first_name="Double", last_name="Logout",
            role=UserRole.SMALLHOLDER_FARMER,
        )
        refresh = RefreshToken.for_user(user)
        api_client.force_authenticate(user=user)

        url = reverse("auth-logout")
        api_client.post(url, {"refresh": str(refresh)})
        resp = api_client.post(url, {"refresh": str(refresh)})
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
