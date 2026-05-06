"""Append-only trace chain: genesis prev hash + tip linking for strict ordering."""

from __future__ import annotations

import re

# 32-byte zero commitment (hex, no 0x) — first event per lot must link here.
GENESIS_PREV_EVENT_HASH = "0" * 64

_HEX64 = re.compile(r"^[0-9a-f]{64}$")


def normalize_prev_event_hash(value: str | None) -> str:
    """Lowercase 64-char hex; strips optional 0x prefix."""
    if value is None:
        return ""
    s = str(value).strip().lower()
    if s.startswith("0x"):
        s = s[2:]
    if not _HEX64.match(s):
        raise ValueError(
            "prev_event_hash must be 64 lowercase hex characters (optionally 0x-prefixed)."
        )
    return s


def expected_prev_event_hash_for_lot(*, lot_id) -> str:
    """Tip of chain for lot: genesis if empty, else latest event's event_hash (by created_at)."""
    from apps.traceability.models import TraceEvent

    tip = (
        TraceEvent.objects.filter(lot_id=lot_id)
        .order_by("-created_at", "-id")
        .first()
    )
    if tip is None:
        return GENESIS_PREV_EVENT_HASH
    return tip.event_hash
