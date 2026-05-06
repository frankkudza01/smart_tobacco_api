from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.common.enums import SaleType
from apps.common.models import BaseModel
from apps.lots.models import Lot


class SaleStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    ACCEPTED = "ACCEPTED", "Accepted"
    DECLINED = "DECLINED", "Declined"
    BOUGHT = "BOUGHT", "Bought"


class GradeAnnualPrice(BaseModel):
    grade = models.CharField(max_length=20, db_index=True)
    year = models.PositiveIntegerField(db_index=True)
    price_per_kg = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default="USD")
    notes = models.TextField(blank=True, default="")

    class Meta:
        db_table = "sales_grade_annual_price"
        ordering = ["-year", "grade"]
        unique_together = ("grade", "year")

    def __str__(self):
        return f"{self.grade} {self.year}={self.price_per_kg} {self.currency}"


class Sale(BaseModel):
    lot = models.ForeignKey(Lot, on_delete=models.CASCADE, related_name="sales")
    buyer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="purchases",
    )
    sale_type = models.CharField(max_length=20, choices=SaleType.choices, default=SaleType.AUCTION)
    price_per_kg = models.DecimalField(max_digits=10, decimal_places=2)
    total_weight_kg = models.DecimalField(max_digits=10, decimal_places=2)
    total_amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=3, default="USD")
    sale_date = models.DateTimeField()
    status = models.CharField(
        max_length=20,
        choices=SaleStatus.choices,
        default=SaleStatus.PENDING,
        db_index=True,
    )
    annual_price_year = models.PositiveIntegerField(default=timezone.now().year)
    grading_trail = models.JSONField(default=list, blank=True)
    ai_pricing_note = models.TextField(blank=True, default="")
    auction_floor_reference = models.CharField(max_length=100, blank=True, default="")
    contract_reference = models.CharField(max_length=100, blank=True, default="")
    notes = models.TextField(blank=True, default="")
    accepted_at = models.DateTimeField(null=True, blank=True)
    declined_at = models.DateTimeField(null=True, blank=True)
    bought_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "sales_sale"
        ordering = ["-sale_date"]

    def __str__(self):
        return f"Sale of Lot {self.lot.lot_number} - {self.total_amount} {self.currency}"
