from rest_framework import generics
from rest_framework.permissions import IsAuthenticated

from apps.common.enums import UserRole
from apps.common.permissions import IsBuyerContractor
from apps.settlements.models import Settlement
from apps.settlements.serializers import SettlementSerializer


class SettlementListCreateView(generics.ListCreateAPIView):
    serializer_class = SettlementSerializer
    filterset_fields = ["sale", "status", "currency"]
    ordering_fields = ["created_at", "due_date", "amount_due"]

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsBuyerContractor()]
        return [IsAuthenticated()]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Settlement.objects.none()
        user = self.request.user
        qs = Settlement.objects.select_related("sale", "sale__lot", "farmer", "created_by")
        if user.role == UserRole.SMALLHOLDER_FARMER:
            return qs.filter(farmer=user)
        if user.role == UserRole.BUYER_CONTRACTOR:
            return qs.filter(created_by=user)
        return qs


class SettlementDetailView(generics.RetrieveUpdateAPIView):
    serializer_class = SettlementSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = "pk"

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Settlement.objects.none()
        user = self.request.user
        qs = Settlement.objects.select_related("sale", "sale__lot", "farmer")
        if user.role == UserRole.SMALLHOLDER_FARMER:
            return qs.filter(farmer=user)
        if user.role == UserRole.BUYER_CONTRACTOR:
            return qs.filter(created_by=user)
        return qs
