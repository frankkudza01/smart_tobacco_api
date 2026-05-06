import logging

from django.db import transaction

from apps.traceability.models import TraceEvent

logger = logging.getLogger(__name__)


@transaction.atomic
def create_trace_event(
    *,
    lot,
    actor,
    event_type,
    timestamp,
    location="",
    latitude=None,
    longitude=None,
    payload=None,
    notes="",
    prev_event_hash: str | None = None,
) -> TraceEvent:
    event = TraceEvent(
        lot=lot,
        actor=actor,
        event_type=event_type,
        timestamp=timestamp,
        location=location,
        latitude=latitude,
        longitude=longitude,
        payload=payload or {},
        notes=notes,
        prev_event_hash=(prev_event_hash or "").strip(),
    )
    event.save()

    # Enqueue blockchain anchoring asynchronously
    try:
        from apps.blockchain.tasks import anchor_event_hash
        anchor_event_hash.delay(str(event.id))
    except Exception:
        logger.warning("Failed to enqueue blockchain anchoring for event %s", event.id)

    return event
