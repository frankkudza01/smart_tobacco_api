from __future__ import annotations

import logging
from typing import Callable

from apps.ai_intelligence.detectors import document_detectors
from apps.ai_intelligence.detectors import grading_detectors
from apps.ai_intelligence.detectors import trace_detectors
from apps.ai_intelligence.detectors import yield_detector

logger = logging.getLogger(__name__)


def run_anomaly_detection(organization, detection_types: list[str] | None = None) -> int:
    """
    Run enabled detectors for an organization. Returns count of new alerts created.
    """
    types = set(detection_types) if detection_types else None
    created = 0
    runners: list[tuple[str, Callable[..., int]]] = [
        ("document", document_detectors.run_all),
        ("trace", trace_detectors.run_all),
        ("grading", grading_detectors.run_all),
        ("yield", yield_detector.run_all),
    ]
    for name, fn in runners:
        if types is not None and name not in types:
            continue
        try:
            created += int(fn(organization))
        except Exception:
            logger.exception("Detector %s failed for org %s", name, organization.id)
    return created
