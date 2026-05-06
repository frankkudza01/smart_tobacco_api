from rest_framework import serializers

from apps.grading.models import GradeRecord


class GradeRecordSerializer(serializers.ModelSerializer):
    graded_by_name = serializers.CharField(source="graded_by.full_name", read_only=True)
    lot_number = serializers.CharField(source="lot.lot_number", read_only=True)

    class Meta:
        model = GradeRecord
        fields = [
            "id", "lot", "graded_by", "grade",
            "weight_kg", "moisture_percent", "quality_score",
            "notes", "graded_at",
            "graded_by_name", "lot_number",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "graded_by", "created_at", "updated_at"]

    def create(self, validated_data):
        validated_data["graded_by"] = self.context["request"].user
        return super().create(validated_data)
