from django.urls import path

from apps.blockchain.views import (
    AnchorRevocationListView,
    AnchorRevokeView,
    BlockchainReceiptListView,
    BlockchainVerifyView,
    CustodyTransferAcceptView,
    CustodyTransferCancelView,
    CustodyTransferDeclineView,
    CustodyTransferDetailView,
    CustodyTransferInitiateView,
    InspectionAttestView,
    LotCustodyHistoryView,
    LotInspectionsView,
    LotIntegrityAuditView,
    LotProofBundleView,
    MerkleBatchAnchorTodayView,
    MerkleBatchDetailView,
    MerkleBatchListView,
    MySigningAddressView,
    PassportIssueView,
    PassportVerifyView,
    PublicLotSummaryView,
    PublicTxVerifyView,
    ReconciliationHealthView,
    ReconciliationRunView,
)

urlpatterns = [
    # Receipts and basic verify
    path("receipts/", BlockchainReceiptListView.as_view(), name="blockchain-receipt-list"),
    path("verify/", BlockchainVerifyView.as_view(), name="blockchain-verify"),

    # Tier 1 — Merkle batches + tamper evidence + proof bundle
    path("batches/", MerkleBatchListView.as_view(), name="blockchain-batch-list"),
    path("batches/<uuid:pk>/", MerkleBatchDetailView.as_view(), name="blockchain-batch-detail"),
    path("batches/anchor-today/", MerkleBatchAnchorTodayView.as_view(), name="blockchain-batch-anchor-today"),
    path("integrity/<uuid:lot_id>/", LotIntegrityAuditView.as_view(), name="blockchain-lot-integrity"),
    path("proof-bundle/<uuid:lot_id>/", LotProofBundleView.as_view(), name="blockchain-lot-proof-bundle"),

    # Tier 2 #4 — Custody transfers
    path("custody/me/address/", MySigningAddressView.as_view(), name="blockchain-my-signing-address"),
    path("custody/initiate/", CustodyTransferInitiateView.as_view(), name="blockchain-custody-initiate"),
    path("custody/<uuid:pk>/accept/", CustodyTransferAcceptView.as_view(), name="blockchain-custody-accept"),
    path("custody/<uuid:pk>/decline/", CustodyTransferDeclineView.as_view(), name="blockchain-custody-decline"),
    path("custody/<uuid:pk>/cancel/", CustodyTransferCancelView.as_view(), name="blockchain-custody-cancel"),
    path("custody/<uuid:pk>/", CustodyTransferDetailView.as_view(), name="blockchain-custody-detail"),
    path("custody/lot/<uuid:lot_id>/", LotCustodyHistoryView.as_view(), name="blockchain-custody-lot"),

    # Tier 2 #5 — Inspection attestations
    path("inspections/attest/", InspectionAttestView.as_view(), name="blockchain-inspection-attest"),
    path("inspections/lot/<uuid:lot_id>/", LotInspectionsView.as_view(), name="blockchain-inspection-lot"),

    # Tier 2 #6 — Reconciliation
    path("reconciliation/run/", ReconciliationRunView.as_view(), name="blockchain-reconciliation-run"),
    path("reconciliation/health/", ReconciliationHealthView.as_view(), name="blockchain-reconciliation-health"),

    # Tier 3 #7 — Public verification (no auth)
    path("public/tx/<str:tx_hash>/", PublicTxVerifyView.as_view(), name="blockchain-public-tx"),
    path("public/lot/<uuid:lot_id>/", PublicLotSummaryView.as_view(), name="blockchain-public-lot"),

    # Tier 3 #8 — Bale-level passport
    path("passport/issue/", PassportIssueView.as_view(), name="blockchain-passport-issue"),
    path("public/passport/verify/", PassportVerifyView.as_view(), name="blockchain-public-passport-verify"),

    # Tier 3 #9 — Anchor revocation
    path("revocations/", AnchorRevocationListView.as_view(), name="blockchain-revocation-list"),
    path("revocations/issue/", AnchorRevokeView.as_view(), name="blockchain-revocation-issue"),
]
