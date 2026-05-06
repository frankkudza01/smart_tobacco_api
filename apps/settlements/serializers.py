from decimal import Decimal

from rest_framework import serializers

from apps.common.enums import SettlementStatus
from apps.settlements.models import Settlement


class SettlementSerializer(serializers.ModelSerializer):
    farmer_name = serializers.CharField(source="farmer.full_name", read_only=True)
    lot_number = serializers.CharField(source="sale.lot.lot_number", read_only=True)
    lot = serializers.UUIDField(source="sale.lot_id", read_only=True)

    class Meta:
        model = Settlement
        fields = [
            "id", "sale", "farmer", "created_by",
            "amount_due", "amount_paid", "currency", "status",
            "payment_reference", "payment_method",
            "payment_date", "due_date", "notes",
            "farmer_name", "lot_number", "lot",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_by", "created_at", "updated_at"]

    def validate(self, attrs):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return attrs

        sale = attrs.get("sale")
        farmer = attrs.get("farmer")
        instance = getattr(self, "instance", None)
        if instance is not None:
            sale = sale or instance.sale
            farmer = farmer or instance.farmer

        if sale is None:
            raise serializers.ValidationError({"sale": "Sale is required."})

        if sale.buyer_id != user.id:
            raise serializers.ValidationError(
                {"sale": "You can only create settlements for your own sales."},
            )

        lot_owner_id = sale.lot.farm.owner_id
        if farmer is None:
            raise serializers.ValidationError({"farmer": "Farmer is required."})
        if farmer.id != lot_owner_id:
            raise serializers.ValidationError(
                {
                    "farmer": (
                        "Farmer must be the owner of the farm linked to this sale's lot."
                    ),
                },
            )

        amount_due = attrs.get("amount_due", getattr(instance, "amount_due", None) if instance else None)
        amount_paid = attrs.get("amount_paid", getattr(instance, "amount_paid", None) if instance else None)
        currency = attrs.get("currency", getattr(instance, "currency", None) if instance else None)
        st = attrs.get("status", getattr(instance, "status", None) if instance else None)

        if amount_due is not None and amount_due <= 0:
            raise serializers.ValidationError(
                {"amount_due": "Amount due must be greater than zero."},
            )
        if amount_paid is not None and amount_paid < 0:
            raise serializers.ValidationError(
                {"amount_paid": "Amount paid cannot be negative."},
            )
        if (
            amount_due is not None
            and amount_paid is not None
            and amount_paid > amount_due + Decimal("0.01")
        ):
            raise serializers.ValidationError(
                {
                    "amount_paid": (
                        "Amount paid cannot exceed amount due for a single settlement record."
                    ),
                },
            )

        if currency is not None and str(currency).upper() != str(sale.currency).upper():
            raise serializers.ValidationError(
                {
                    "currency": (
                        f"Currency must match the sale ({sale.currency})."
                    ),
                },
            )

        if st == SettlementStatus.PAID and amount_due is not None and amount_paid is not None:
            if amount_paid + Decimal("0.01") < amount_due:
                raise serializers.ValidationError(
                    {
                        "status": (
                            "Status PAID requires amount paid to cover amount due."
                        ),
                    },
                )

        return attrs

    def create(self, validated_data):
        validated_data["created_by"] = self.context["request"].user
        return super().create(validated_data)
