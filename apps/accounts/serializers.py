from django.contrib.auth import get_user_model
from rest_framework import serializers

from apps.common.enums import UserRole

User = get_user_model()

# Public self-registration must never create privileged accounts.
_PUBLIC_REGISTER_ROLES = frozenset(
    {UserRole.SMALLHOLDER_FARMER, UserRole.BUYER_CONTRACTOR},
)


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    password_confirm = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = [
            "id", "email", "first_name", "last_name",
            "phone_number", "role", "password", "password_confirm",
        ]
        read_only_fields = ["id"]

    def validate(self, attrs):
        if attrs["password"] != attrs.pop("password_confirm"):
            raise serializers.ValidationError({"password_confirm": "Passwords do not match."})
        role = attrs.get("role", UserRole.SMALLHOLDER_FARMER)
        if role not in _PUBLIC_REGISTER_ROLES:
            raise serializers.ValidationError(
                {
                    "role": (
                        "Registration is only available for smallholder farmer "
                        "or buyer accounts."
                    ),
                },
            )
        attrs["role"] = role
        return attrs

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)


class UserSerializer(serializers.ModelSerializer):
    full_name = serializers.ReadOnlyField()
    organization_id = serializers.SerializerMethodField()
    organization_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id", "email", "first_name", "last_name",
            "phone_number", "role", "full_name",
            "is_active", "date_joined", "updated_at",
            "organization_id", "organization_name",
        ]
        read_only_fields = [
            "id", "email", "role", "date_joined", "updated_at",
            "organization_id", "organization_name",
        ]

    def get_organization_id(self, obj):
        from apps.common.org_utils import get_user_primary_organization

        org = get_user_primary_organization(obj)
        return str(org.id) if org else None

    def get_organization_name(self, obj):
        from apps.common.org_utils import get_user_primary_organization

        org = get_user_primary_organization(obj)
        return org.name if org else None


class UserDetailSerializer(UserSerializer):
    farmer_profile = serializers.SerializerMethodField()
    buyer_profile = serializers.SerializerMethodField()

    class Meta(UserSerializer.Meta):
        fields = UserSerializer.Meta.fields + ["farmer_profile", "buyer_profile"]

    def get_farmer_profile(self, obj):
        if obj.role == UserRole.SMALLHOLDER_FARMER and hasattr(obj, "farmer_profile"):
            from apps.accounts.profile_serializers import FarmerProfileSerializer
            return FarmerProfileSerializer(obj.farmer_profile).data
        return None

    def get_buyer_profile(self, obj):
        if obj.role == UserRole.BUYER_CONTRACTOR and hasattr(obj, "buyer_profile"):
            from apps.accounts.profile_serializers import BuyerProfileSerializer
            return BuyerProfileSerializer(obj.buyer_profile).data
        return None


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField()
    new_password = serializers.CharField(min_length=8)

    def validate_old_password(self, value):
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("Current password is incorrect.")
        return value


class AdminUserCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = [
            "id", "email", "first_name", "last_name",
            "phone_number", "role", "password", "is_active",
        ]
        read_only_fields = ["id"]

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)
