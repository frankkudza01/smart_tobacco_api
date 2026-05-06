from django.contrib.auth import get_user_model
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from apps.accounts.serializers import (
    AdminUserCreateSerializer,
    ChangePasswordSerializer,
    RegisterSerializer,
    UserDetailSerializer,
    UserSerializer,
)
from apps.accounts.profile_serializers import (
    FarmerProfileSerializer,
    BuyerProfileSerializer,
)
from apps.accounts.services import register_user
from apps.common.enums import UserRole
from apps.common.permissions import IsSystemAdmin

User = get_user_model()


class RegisterView(generics.CreateAPIView):
    """Public registration endpoint for new users."""
    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        user = register_user(
            email=data["email"],
            password=data["password"],
            first_name=data["first_name"],
            last_name=data["last_name"],
            role=data.get("role", UserRole.SMALLHOLDER_FARMER),
            phone_number=data.get("phone_number", ""),
        )
        return Response(
            UserSerializer(user).data,
            status=status.HTTP_201_CREATED,
        )


class LoginView(TokenObtainPairView):
    """JWT login returning access + refresh tokens."""
    pass


class TokenRefreshAPIView(TokenRefreshView):
    pass


class MeView(generics.RetrieveUpdateAPIView):
    """Get or update the current user's profile."""
    serializer_class = UserDetailSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user


class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ChangePasswordSerializer

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        request.user.set_password(serializer.validated_data["new_password"])
        request.user.save(update_fields=["password"])
        return Response({"detail": "Password updated."}, status=status.HTTP_200_OK)


class FarmerProfileView(generics.RetrieveUpdateAPIView):
    serializer_class = FarmerProfileSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user.farmer_profile


class BuyerProfileView(generics.RetrieveUpdateAPIView):
    serializer_class = BuyerProfileSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user.buyer_profile


# --- Admin user management ---

class UserListView(generics.ListAPIView):
    serializer_class = UserSerializer
    permission_classes = [IsSystemAdmin]
    filterset_fields = ["role", "is_active"]
    search_fields = ["email", "first_name", "last_name"]
    ordering_fields = ["date_joined", "email"]

    def get_queryset(self):
        return User.objects.all()


class UserCreateView(generics.CreateAPIView):
    serializer_class = AdminUserCreateSerializer
    permission_classes = [IsSystemAdmin]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        user = register_user(
            email=data["email"],
            password=data["password"],
            first_name=data["first_name"],
            last_name=data["last_name"],
            role=data.get("role", UserRole.SMALLHOLDER_FARMER),
            phone_number=data.get("phone_number", ""),
        )
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)


class UserDetailView(generics.RetrieveUpdateAPIView):
    serializer_class = UserSerializer
    permission_classes = [IsSystemAdmin]
    queryset = User.objects.all()
    lookup_field = "pk"
