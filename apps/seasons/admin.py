from django.contrib import admin

from apps.seasons.models import FarmSeasonAssociation, Season


@admin.register(Season)
class SeasonAdmin(admin.ModelAdmin):
    list_display = ("crop_year", "name", "status", "planting_date", "expected_harvest_date")
    list_filter = ("status", "crop_year")
    search_fields = ("name", "crop_year")


@admin.register(FarmSeasonAssociation)
class FarmSeasonAssociationAdmin(admin.ModelAdmin):
    list_display = ("farm", "season", "farmer_accepted", "farmer_accepted_at")
    list_filter = ("farmer_accepted", "season__crop_year")
    search_fields = ("farm__name", "season__name", "farm__owner__email")
    raw_id_fields = ("farm", "season", "accepted_by")
