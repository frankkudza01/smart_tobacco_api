from django.conf import settings
from django.db import models

from apps.common.models import BaseModel
from apps.lots.models import Lot


class GradeRecord(BaseModel):
    lot = models.ForeignKey(Lot, on_delete=models.CASCADE, related_name="grade_records")
    graded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="grade_records",
    )
    grade = models.CharField(max_length=20, db_index=True)
    weight_kg = models.DecimalField(max_digits=10, decimal_places=2)
    moisture_percent = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    quality_score = models.PositiveIntegerField(null=True, blank=True)
    notes = models.TextField(blank=True, default="")
    graded_at = models.DateTimeField()

    class Meta:
        db_table = "grading_grade_record"
        ordering = ["-graded_at"]

    def __str__(self):
        return f"Grade {self.grade} for Lot {self.lot.lot_number}"
