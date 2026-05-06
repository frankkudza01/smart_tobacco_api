from django.conf import settings
from django.db import models

from apps.common.enums import UserRole
from apps.common.models import BaseModel


class Organization(BaseModel):
    name = models.CharField(max_length=255, unique=True)
    org_type = models.CharField(max_length=50, blank=True, default="")
    registration_number = models.CharField(max_length=100, blank=True, default="")
    address = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "organizations_organization"
        ordering = ["name"]

    def __str__(self):
        return self.name


class OrganizationMembership(BaseModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    role = models.CharField(max_length=30, choices=UserRole.choices)
    is_primary = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "organizations_membership"
        unique_together = ["user", "organization"]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user.email} @ {self.organization.name} ({self.role})"


class BuyerLotAssignment(BaseModel):
    """
    Explicit buyer ↔ lot assignment within a tenant.
    Buyers may also see lots via Sale.buyer; access layer unions both.
    """

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="buyer_lot_assignments",
    )
    buyer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="assigned_lots",
    )
    lot = models.ForeignKey(
        "lots.Lot",
        on_delete=models.CASCADE,
        related_name="buyer_assignments",
    )

    class Meta:
        db_table = "organizations_buyer_lot_assignment"
        unique_together = [["buyer", "lot"]]
        indexes = [
            models.Index(fields=["organization", "buyer"]),
            models.Index(fields=["organization", "lot"]),
        ]

    def __str__(self):
        return f"{self.buyer_id} → lot {self.lot_id}"
