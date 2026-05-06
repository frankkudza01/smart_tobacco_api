from rest_framework import serializers

from apps.accounts.models import FarmerProfile, BuyerProfile, AuditorProfile, AdminProfile


class FarmerProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = FarmerProfile
        fields = [
            "id", "national_id", "district", "ward", "village",
            "bank_name", "bank_account_number", "mobile_money_number",
            "years_of_experience", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class BuyerProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = BuyerProfile
        fields = [
            "id", "company_name", "license_number", "buyer_type",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class AuditorProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditorProfile
        fields = [
            "id", "department", "badge_number", "jurisdiction",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class AdminProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = AdminProfile
        fields = ["id", "department", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]
