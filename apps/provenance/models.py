from django.conf import settings
from django.db import models

from apps.common.models import BaseModel


class ProvenanceQueryLog(BaseModel):
    queried_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="provenance_queries",
    )
    query_type = models.CharField(max_length=50)
    reference_id = models.UUIDField(null=True, blank=True)
    reference_type = models.CharField(max_length=50, blank=True, default="")
    result_summary = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "provenance_query_log"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Provenance query by {self.queried_by} on {self.reference_type}:{self.reference_id}"
