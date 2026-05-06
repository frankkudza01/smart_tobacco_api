from django.contrib import admin

from apps.sales.models import Sale


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = ("lot", "buyer", "sale_type", "total_amount", "currency", "sale_date")
    list_filter = ("sale_type", "currency")
    search_fields = ("lot__lot_number", "buyer__email")
    raw_id_fields = ("lot", "buyer")
