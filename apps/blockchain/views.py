from django.http import JsonResponse
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.blockchain.custody_service import (
    CustodyError,
    accept_custody_transfer,
    cancel_custody_transfer,
    decline_custody_transfer,
    initiate_custody_transfer,
    list_custody_for_lot,
    verify_stored_transfer,
)
from apps.blockchain.gateway import get_blockchain_gateway
from apps.blockchain.inspection_service import (
    InspectionError,
    attest_inspection,
    list_inspections_for_lot,
)
from apps.blockchain.key_service import get_address
from apps.blockchain.merkle_service import (
    audit_lot_chain,
    build_and_anchor_event_batch,
    build_proof_bundle,
)
from apps.blockchain.models import (
    AnchorRevocation,
    BlockchainReceipt,
    CustodyTransfer,
    InspectionAttestation,
    MerkleAnchorBatch,
)
from apps.blockchain.passport_service import issue_passport, verify_passport_token
from apps.blockchain.reconciliation_service import (
    reconcile_receipts,
    reconciliation_health,
)
from apps.blockchain.revocation_service import (
    RevocationError,
    revoke_anchor,
)
from apps.blockchain.serializers import (
    AnchorRevocationSerializer,
    AnchorRevokeSerializer,
    AnchorVerifySerializer,
    BlockchainReceiptSerializer,
    CustodyInitiateSerializer,
    CustodyTransferSerializer,
    InspectionAttestSerializer,
    InspectionAttestationSerializer,
    MerkleAnchorBatchDetailSerializer,
    MerkleAnchorBatchListSerializer,
    PassportIssueSerializer,
    PassportVerifySerializer,
)
from apps.common.access import can_view_lot
from apps.common.permissions import IsAdminOrAuditor
from apps.lots.models import Lot


class BlockchainReceiptListView(generics.ListAPIView):
    serializer_class = BlockchainReceiptSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ["reference_type", "status"]
    ordering_fields = ["created_at"]

    def get_queryset(self):
        return BlockchainReceipt.objects.all()


class BlockchainVerifyView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = AnchorVerifySerializer

    def post(self, request):
        serializer = AnchorVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        gateway = get_blockchain_gateway()
        result = gateway.verify_anchor(serializer.validated_data["tx_hash"])
        return Response(result, status=status.HTTP_200_OK)


class MerkleBatchListView(generics.ListAPIView):
    """List Merkle anchor batches (most recent first)."""

    serializer_class = MerkleAnchorBatchListSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ["batch_type", "anchor_status"]
    ordering_fields = ["period_start", "created_at"]

    def get_queryset(self):
        return MerkleAnchorBatch.objects.all()


class MerkleBatchDetailView(generics.RetrieveAPIView):
    """Single Merkle batch incl. ordered leaves (auditor view)."""

    serializer_class = MerkleAnchorBatchDetailSerializer
    permission_classes = [IsAuthenticated, IsAdminOrAuditor]
    queryset = MerkleAnchorBatch.objects.all()


class MerkleBatchAnchorTodayView(APIView):
    """Manual trigger for today's batch (auditors / admins).

    Useful for demos and end-of-day catch-up; the same logic also runs as a
    scheduled Celery task.
    """

    permission_classes = [IsAuthenticated, IsAdminOrAuditor]

    def post(self, request):
        result = build_and_anchor_event_batch()
        batch = result.batch
        return Response(
            {
                "created": result.created,
                "skipped_reason": result.skipped_reason,
                "batch": {
                    "id": str(batch.id),
                    "batch_label": batch.batch_label,
                    "merkle_root": batch.merkle_root,
                    "leaf_count": batch.leaf_count,
                    "tx_hash": batch.tx_hash,
                    "anchor_status": batch.anchor_status,
                    "block_number": batch.block_number,
                    "chain_id": batch.chain_id,
                    "contract_address": batch.contract_address,
                },
            },
            status=status.HTTP_200_OK if not result.created else status.HTTP_201_CREATED,
        )


