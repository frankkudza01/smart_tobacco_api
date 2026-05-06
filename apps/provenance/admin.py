from django.contrib import admin

from apps.provenance.models import ProvenanceQueryLog


@admin.register(ProvenanceQueryLog)
class ProvenanceQueryLogAdmin(admin.ModelAdmin):
    list_display = ("queried_by", "query_type", "reference_type", "reference_id", "created_at")
    list_filter = ("query_type", "reference_type")
    search_fields = ("queried_by__email",)
    raw_id_fields = ("queried_by",)
