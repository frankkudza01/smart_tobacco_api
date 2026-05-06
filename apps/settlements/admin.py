from django.contrib import admin

from apps.settlements.models import Settlement


@admin.register(Settlement)
class SettlementAdmin(admin.ModelAdmin):
    list_display = ("sale", "farmer", "amount_due", "amount_paid", "status", "due_date")
    list_filter = ("status", "currency")
    search_fields = ("sale__lot__lot_number", "farmer__email")
    raw_id_fields = ("sale", "farmer", "created_by")
