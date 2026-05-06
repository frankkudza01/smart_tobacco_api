import pytest
from django.urls import reverse
from rest_framework import status

from apps.farms.models import Farm


@pytest.mark.django_db
class TestFarms:
    def test_create_farm_as_farmer(self, authenticated_farmer_client, farmer_user):
        url = reverse("farm-list")
        data = {
            "name": "New Test Farm",
            "district": "Bindura",
            "province": "Mashonaland Central",
            "size_hectares": "15.5",
        }
        response = authenticated_farmer_client.post(url, data)
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["name"] == "New Test Farm"
        assert Farm.objects.filter(owner=farmer_user).count() == 1

    def test_create_farm_as_buyer_forbidden(self, authenticated_buyer_client):
        url = reverse("farm-list")
        data = {"name": "Buyer Farm", "district": "Test"}
        response = authenticated_buyer_client.post(url, data)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_list_farms_scoped_to_farmer(self, authenticated_farmer_client, farm, farmer_user):
        url = reverse("farm-list")
        response = authenticated_farmer_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1
        assert response.data["results"][0]["id"] == str(farm.id)

    def test_farm_detail(self, authenticated_farmer_client, farm):
        url = reverse("farm-detail", kwargs={"pk": farm.id})
        response = authenticated_farmer_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["name"] == farm.name
