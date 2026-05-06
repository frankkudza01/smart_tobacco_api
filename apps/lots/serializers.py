from rest_framework import serializers

from apps.seasons.models import FarmSeasonAssociation
from apps.lots.models import Lot


class LotSerializer(serializers.ModelSerializer):
    farm_name = serializers.CharField(source="farm.name", read_only=True)
    crop_year = serializers.IntegerField(source="season.crop_year", read_only=True)

    class Meta:
        model = Lot
        fields = [
            "id", "season", "farm", "created_by", "lot_number",
            "description", "weight_kg", "bale_count",
            "tobacco_type", "status", "blockchain_anchor_hash",
            "farm_name", "crop_year",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_by", "blockchain_anchor_hash", "created_at", "updated_at"]
        extra_kwargs = {
            "farm": {"required": False, "allow_null": True},
            "lot_number": {"required": False, "allow_blank": True},
        }

    def create(self, validated_data):
        season = validated_data["season"]
        farm = validated_data.get("farm")
        if farm is None:
            assoc = FarmSeasonAssociation.objects.filter(season=season).order_by("created_at").first()
            if assoc is None:
                raise serializers.ValidationError(
                    {"farm": "No farm is associated with this season."}
                )
            farm = assoc.farm
            validated_data["farm"] = farm
        linked = FarmSeasonAssociation.objects.filter(season=season, farm=farm).exists()
        if not linked:
            raise serializers.ValidationError(
                {"farm": "Selected farm is not associated with this season."}
            )
        lot_number = (validated_data.get("lot_number") or "").strip()
        if not lot_number:
            from apps.lots.services.lot_numbering import generate_lot_number_for_farm_season

            validated_data["lot_number"] = generate_lot_number_for_farm_season(farm, season)
        else:
            validated_data["lot_number"] = lot_number
        validated_data["created_by"] = self.context["request"].user
        return super().create(validated_data)
