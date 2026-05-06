from rest_framework import serializers

from apps.organizations.models import Organization, OrganizationMembership


class OrganizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = [
            "id", "name", "org_type", "registration_number",
            "address", "is_active", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class OrganizationMembershipSerializer(serializers.ModelSerializer):
    user_email = serializers.CharField(source="user.email", read_only=True)
    user_name = serializers.CharField(source="user.full_name", read_only=True)
    organization_name = serializers.CharField(source="organization.name", read_only=True)

    class Meta:
        model = OrganizationMembership
        fields = [
            "id", "user", "organization", "role",
            "is_primary", "is_active",
            "user_email", "user_name", "organization_name",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]
