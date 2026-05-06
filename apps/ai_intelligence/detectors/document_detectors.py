from __future__ import annotations

import logging
from datetime import timedelta
from decimal import Decimal
from difflib import SequenceMatcher

from django.db.models import Count
from django.utils import timezone

from apps.ai_intelligence.models import AnomalyAlert, AnomalyEvidence
from apps.common.enums import AnomalyAlertType, AnomalyEvidenceType, AnomalySeverity, AnomalyAlertStatus, DocumentType
from apps.documents.models import Document
from apps.sales.models import Sale

logger = logging.getLogger(__name__)

MODEL_VERSION = "doc-detect-v1"


def run_all(organization) -> int:
    n = 0
    n += _detect_exact_duplicates(organization)
    n += _detect_near_duplicates(organization)
    n += _detect_receipt_sale_mismatch(organization)
    return n


def _detect_exact_duplicates(organization) -> int:
    created = 0
    dup_qs = (
        Document.objects.filter(
            lot__farm__organization=organization,
            sha256_hash__gt="",
        )
        .values("sha256_hash")
        .annotate(c=Count("id"))
        .filter(c__gt=1)
    )
    for row in dup_qs:
        h = row["sha256_hash"]
        docs = list(
            Document.objects.filter(
                lot__farm__organization=organization,
                sha256_hash=h,
            ).select_related("lot")
        )
        if len(docs) < 2:
            continue
        primary = docs[0]
        if AnomalyAlert.objects.filter(
            organization=organization,
            alert_type=AnomalyAlertType.DOC_DUPLICATE_EXACT,
            document_id=primary.id,
        ).exists():
            continue
        alert = AnomalyAlert.objects.create(
            organization=organization,
            alert_type=AnomalyAlertType.DOC_DUPLICATE_EXACT,
            severity=AnomalySeverity.HIGH,
            score=Decimal("1.0"),
            status=AnomalyAlertStatus.OPEN,
            lot=primary.lot,
            farm=primary.lot.farm if primary.lot_id else None,
            document=primary,
            detected_at=timezone.now(),
            model_version=MODEL_VERSION,
            title="Exact duplicate document hash",
        )
        AnomalyEvidence.objects.create(
            organization=organization,
            alert=alert,
            evidence_type=AnomalyEvidenceType.HASH_MATCH,
            payload_json={
                "sha256_hash": h,
                "matched_document_ids": [str(d.id) for d in docs],
            },
        )
        created += 1
    return created


def _detect_near_duplicates(organization) -> int:
    created = 0
    docs = list(
        Document.objects.filter(
            lot__farm__organization=organization,
        ).select_related("lot", "lot__season", "lot__farm")
    )
    threshold = 0.92
    seen_pairs: set[tuple[str, str]] = set()
    for i, a in enumerate(docs):
        text_a = f"{a.title}\n{a.description}".strip()
        if len(text_a) < 8:
            continue
        for b in docs[i + 1 :]:
            if a.lot_id != b.lot_id:
                continue
            text_b = f"{b.title}\n{b.description}".strip()
            ratio = SequenceMatcher(None, text_a, text_b).ratio()
            if ratio < threshold:
                continue
            if a.sha256_hash and a.sha256_hash == b.sha256_hash:
                continue
            key = tuple(sorted([str(a.id), str(b.id)]))
            if key in seen_pairs:
                continue
            seen_pairs.add(key)
            if AnomalyAlert.objects.filter(
                organization=organization,
                alert_type=AnomalyAlertType.DOC_DUPLICATE_NEAR,
                document=a,
            ).exists():
                continue
            alert = AnomalyAlert.objects.create(
                organization=organization,
                alert_type=AnomalyAlertType.DOC_DUPLICATE_NEAR,
                severity=AnomalySeverity.MEDIUM,
                score=Decimal(str(round(ratio, 4))),
                status=AnomalyAlertStatus.OPEN,
                lot=a.lot,
                farm=a.lot.farm,
                document=a,
                detected_at=timezone.now(),
                model_version=MODEL_VERSION,
                title="Near-duplicate document text",
            )
            AnomalyEvidence.objects.create(
                organization=organization,
                alert=alert,
                evidence_type=AnomalyEvidenceType.SIMILARITY,
                payload_json={
                    "similarity": ratio,
                    "other_document_id": str(b.id),
                    "overlapping_fields": ["title", "description"],
                },
            )
            created += 1
    return created


def _detect_receipt_sale_mismatch(organization) -> int:
    created = 0
    receipts = Document.objects.filter(
        lot__farm__organization=organization,
        document_type=DocumentType.RECEIPT,
    ).select_related("lot")
    for doc in receipts:
        lot = doc.lot
        if not lot:
            continue
        sale = Sale.objects.filter(lot=lot).order_by("-sale_date").first()
        if not sale:
            continue
        # Heuristic: sale_date vs document upload time — large skew may indicate mismatch
        window = timedelta(days=14)
        if abs((sale.sale_date - doc.created_at).total_seconds()) > window.total_seconds():
            if _make_receipt_sale_alert(
                organization,
                doc,
                lot,
                "date_outside_window",
                {"sale_date": sale.sale_date.isoformat(), "doc_created": doc.created_at.isoformat()},
            ):
                created += 1
        # Currency rule when receipt title mentions a currency different from sale
        title_u = (doc.title or "").upper()
        if "ZWL" in title_u and sale.currency.upper() == "USD":
            if _make_receipt_sale_alert(
                organization,
                doc,
                lot,
                "currency_mismatch_heuristic",
                {"sale_currency": sale.currency, "hint": "title mentions ZWL"},
            ):
                created += 1
    return created


def _make_receipt_sale_alert(organization, doc, lot, reason: str, detail: dict) -> bool:
    if AnomalyAlert.objects.filter(
        organization=organization,
        alert_type=AnomalyAlertType.RECEIPT_SALE_MISMATCH,
        document=doc,
    ).exists():
        return False
    alert = AnomalyAlert.objects.create(
        organization=organization,
        alert_type=AnomalyAlertType.RECEIPT_SALE_MISMATCH,
        severity=AnomalySeverity.MEDIUM,
        score=Decimal("0.75"),
        status=AnomalyAlertStatus.OPEN,
        lot=lot,
        farm=lot.farm,
        document=doc,
        detected_at=timezone.now(),
        model_version=MODEL_VERSION,
        title=f"Receipt vs sale mismatch ({reason})",
    )
    AnomalyEvidence.objects.create(
        organization=organization,
        alert=alert,
        evidence_type=AnomalyEvidenceType.RULE_VIOLATION,
        payload_json={"reason": reason, **detail},
    )
    return True
