"""Role-scoped document verification by hash or uploaded bytes."""
from __future__ import annotations

from apps.common.access import can_view_document
from apps.common.org_utils import get_user_primary_organization
from apps.common.utils import compute_sha256
from apps.documents.models import Document
from apps.documents.services import verify_document


def verify_hash_for_user(*, user, sha256_hex: str) -> dict:
    org = get_user_primary_organization(user)
    if not org or not sha256_hex:
        return {"verified": False, "matches": []}
    qs = Document.objects.filter(organization_id=org.id, sha256_hash=sha256_hex.lower())
    matches = []
    for doc in qs[:20]:
        if not can_view_document(user, doc):
            continue
        vr = verify_document(doc)
        matches.append(
            {
                "document_id": str(doc.id),
                "verified": vr.get("hash_match", False),
                "matched_lot_id": str(doc.lot_id) if doc.lot_id else None,
                "anchor_status": doc.anchor_status,
                "chain_tx_hash": doc.anchor_tx_hash if user.role in (
                    "REGULATOR_AUDITOR",
                    "SYSTEM_ADMIN",
                    "BUYER_CONTRACTOR",
                    "SMALLHOLDER_FARMER",
                )
                else None,
                "anchored_at": None,
            }
        )
    return {"verified": bool(matches and matches[0].get("verified")), "matches": matches}


def verify_upload_for_user(*, user, file) -> dict:
    h = compute_sha256(file)
    return verify_hash_for_user(user=user, sha256_hex=h)