class LotIntegrityAuditView(APIView):
    """Re-derive every TraceEvent hash for a lot and report drift vs storage + on-chain root.

    This is the "tamper evidence" view: it answers "has anyone tampered with
    this lot's history since it was anchored?" with cryptographic certainty.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, lot_id):
        try:
            lot = Lot.objects.select_related("farm").get(id=lot_id)
        except Lot.DoesNotExist:
            return Response({"detail": "Lot not found."}, status=status.HTTP_404_NOT_FOUND)
        if not can_view_lot(request.user, lot):
            return Response({"detail": "Forbidden."}, status=status.HTTP_403_FORBIDDEN)

        report = audit_lot_chain(lot_id=lot.id)
        report["lot_number"] = lot.lot_number
        return Response(report, status=status.HTTP_200_OK)


class LotProofBundleView(APIView):
    """Download a self-contained verifiable proof bundle for a lot.

    Returns ``application/json`` with ``Content-Disposition: attachment`` so
    browsers save it as ``lot-<lot_number>.proof.json``. The structure is
    accepted by ``apps.blockchain.verifier.verify_proof_bundle`` and by the
    standalone verifier script we ship in the docs.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, lot_id):
        try:
            lot = Lot.objects.select_related("farm").get(id=lot_id)
        except Lot.DoesNotExist:
            return JsonResponse({"detail": "Lot not found."}, status=404)
        if not can_view_lot(request.user, lot):
            return JsonResponse({"detail": "Forbidden."}, status=403)

        bundle = build_proof_bundle(lot_id=lot.id)
        response = JsonResponse(bundle, json_dumps_params={"indent": 2})
        filename = f"lot-{lot.lot_number or lot.id}.proof.json"
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response


# ---------------------------------------------------------------------------
# Tier 2 #4 — Custody transfers (co-signed)
# ---------------------------------------------------------------------------


class CustodyTransferInitiateView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = CustodyInitiateSerializer

    def post(self, request):
        ser = CustodyInitiateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            lot = Lot.objects.get(id=ser.validated_data["lot_id"])
            to_user = User.objects.get(id=ser.validated_data["to_user_id"])
        except (Lot.DoesNotExist, User.DoesNotExist):
            return Response({"detail": "Lot or recipient user not found."}, status=404)
        if not can_view_lot(request.user, lot):
            return Response({"detail": "Forbidden."}, status=403)

        try:
            outcome = initiate_custody_transfer(
                lot=lot,
                from_user=request.user,
                to_user=to_user,
                weight_kg=ser.validated_data["weight_kg"],
                transfer_timestamp=ser.validated_data.get("transfer_timestamp"),
                notes=ser.validated_data.get("notes", ""),
            )
        except CustodyError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(
            CustodyTransferSerializer(outcome.transfer).data,
            status=status.HTTP_201_CREATED,
        )


class CustodyTransferAcceptView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        try:
            transfer = CustodyTransfer.objects.select_related("lot").get(id=pk)
        except CustodyTransfer.DoesNotExist:
            return Response({"detail": "Transfer not found."}, status=404)
        try:
            outcome = accept_custody_transfer(transfer=transfer, accepting_user=request.user)
        except CustodyError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(CustodyTransferSerializer(outcome.transfer).data)


class CustodyTransferDeclineView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        try:
            transfer = CustodyTransfer.objects.get(id=pk)
        except CustodyTransfer.DoesNotExist:
            return Response({"detail": "Transfer not found."}, status=404)
        try:
            transfer = decline_custody_transfer(transfer=transfer, declining_user=request.user)
        except CustodyError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(CustodyTransferSerializer(transfer).data)


class CustodyTransferCancelView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        try:
            transfer = CustodyTransfer.objects.get(id=pk)
        except CustodyTransfer.DoesNotExist:
            return Response({"detail": "Transfer not found."}, status=404)
        try:
            transfer = cancel_custody_transfer(transfer=transfer, cancelling_user=request.user)
        except CustodyError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(CustodyTransferSerializer(transfer).data)


class CustodyTransferDetailView(APIView):
    """Detail view that ALSO re-verifies both ECDSA signatures live."""

    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        try:
            transfer = CustodyTransfer.objects.select_related("lot").get(id=pk)
        except CustodyTransfer.DoesNotExist:
            return Response({"detail": "Transfer not found."}, status=404)
        if not can_view_lot(request.user, transfer.lot):
            return Response({"detail": "Forbidden."}, status=403)
        return Response(
            {
                "transfer": CustodyTransferSerializer(transfer).data,
                "verification": verify_stored_transfer(transfer),
            }
        )


