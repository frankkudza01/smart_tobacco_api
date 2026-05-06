from __future__ import annotations

import hashlib
import json
import math
import re
from decimal import Decimal

from django.conf import settings
from django.utils import timezone

from apps.ai_intelligence.models import AnomalyAlert, AnomalyEvidence
from apps.ai_intelligence.services.pii_redaction import redact_text
from apps.common.enums import (
    AnomalyAlertStatus,
    AnomalyAlertType,
    AnomalyEvidenceType,
    AnomalySeverity,
)
from apps.documents.models import Document, DocumentFingerprint


def _stub_embedding_from_text(text: str, dim: int = 64) -> list[float]:
    h = hashlib.sha256(text.encode("utf-8", errors="ignore")).digest()
    out = []
    for i in range(dim):
        b = h[i % len(h)]
        out.append((b / 255.0) * 2 - 1.0)
    return out


def _cosine(a: list[float], b: list[float]) -> float:
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _extract_key_fields_llm(redacted_text: str) -> dict:
    """
    Uses the configured AI provider (see AI_PROVIDER + API keys), not OPENAI_API_KEY alone,
    so Celery does not call Gemini when the deployment is OpenAI-only.
    """
    if not getattr(settings, "AI_ENABLED", False):
        return _extract_key_fields_heuristic(redacted_text)
    from apps.ai_intelligence.services.openai_safe import chat_json_schema, has_provider_credentials

    if not has_provider_credentials():
        return _extract_key_fields_heuristic(redacted_text)

    schema = {
        "type": "object",
        "properties": {
            "vendor": {"type": "string"},
            "amount": {"type": "string"},
            "date": {"type": "string"},
            "receipt_no": {"type": "string"},
        },
        "required": ["vendor", "amount", "date", "receipt_no"],
        "additionalProperties": False,
    }
    try:
        return chat_json_schema(
            system_prompt="Extract receipt fields from redacted text only. Use empty string if unknown.",
            user_message=redacted_text[:4000],
            json_schema_name="receipt_fields",
            json_schema=schema,
        )
    except Exception:
        return _extract_key_fields_heuristic(redacted_text)


def _extract_key_fields_heuristic(text: str) -> dict:
    amt_m = re.search(r"(\d+[.,]\d{2})\s*(USD|ZWL)?", text)
    date_m = re.search(r"\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4}", text)
    return {
        "vendor": (text[:40] or "").strip(),
        "amount": amt_m.group(1) if amt_m else "",
        "date": date_m.group(0) if date_m else "",
        "receipt_no": "",
    }


def _key_overlap(a: dict, b: dict) -> int:
    n = 0
    for k in ("vendor", "amount", "date", "receipt_no"):
        if a.get(k) and b.get(k) and str(a[k]).lower()[:3] == str(b[k]).lower()[:3]:
            n += 1
        elif a.get(k) and b.get(k) and str(a[k]) == str(b[k]):
            n += 1
    return n


def build_or_update_fingerprint(document: Document) -> DocumentFingerprint:
    raw = f"{document.title}\n{document.description}"
    redacted = redact_text(raw)
    key_fields = _extract_key_fields_llm(redacted)
    emb = _stub_embedding_from_text(redacted)
    fp, _ = DocumentFingerprint.objects.update_or_create(
        document=document,
        defaults={
            "organization_id": document.organization_id,
            "extracted_text_redacted": redacted[:8000],
            "embedding_json": emb,
            "key_fields_json": key_fields,
        },
    )
    return fp


def scan_near_duplicates_for_document(document: Document, threshold: float = 0.88) -> int:
    if not document.organization_id:
        return 0
    try:
        fp = document.fingerprint
    except DocumentFingerprint.DoesNotExist:
        return 0
    peers = (
        DocumentFingerprint.objects.filter(
            organization_id=document.organization_id,
            document__document_type=document.document_type,
        )
        .exclude(document_id=document.id)
    )
    created = 0
    for other in peers[:200]:
        sim = _cosine(fp.embedding_json or [], other.embedding_json or [])
        overlap = _key_overlap(fp.key_fields_json or {}, other.key_fields_json or {})
        if sim >= threshold and overlap >= 2:
            if AnomalyAlert.objects.filter(
                organization_id=document.organization_id,
                alert_type=AnomalyAlertType.DOC_DUPLICATE_NEAR,
                document=document,
            ).exists():
                continue
            alert = AnomalyAlert.objects.create(
                organization_id=document.organization_id,
                alert_type=AnomalyAlertType.DOC_DUPLICATE_NEAR,
                severity=AnomalySeverity.MEDIUM,
                score=Decimal(str(round(sim, 4))),
                status=AnomalyAlertStatus.OPEN,
                lot=document.lot,
                farm=document.lot.farm if document.lot_id else None,
                document=document,
                detected_at=timezone.now(),
                model_version="embed-near-v1",
                title="Near-duplicate document",
            )
            AnomalyEvidence.objects.create(
                organization_id=document.organization_id,
                alert=alert,
                evidence_type=AnomalyEvidenceType.SIMILARITY,
                payload_json={
                    "similarity": sim,
                    "matched_document_id": str(other.document_id),
                    "matching_fields_estimate": overlap,
                },
            )
            created += 1
    return created
