from django.contrib import admin

from apps.lots.models import Lot


@admin.register(Lot)
class LotAdmin(admin.ModelAdmin):
    list_display = ("lot_number", "season", "status", "weight_kg", "bale_count", "created_at")
    list_filter = ("status", "tobacco_type")
    search_fields = ("lot_number", "farm__name")
    raw_id_fields = ("season", "created_by")