class LotCustodyHistoryView(APIView):
    """All custody transfers for a single lot (chronological)."""

    permission_classes = [IsAuthenticated]

    def get(self, request, lot_id):
        try:
            lot = Lot.objects.get(id=lot_id)
        except Lot.DoesNotExist:
            return Response({"detail": "Lot not found."}, status=404)
        if not can_view_lot(request.user, lot):
            return Response({"detail": "Forbidden."}, status=403)
        transfers = list_custody_for_lot(lot_id=lot.id)
        return Response(CustodyTransferSerializer(transfers, many=True).data)


class MySigningAddressView(APIView):
    """Return the caller's ECDSA signing address (lazily generated)."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({"address": get_address(request.user)})


# ---------------------------------------------------------------------------
# Tier 2 #5 — Inspection attestations
# ---------------------------------------------------------------------------


class InspectionAttestView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrAuditor]
    serializer_class = InspectionAttestSerializer

    def post(self, request):
        ser = InspectionAttestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            lot = Lot.objects.get(id=ser.validated_data["lot_id"])
        except Lot.DoesNotExist:
            return Response({"detail": "Lot not found."}, status=404)
        try:
            outcome = attest_inspection(
                lot=lot,
                inspector=request.user,
                score=ser.validated_data["score"],
                summary=ser.validated_data.get("summary", ""),
                notes_uri=ser.validated_data.get("notes_uri", ""),
                inspected_at=ser.validated_data.get("inspected_at"),
            )
        except InspectionError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(
            InspectionAttestationSerializer(outcome.attestation).data,
            status=status.HTTP_201_CREATED,
        )


class LotInspectionsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, lot_id):
        try:
            lot = Lot.objects.get(id=lot_id)
        except Lot.DoesNotExist:
            return Response({"detail": "Lot not found."}, status=404)
        if not can_view_lot(request.user, lot):
            return Response({"detail": "Forbidden."}, status=403)
        attestations = list_inspections_for_lot(lot_id=lot.id)
        return Response(InspectionAttestationSerializer(attestations, many=True).data)


# ---------------------------------------------------------------------------
# Tier 2 #6 — Reconciliation
# ---------------------------------------------------------------------------


class ReconciliationRunView(APIView):
    """Manually trigger an on-demand reconciliation sweep (auditor/admin)."""

    permission_classes = [IsAuthenticated, IsAdminOrAuditor]

    def post(self, request):
        batch_size = int(request.data.get("batch_size", 50))
        batch_size = max(1, min(batch_size, 500))
        outcome = reconcile_receipts(batch_size=batch_size)
        return Response(
            {
                "receipts_checked": outcome.receipts_checked,
                "ok": outcome.ok,
                "drift": outcome.drift,
                "missing": outcome.missing,
                "unverifiable": outcome.unverifiable,
            }
        )


class ReconciliationHealthView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(reconciliation_health())


# ---------------------------------------------------------------------------
# Tier 3 #7 — Public verification endpoints (no auth)
# ---------------------------------------------------------------------------


class PublicTxVerifyView(APIView):
    """Public: anyone can verify a transaction hash without logging in.

    Designed for QR codes printed on bales: the URL points here, the consumer
    sees a confirmation that the lot's most recent anchor is genuine.
    """

    permission_classes = [AllowAny]
    authentication_classes: list = []

    def get(self, request, tx_hash):
        receipt = (
            BlockchainReceipt.objects.filter(tx_hash=tx_hash).order_by("-created_at").first()
        )
        if receipt is None:
            return Response({"verified": False, "error": "tx_hash_unknown"}, status=404)
        revocations = list(receipt.revocations.values("reason_code", "created_at", "anchor_tx_hash"))
        return Response(
            {
                "verified": True,
                "tx_hash": receipt.tx_hash,
                "reference_type": receipt.reference_type,
                "reference_id": str(receipt.reference_id),
                "method_name": receipt.method_name,
                "data_hash": receipt.data_hash,
                "block_number": receipt.block_number,
                "chain_id": receipt.chain_id,
                "contract_address": receipt.contract_address,
                "status": receipt.status,
                "reconciliation_status": receipt.reconciliation_status,
                "revocations": revocations,
                "created_at": receipt.created_at,
            }
        )


class PublicLotSummaryView(APIView):
    """Public: minimal anchored summary of a lot's traceability.

    Intentionally returns only **non-PII** fields so it can be exposed publicly
    (e.g. a buyer scanning a QR who is not registered on the platform).
    """

    permission_classes = [AllowAny]
    authentication_classes: list = []

    def get(self, request, lot_id):
        try:
            lot = Lot.objects.select_related("farm", "season").get(id=lot_id)
        except Lot.DoesNotExist:
            return Response({"verified": False, "error": "lot_not_found"}, status=404)

        from apps.traceability.models import TraceEvent

        events = TraceEvent.objects.filter(lot=lot).exclude(event_hash="").order_by("created_at")
        anchored_events = events.exclude(anchor_tx_hash="").count()
        latest_batch = (
            MerkleAnchorBatch.objects.filter(period_start__lte=lot.created_at).order_by("-period_start").first()
        )
        return Response(
            {
                "verified": True,
                "lot": {
                    "id": str(lot.id),
                    "lot_number": lot.lot_number,
                    "tobacco_type": lot.tobacco_type,
                },
                "farm_district": lot.farm.district,
                "farm_province": lot.farm.province,
                "crop_year": lot.season.crop_year,
                "events_total": events.count(),
                "events_anchored": anchored_events,
                "latest_known_batch": (
                    {
                        "batch_label": latest_batch.batch_label,
                        "merkle_root": latest_batch.merkle_root,
                        "tx_hash": latest_batch.tx_hash,
                    }
                    if latest_batch
                    else None
                ),
            }
        )


# ---------------------------------------------------------------------------
# Tier 3 #8 — Bale-level signed passport
# ---------------------------------------------------------------------------


class PassportIssueView(APIView):
    """Issue a signed QR passport token for a lot/bale (authenticated)."""

    permission_classes = [IsAuthenticated]
    serializer_class = PassportIssueSerializer

    def post(self, request):
        ser = PassportIssueSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            lot = Lot.objects.get(id=ser.validated_data["lot_id"])
        except Lot.DoesNotExist:
            return Response({"detail": "Lot not found."}, status=404)
        if not can_view_lot(request.user, lot):
            return Response({"detail": "Forbidden."}, status=403)
        bundle = issue_passport(lot=lot, bale_index=ser.validated_data.get("bale_index"))
        return Response(
            {
                "token": bundle.token,
                "qr_text": bundle.qr_text,
                "payload": bundle.payload,
            }
        )


class PassportVerifyView(APIView):
    """Public: verify a passport token (HMAC + on-chain anchor cross-check)."""

    permission_classes = [AllowAny]
    authentication_classes: list = []
    serializer_class = PassportVerifySerializer

    def get(self, request):
        token = request.query_params.get("token", "")
        if not token:
            return Response({"ok": False, "error": "token_required"}, status=400)
        return Response(verify_passport_token(token))


# ---------------------------------------------------------------------------
# Tier 3 #9 — Anchor revocation
# ---------------------------------------------------------------------------


class AnchorRevokeView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrAuditor]
    serializer_class = AnchorRevokeSerializer

    def post(self, request):
        ser = AnchorRevokeSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            target = BlockchainReceipt.objects.get(id=ser.validated_data["target_receipt_id"])
        except BlockchainReceipt.DoesNotExist:
            return Response({"detail": "Receipt not found."}, status=404)
        try:
            outcome = revoke_anchor(
                target_receipt=target,
                revoker=request.user,
                reason_code=ser.validated_data["reason_code"],
                reason_text=ser.validated_data["reason_text"],
            )
        except RevocationError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(
            AnchorRevocationSerializer(outcome.revocation).data,
            status=status.HTTP_201_CREATED,
        )


class AnchorRevocationListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = AnchorRevocationSerializer
    queryset = AnchorRevocation.objects.all()
    filterset_fields = ["reason_code", "anchor_status"]
    ordering_fields = ["created_at"]
