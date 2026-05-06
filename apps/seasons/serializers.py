from django.db import connection
from rest_framework import serializers

from apps.seasons.models import FarmSeasonAssociation, Season


class SeasonSerializer(serializers.ModelSerializer):
    accepted_for_farm = serializers.SerializerMethodField()
    accepted_at_for_farm = serializers.SerializerMethodField()

    class Meta:
        model = Season
        fields = [
            "id", "crop_year", "name", "status",
            "planting_date", "expected_harvest_date", "actual_harvest_date",
            "expected_yield_kg", "actual_yield_kg", "notes",
            "accepted_for_farm", "accepted_at_for_farm",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def update(self, instance, validated_data):
        return super().update(instance, validated_data)

    def get_accepted_for_farm(self, obj):
        farm_id = self.context.get("farm_id")
        if not farm_id:
            return False
        if FarmSeasonAssociation._meta.db_table not in connection.introspection.table_names():
            return False
        return FarmSeasonAssociation.objects.filter(
            farm_id=farm_id,
            season=obj,
            farmer_accepted=True,
        ).exists()

    def get_accepted_at_for_farm(self, obj):
        farm_id = self.context.get("farm_id")
        if not farm_id:
            return None
        if FarmSeasonAssociation._meta.db_table not in connection.introspection.table_names():
            return None
        assoc = FarmSeasonAssociation.objects.filter(
            farm_id=farm_id,
            season=obj,
            farmer_accepted=True,
        ).order_by("-farmer_accepted_at", "-updated_at").first()
        return assoc.farmer_accepted_at if assoc else None
