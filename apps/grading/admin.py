from django.contrib import admin

from apps.grading.models import GradeRecord


@admin.register(GradeRecord)
class GradeRecordAdmin(admin.ModelAdmin):
    list_display = ("lot", "grade", "weight_kg", "graded_by", "graded_at")
    list_filter = ("grade",)
    search_fields = ("lot__lot_number",)
    raw_id_fields = ("lot", "graded_by")
