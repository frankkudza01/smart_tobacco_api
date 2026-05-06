from django.conf import settings
from django.db import models

from apps.common.enums import SettlementStatus
from apps.common.models import BaseModel
from apps.sales.models import Sale


class Settlement(BaseModel):
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name="settlements")
    farmer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="settlements_received",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="settlements_created",
    )
    amount_due = models.DecimalField(max_digits=14, decimal_places=2)
    amount_paid = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    currency = models.CharField(max_length=3, default="USD")
    status = models.CharField(
        max_length=20,
        choices=SettlementStatus.choices,
        default=SettlementStatus.PENDING,
        db_index=True,
    )
    payment_reference = models.CharField(max_length=200, blank=True, default="")
    payment_method = models.CharField(max_length=50, blank=True, default="")
    payment_date = models.DateTimeField(null=True, blank=True)
    due_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True, default="")

    class Meta:
        db_table = "settlements_settlement"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Settlement for Sale {self.sale_id} - {self.status}"
