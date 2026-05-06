from django.contrib import admin

from apps.farms.models import Farm


@admin.register(Farm)
class FarmAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "owner",
        "district",
        "province",
        "size_hectares",
        "gis_verification_status",
        "is_active",
    )
    list_filter = ("is_active", "province", "district", "gis_verification_status")
    search_fields = ("name", "owner__email", "district")
    raw_id_fields = ("owner", "organization")
