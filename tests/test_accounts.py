import pytest
from django.urls import reverse
from rest_framework import status

from apps.accounts.models import User, FarmerProfile
from apps.common.enums import UserRole


@pytest.mark.django_db
class TestRegistration:
    def test_register_farmer(self, api_client):
        url = reverse("auth-register")
        data = {
            "email": "newfarmer@test.com",
            "first_name": "Test",
            "last_name": "Farmer",
            "password": "strongpass123",
            "password_confirm": "strongpass123",
            "role": UserRole.SMALLHOLDER_FARMER,
        }
        response = api_client.post(url, data)
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["email"] == "newfarmer@test.com"
        assert response.data["role"] == UserRole.SMALLHOLDER_FARMER

        user = User.objects.get(email="newfarmer@test.com")
        assert user.check_password("strongpass123")
        assert hasattr(user, "farmer_profile")

    def test_register_password_mismatch(self, api_client):
        url = reverse("auth-register")
        data = {
            "email": "bad@test.com",
            "first_name": "Bad",
            "last_name": "User",
            "password": "password123",
            "password_confirm": "different123",
            "role": UserRole.SMALLHOLDER_FARMER,
        }
        response = api_client.post(url, data)
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_register_duplicate_email(self, api_client, farmer_user):
        url = reverse("auth-register")
        data = {
            "email": farmer_user.email,
            "first_name": "Dup",
            "last_name": "User",
            "password": "password123",
            "password_confirm": "password123",
        }
        response = api_client.post(url, data)
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_register_system_admin_role_rejected(self, api_client):
        url = reverse("auth-register")
        data = {
            "email": "hacker_admin@test.com",
            "first_name": "Bad",
            "last_name": "Actor",
            "password": "password123",
            "password_confirm": "password123",
            "role": UserRole.SYSTEM_ADMIN,
        }
        response = api_client.post(url, data, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "role" in response.data

    def test_register_auditor_role_rejected(self, api_client):
        url = reverse("auth-register")
        data = {
            "email": "hacker_auditor@test.com",
            "first_name": "Bad",
            "last_name": "Actor",
            "password": "password123",
            "password_confirm": "password123",
            "role": UserRole.REGULATOR_AUDITOR,
        }
        response = api_client.post(url, data, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "role" in response.data


@pytest.mark.django_db
class TestLogin:
    def test_login_success(self, api_client):
        user = User.objects.create_user(
            email="login@test.com", password="testpass123",
            first_name="Login", last_name="User",
        )
        url = reverse("auth-login")
        response = api_client.post(url, {"email": "login@test.com", "password": "testpass123"})
        assert response.status_code == status.HTTP_200_OK
        assert "access" in response.data
        assert "refresh" in response.data

    def test_login_wrong_password(self, api_client):
        User.objects.create_user(email="login2@test.com", password="testpass123", first_name="X", last_name="Y")
        url = reverse("auth-login")
        response = api_client.post(url, {"email": "login2@test.com", "password": "wrong"})
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
class TestMe:
    def test_me_authenticated(self, authenticated_farmer_client, farmer_user):
        url = reverse("auth-me")
        response = authenticated_farmer_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["email"] == farmer_user.email

    def test_me_unauthenticated(self, api_client):
        url = reverse("auth-me")
        response = api_client.get(url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
class TestChangePassword:
    def test_change_password(self, authenticated_farmer_client, farmer_user):
        url = reverse("auth-change-password")
        response = authenticated_farmer_client.post(url, {
            "old_password": "testpass123",
            "new_password": "newstrongpass456",
        })
        assert response.status_code == status.HTTP_200_OK
        farmer_user.refresh_from_db()
        assert farmer_user.check_password("newstrongpass456")


@pytest.mark.django_db
class TestUserAdmin:
    def test_user_list_admin_only(self, authenticated_farmer_client):
        url = reverse("user-list")
        response = authenticated_farmer_client.get(url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_user_list_as_admin(self, authenticated_admin_client):
        url = reverse("user-list")
        response = authenticated_admin_client.get(url)
        assert response.status_code == status.HTTP_200_OK
