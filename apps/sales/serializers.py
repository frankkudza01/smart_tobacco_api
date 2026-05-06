from datetime import timedelta
from decimal import Decimal

from django.utils import timezone
from rest_framework import serializers

from apps.common.enums import LotStatus
from apps.sales.models import Sale

_LINE_TOTAL_TOLERANCE = Decimal("0.05")


class SaleSerializer(serializers.ModelSerializer):
    buyer_name = serializers.CharField(source="buyer.full_name", read_only=True)
    lot_number = serializers.CharField(source="lot.lot_number", read_only=True)
    lot_data = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Sale
        fields = [
            "id", "lot", "buyer", "sale_type",
            "price_per_kg", "total_weight_kg", "total_amount",
            "currency", "sale_date", "status", "annual_price_year",
            "grading_trail", "ai_pricing_note",
            "auction_floor_reference", "contract_reference",
            "accepted_at", "declined_at", "bought_at",
            "notes", "buyer_name", "lot_number",
            "lot_data",
            "created_at", "updated_at",
        ]
        read_only_fields = [
            "id",
            "buyer",
            "status",
            "annual_price_year",
            "grading_trail",
            "ai_pricing_note",
            "accepted_at",
            "declined_at",
            "bought_at",
            "created_at",
            "updated_at",
        ]

    def _merged_decimal(self, attrs, field, instance):
        if field in attrs and attrs[field] is not None:
            return attrs[field]
        if instance is not None:
            return getattr(instance, field)
        return None

    def validate(self, attrs):
        instance = getattr(self, "instance", None)
        lot = attrs.get("lot") or (instance.lot if instance else None)

        currency = attrs.get("currency") or (getattr(instance, "currency", None) if instance else None)
        if currency is not None:
            c = str(currency).strip().upper()
            if len(c) != 3 or not c.isalpha():
                raise serializers.ValidationError(
                    {"currency": "Currency must be a 3-letter ISO code (e.g. USD)."},
                )
            attrs["currency"] = c

        total_amount = self._merged_decimal(attrs, "total_amount", instance)
        price_per_kg = self._merged_decimal(attrs, "price_per_kg", instance)
        total_weight_kg = self._merged_decimal(attrs, "total_weight_kg", instance)

        if total_amount is not None and total_amount <= 0:
            raise serializers.ValidationError(
                {"total_amount": "Total amount must be greater than zero."},
            )
        if price_per_kg is not None and price_per_kg <= 0:
            raise serializers.ValidationError(
                {"price_per_kg": "Price per kg must be greater than zero."},
            )
        if total_weight_kg is not None and total_weight_kg <= 0:
            raise serializers.ValidationError(
                {"total_weight_kg": "Total weight must be greater than zero."},
            )

        sale_date = attrs.get("sale_date") or (getattr(instance, "sale_date", None) if instance else None)
        if sale_date is not None:
            now = timezone.now()
            if timezone.is_naive(sale_date):
                sale_date = timezone.make_aware(sale_date, timezone.get_current_timezone())
            if sale_date > now + timedelta(days=1):
                raise serializers.ValidationError(
                    {"sale_date": "Sale date cannot be more than one day in the future."},
                )
            if sale_date.year < 2000:
                raise serializers.ValidationError(
                    {"sale_date": "Sale date is not valid."},
                )

        # Graded lots: totals are recomputed server-side from grading; do not require line match.
        if (
            lot is not None
            and getattr(lot, "status", None) == LotStatus.GRADED
            and instance is None
        ):
            return attrs

        if (
            total_amount is not None
            and price_per_kg is not None
            and total_weight_kg is not None
        ):
            expected = (price_per_kg * total_weight_kg).quantize(Decimal("0.01"))
            total_q = total_amount.quantize(Decimal("0.01"))
            if abs(total_q - expected) > _LINE_TOTAL_TOLERANCE:
                raise serializers.ValidationError(
                    {
                        "total_amount": (
                            "Total amount must match price per kg × total weight "
                            f"(expected {expected}, tolerance ±{_LINE_TOTAL_TOLERANCE})."
                        ),
                    },
                )

        return attrs

    def create(self, validated_data):
        validated_data["buyer"] = self.context["request"].user
        return super().create(validated_data)

    def get_lot_data(self, obj):
        lot = obj.lot
        return {
            "id": str(lot.id),
            "lot_number": lot.lot_number,
            "farm_id": str(lot.farm_id),
            "season_id": str(lot.season_id),
            "status": lot.status,
            "bale_count": lot.bale_count,
            "weight_kg": float(lot.weight_kg) if lot.weight_kg is not None else None,
            "tobacco_type": lot.tobacco_type,
            "description": lot.description,
        }
