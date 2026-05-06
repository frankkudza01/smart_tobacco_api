from django.db import transaction
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.enums import LotStatus, UserRole
from apps.common.permissions import IsBuyerContractor
from apps.grading.models import GradeRecord
from apps.lots.models import Lot
from apps.sales.models import Sale, SaleStatus
from apps.sales.serializers import SaleSerializer
from apps.sales.services import create_or_refresh_sale_from_grading


class SaleListCreateView(generics.ListCreateAPIView):
    serializer_class = SaleSerializer
    filterset_fields = ["lot", "sale_type", "currency"]
    ordering_fields = ["sale_date", "total_amount"]

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsBuyerContractor()]
        return [IsAuthenticated()]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Sale.objects.none()
        user = self.request.user
        qs = Sale.objects.select_related("lot", "buyer")
        if user.role == UserRole.SMALLHOLDER_FARMER:
            return qs.filter(lot__farm__owner=user)
        if user.role == UserRole.BUYER_CONTRACTOR:
            self._ensure_sales_from_graded_lots(user)
            return qs.filter(buyer=user)
        return qs

    def _ensure_sales_from_graded_lots(self, user):
        org_ids = user.memberships.values_list("organization_id", flat=True)
        candidates = Lot.objects.filter(
            farm__organization_id__in=org_ids,
            status__in=[LotStatus.GRADED, LotStatus.LISTED_FOR_SALE],
        ).order_by("-updated_at")[:50]
        for lot in candidates:
            if not GradeRecord.objects.filter(lot=lot, graded_by=user).exists():
                continue
            has_sale = Sale.objects.filter(
                lot=lot,
                buyer=user,
                status__in=[SaleStatus.PENDING, SaleStatus.ACCEPTED, SaleStatus.BOUGHT],
            ).exists()
            if has_sale:
                continue
            create_or_refresh_sale_from_grading(lot=lot, buyer=user)

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        lot = serializer.validated_data["lot"]
        if lot.status in {LotStatus.SOLD, LotStatus.SETTLED}:
            return Response({"detail": "Lot is already closed for bidding."}, status=status.HTTP_400_BAD_REQUEST)
        if Sale.objects.filter(
            lot=lot,
            status=SaleStatus.BOUGHT,
        ).exclude(buyer=request.user).exists():
            return Response(
                {"detail": "Lot is already locked by another buyer."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if lot.status == LotStatus.GRADED:
            sale = create_or_refresh_sale_from_grading(lot=lot, buyer=request.user)
        else:
            sale = serializer.save()
        lot = sale.lot
        if lot.status == LotStatus.GRADED:
            lot.status = LotStatus.LISTED_FOR_SALE
            lot.save(update_fields=["status", "updated_at"])
        return Response(SaleSerializer(sale).data, status=status.HTTP_201_CREATED)


class SaleDetailView(generics.RetrieveAPIView):
    serializer_class = SaleSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = "pk"
    queryset = Sale.objects.select_related("lot", "buyer")

    def get_object(self):
        obj = super().get_object()
        user = self.request.user
        if user.role == UserRole.BUYER_CONTRACTOR and obj.buyer_id != user.id:
            raise PermissionDenied("You can only view your own sales.")
        if user.role == UserRole.SMALLHOLDER_FARMER and obj.lot.farm.owner_id != user.id:
            raise PermissionDenied("You can only view sales for your own lots.")
        return obj


class SaleStatusActionView(APIView):
    permission_classes = [IsBuyerContractor]

    @transaction.atomic
    def post(self, request, pk, action):
        try:
            sale = Sale.objects.select_related("lot", "buyer").get(pk=pk, buyer=request.user)
        except Sale.DoesNotExist:
            return Response({"detail": "Sale not found."}, status=status.HTTP_404_NOT_FOUND)

        if action == "accept":
            if sale.status == SaleStatus.BOUGHT:
                return Response({"detail": "Bought sale cannot be accepted again."}, status=status.HTTP_400_BAD_REQUEST)
            sale.status = SaleStatus.ACCEPTED
            sale.accepted_at = timezone.now()
            sale.declined_at = None
            sale.save(update_fields=["status", "accepted_at", "declined_at", "updated_at"])
            return Response(SaleSerializer(sale).data, status=status.HTTP_200_OK)

        if action == "decline":
            if sale.status == SaleStatus.BOUGHT:
                return Response({"detail": "Bought sale cannot be declined."}, status=status.HTTP_400_BAD_REQUEST)
            sale.status = SaleStatus.DECLINED
            sale.declined_at = timezone.now()
            sale.save(update_fields=["status", "declined_at", "updated_at"])
            return Response(SaleSerializer(sale).data, status=status.HTTP_200_OK)

        if action == "buy":
            if sale.status != SaleStatus.ACCEPTED:
                return Response({"detail": "Only accepted sales can be bought."}, status=status.HTTP_400_BAD_REQUEST)
            if Sale.objects.filter(
                lot=sale.lot,
                status=SaleStatus.BOUGHT,
            ).exclude(pk=sale.pk).exists():
                return Response({"detail": "Lot is already locked by another buyer."}, status=status.HTTP_400_BAD_REQUEST)
            sale.status = SaleStatus.BOUGHT
            sale.bought_at = timezone.now()
            sale.save(update_fields=["status", "bought_at", "updated_at"])
            sale.lot.status = LotStatus.SOLD
            sale.lot.save(update_fields=["status", "updated_at"])
            Sale.objects.filter(
                lot=sale.lot,
                status__in=[SaleStatus.PENDING, SaleStatus.ACCEPTED],
            ).exclude(pk=sale.pk).update(status=SaleStatus.DECLINED, declined_at=timezone.now())
            return Response(SaleSerializer(sale).data, status=status.HTTP_200_OK)

        return Response({"detail": "Unsupported action."}, status=status.HTTP_400_BAD_REQUEST)
