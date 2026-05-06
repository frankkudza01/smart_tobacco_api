import json

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.common.enums import BlockchainAnchorStatus, TraceEventType
from apps.common.models import BaseModel
from apps.common.utils import compute_sha256_from_bytes
from apps.lots.models import Lot


class TraceEvent(BaseModel):
    """
    Append-only traceability event. Once created, should never be updated or deleted.
    The event_hash provides tamper evidence for the canonical payload.
    """

    lot = models.ForeignKey(Lot, on_delete=models.CASCADE, related_name="trace_events")
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="trace_events",
    )
    event_type = models.CharField(max_length=30, choices=TraceEventType.choices, db_index=True)
    timestamp = models.DateTimeField()
    location = models.CharField(max_length=255, blank=True, default="")
    latitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    longitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    payload = models.JSONField(default=dict, blank=True)
    notes = models.TextField(blank=True, default="")
    prev_event_hash = models.CharField(
        max_length=64,
        blank=True,
        default="",
        db_index=True,
        help_text="Previous event hash in the append-only chain (64 hex chars; genesis is all zeros).",
    )
    event_hash = models.CharField(max_length=64, blank=True, default="", db_index=True)
    anchor_status = models.CharField(
        max_length=20,
        choices=BlockchainAnchorStatus.choices,
        default=BlockchainAnchorStatus.PENDING,
    )
    anchor_tx_hash = models.CharField(max_length=66, blank=True, default="")

    class Meta:
        db_table = "traceability_trace_event"
        ordering = ["timestamp"]
        indexes = [
            models.Index(fields=["lot", "event_type"]),
            models.Index(fields=["lot", "timestamp"]),
        ]

    def __str__(self):
        return f"{self.event_type} on Lot {self.lot.lot_number} at {self.timestamp}"

    def compute_hash(self) -> str:
        from apps.traceability.chain import GENESIS_PREV_EVENT_HASH

        prev = (self.prev_event_hash or "").strip() or GENESIS_PREV_EVENT_HASH
        canonical = json.dumps(
            {
                "lot_id": str(self.lot_id),
                "event_type": self.event_type,
                "timestamp": self.timestamp.isoformat(),
                "payload": self.payload,
                "prev_event_hash": prev,
            },
            sort_keys=True,
        )
        return compute_sha256_from_bytes(canonical.encode("utf-8"))

    def _enforce_and_normalize_prev(self) -> None:
        from apps.traceability.chain import (
            expected_prev_event_hash_for_lot,
            normalize_prev_event_hash,
        )

        expected = expected_prev_event_hash_for_lot(lot_id=self.lot_id)
        raw = (self.prev_event_hash or "").strip()
        if not raw:
            self.prev_event_hash = expected
            return
        try:
            normalized = normalize_prev_event_hash(raw)
        except ValueError as exc:
            raise ValidationError({"prev_event_hash": str(exc)}) from exc
        if normalized != expected:
            raise ValidationError(
                {
                    "prev_event_hash": (
                        "Does not match chain tip (strict ordering). "
                        "Use genesis (64 zeros) for the first event, or the latest "
                        "event_hash for subsequent events."
                    )
                }
            )
        self.prev_event_hash = normalized

    def save(self, *args, **kwargs):
        skip_chain = kwargs.pop("skip_chain_validation", False)
        if self.pk is None:
            if not skip_chain:
                self._enforce_and_normalize_prev()
            self.event_hash = self.compute_hash()
        super().save(*args, **kwargs)
