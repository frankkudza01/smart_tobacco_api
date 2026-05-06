# Requirements appendix — supervisor feedback (May 2026)

This document **extends** the functional / academic requirements of the Igwayi Hub platform in response to project supervision. It is the canonical place to cite how the system addresses **(A) reliance on external AI APIs** and **(B) GPS accuracy vs farm boundaries**.

## A) Local models (not only hosted LLMs / vision APIs)

**Requirement (appended):** Where the platform has a **locally-developed model**, that local model is the **primary** path. External AI APIs run **only as fallback** (and the response always declares which path was used). This justifies — academically and operationally — that the system can run on-premise and that the coursework demonstrates classical ML, not just API stitching.

**Implementation:**

1. **Ridge regression yield forecaster** (`apps/ai_intelligence/local_models/ridge_yield.py`) — `uses_external_api: false`
   - Trained when an organisation has **≥ 5** farm–season rows with `actual_yield_kg` recorded.
   - Features: bias, **z-scored** `expected_yield_kg`, **z-scored** `size_hectares`; target: `actual_yield_kg`.
   - Fitted in closed form (ridge penalty λ, default 2.0) with **no sklearn** dependency.
   - Predictions clipped to `[0, max(2.5 × max(actual), 1500)]` (no negative / runaway extrapolation).
   - **Accuracy is measured every retrain**: in-sample MAE/MAPE/RMSE/R² **and** k-fold CV (k = min(5, n // 2)) when `n ≥ 5`. Metrics are stored in `ForecastRun.metrics_json` and per-metric rows are written to `EvaluationMetricRun` so `/api/v1/ai/metrics/evaluation/` surfaces them.
   - When `n < 5` the deterministic baseline is used and tagged `baseline_expected_yield`; **no external API is called**.

2. **Local histogram leaf grader** (`apps/grading/local_leaf_histogram.py`) — **primary path**
   - Default provider chain in `grading_ai_service.suggest_grade_from_leaf_image`:
     `local_histogram_v1` → `openai_vision` → `gemini_vision`.
   - Tobacco-likeness gate (`leaflike_ratio` + Shannon entropy) refuses obviously non-leaf inputs **without** burning API quota.
   - Confidence is **hard-capped at 0.30** so consumers can never mistake a histogram heuristic for a foundation-model classification.
   - Caller can opt into the legacy API-first order for one call by sending `prefer_api=true` (multipart form field).
   - Response always carries `provider`, `provider_chain`, `provider_chain_position`, and `hallucination_guards` so the chosen path is auditable.

## B) GNSS drift, accuracy, and farm boundaries

**Requirement (appended):** Farm registration and downstream checks must tolerate **horizontal position uncertainty** (device accuracy, multipath, map digitisation) so minor coordinate shifts do not falsely invalidate a farm.

**Implementation:**

1. **Data model** (`Farm`):  
   - `geofence_horizontal_accuracy_m` — optional capture-time GNSS accuracy (metres).  
   - `boundary_check_tolerance_m` — configurable server margin (default **25 m**, allowed range 5–200 m) added to device accuracy for checks.

2. **Geometry helpers** (`apps/farms/geofence.py`):  
   - `geolocation_geofence_consistency` — strict point-in-polygon **or** “near boundary” acceptance when distance-to-edge ≤ `tolerance_m + horizontal_accuracy_m`.  
   - `POST /api/v1/farms/<uuid>/location-check/` — returns `consistent`, `mode`, `distance_to_boundary_m`, `effective_tolerance_m`.

3. **Registration validation** (`FarmSerializer`):  
   - When both a polygon and anchor coordinates are supplied, the anchor must be **consistent** with the polygon under the effective tolerance.  
   - Auto-generated point buffers (`_point_buffer_polygon`) **expand** with poor reported accuracy (`max(125 m, 1.5 × accuracy)` half-edge).

4. **Flutter** (`Farm` entity, `ApiConstants.farmLocationCheck`): fields and URL constant so the mobile app can surface tolerance and call the check endpoint when you wire UI.

## C) Blockchain traceability — Merkle batching, tamper-evidence, downloadable proofs

**Requirement (appended):** The platform must do more than write hashes to a chain — it must let a regulator (TIMB) or buyer **prove** that a specific lot's history has not been tampered with **after** anchoring, and do so cheaply enough that real-world volumes (thousands of trace events per day) are economically viable.

**Implementation:**

1. **Daily Merkle batch anchoring** (`apps/blockchain/merkle_service.py`, `apps/blockchain/merkle.py`)
   - A scheduled Celery task `build_and_anchor_daily_event_batch` collects every TraceEvent that landed in the last 24 h, builds a deterministic SHA-256 Merkle tree (Bitcoin convention: duplicate last leaf on odd levels), and submits **one** transaction — `TobaccoTraceability.anchorBatchRoot(merkleRoot, batchType, batchLabel, leafCount)` — instead of one tx per event.  
   - **Cost saving:** ~100× cheaper gas at scale (one `anchorBatchRoot` ≈ one `anchorEventHash` + ~1 storage slot, regardless of leaf count).  
   - **Idempotent** on `batch_label` (`trace_events-YYYY-MM-DD`); re-runs return the existing batch.  
   - Empty days still anchor `GENESIS_EMPTY_ROOT = sha256("")` so the daily attestation chain is **continuous** and missing days are detectable.

2. **Per-event inclusion proofs (`O(log n)`)**
   - For any anchored event, `compute_inclusion_proof` returns the sibling hashes + L/R positions needed to re-derive the on-chain Merkle root from the event's own hash.  
   - Verification is one SHA-256 per proof step. A regulator does **not** need the full database to verify a single event.

3. **Tamper-evidence audit endpoint** (`GET /api/v1/blockchain/integrity/<lot_uuid>/`)
   - Re-derives every event's hash from its stored payload, compares to the stored `event_hash`, walks the `prev_event_hash → event_hash` chain to detect re-ordering, and re-verifies each batched event against the on-chain Merkle root.  
   - Response: `{ event_count, events_intact, events_tampered, chain_intact, merkle_intact, events: [...] }` — auditor-grade and unambiguous.

4. **Downloadable proof bundle** (`GET /api/v1/blockchain/proof-bundle/<lot_uuid>/`)
   - Returns a single JSON document (`schema: smart-tobacco.proof-bundle.v1`) containing every event's canonical payload, prev/event hashes, Merkle inclusion proof, and on-chain anchor metadata (`tx_hash`, `block_number`, `chain_id`, `contract_address`, `merkle_root`).  
   - The companion **standalone verifier** (`apps/blockchain/verifier.py`) has **no Django imports** and re-derives the on-chain root for every event purely from the bundle. A buyer in another country can verify with ~50 lines of Python and zero access to our database.

5. **Smart contract additions** (`contracts/TobaccoTraceability.sol`)
   - New struct `BatchAnchor`, mapping `batchAnchors`, function `anchorBatchRoot`, view `verifyBatchRoot`, event `BatchRootAnchored(batchId, merkleRoot, leafCount, batchType, batchLabel, submitter, timestamp)`.  
   - The ABI in `apps/blockchain/contract_abi.py` is kept in sync.  
   - Existing `anchorEventHash` / `anchorDocumentHash` paths are unchanged — Merkle batching is **additive**.

6. **Off-chain model** (`MerkleAnchorBatch`)
   - Persists `merkle_root`, ordered `leaves_json`, `tx_hash`, `block_number`, `chain_id`, `gas_used`, `anchor_status`. The `leaves_json` ordering is what makes proofs reproducible — the service never re-sorts.

7. **Tests** (`apps/blockchain/tests/`)
   - `test_merkle.py` — pure-function correctness on trees of size 1–7, tamper detection on leaves and roots, accepts both `MerkleProofStep` objects and JSON-dict steps.  
   - `test_merkle_service.py` — end-to-end build → anchor → audit → bundle round-trip, including the negative cases (mutated event hash flagged; forged canonical payload flagged by the standalone verifier).

### Why this enhances **traceability** specifically

- **Regulator-grade evidence**: any tampering after anchoring (DB write, schema migration bug, or insider) is detected by the integrity endpoint.  
- **Public verifiability without trust**: the proof bundle + standalone verifier remove the need to trust this codebase or this database.  
- **Economic viability at real volumes**: daily Merkle batching keeps per-event on-chain cost negligible, which is what makes this approach deployable for a national board such as TIMB.

## D) Custody, inspection, revocation, reconciliation, and public verification (Tier 2 + Tier 3)

Tier 1 establishes that the trace history of a lot is **anchored and tamper-evident**. Tiers 2 and 3 add the human/regulatory loop on top: provable hand-overs, regulator attestations, drift detection, public scanning, and structured dispute trails.

### D.1 Co-signed custody transfers (Tier 2 #4) — `apps/blockchain/custody_service.py`

**Problem.** A lot moves farmer → buyer → exporter. If the platform alone records the transfer, a malicious operator could rewrite history. We need **both** parties to non-repudiably authorise the move.

**Solution.**
- Each user has a lazily-provisioned **secp256k1 ECDSA keypair** stored encrypted at rest with **Fernet** (key derived from `settings.SECRET_KEY`); see `apps/blockchain/key_service.py`.
- A custody transfer is a **two-step protocol**:
  1. *Initiate*: current holder posts to `/custody/initiate/`. Server builds a canonical payload (`{lot_id, from_address, to_address, weight_kg, transfer_timestamp, notes}`), hashes it (SHA-256), and the initiator's keypair ECDSA-signs the hash via **EIP-191 personal_sign**. Stored as `PENDING_ACCEPT`.
  2. *Accept*: recipient posts to `/custody/<id>/accept/`. Server **re-derives** the canonical payload from stored fields (rejects on drift), re-verifies the from-signature, signs with the recipient's keypair, then calls `recordCustodyTransfer(...)` which emits the `CustodyTransferred(lotId, from, to, payloadHash, weightGrams, timestamp, submitter)` event.
- The Solidity contract intentionally does **not** verify the ECDSA signatures itself (cheap-gas design) — it stores the joint payload hash. Off-chain verification (`verify_stored_transfer`) recovers both addresses with the same `eth_account` library a regulator would use, so the proof is regulator-replayable.
- Recipients can `decline`; initiators can `cancel`. Once `ANCHORED`, the on-chain `CustodyTransferred` event is permanent.

### D.2 Inspection attestations (Tier 2 #5) — `apps/blockchain/inspection_service.py`

A regulator/auditor anchors a structured inspection result on chain via `attestInspection(lotId, dataHash, score, notesUri)`:
- `score` ∈ [0, 100], `notesUri` may point to redacted off-chain notes (e.g. an IPFS URL) so PII does not land on-chain;
- the contract emits `InspectionAttested(inspectionId, lotId, inspector, score, dataHash, notesUri, timestamp)`;
- DB row `InspectionAttestation` mirrors the event for fast querying and links to a `BlockchainReceipt`.

This gives a TIMB inspector a public, time-stamped proof that an inspection occurred at a specific block height — the dissertation soundbite is **"non-repudiable inspection at block height X"**.

### D.3 Reconciliation / chain-reorg detector (Tier 2 #6) — `apps/blockchain/reconciliation_service.py`

A periodic Celery task `reconcile_anchored_receipts` re-reads every confirmed receipt from the chain via `gateway.verify_anchor(tx_hash)` and updates `BlockchainReceipt.reconciliation_status`:

| Status | Meaning |
|---|---|
| `OK` | On-chain matches the stored row |
| `DRIFT` | On-chain status disagrees (e.g. moved from CONFIRMED → FAILED via reorg) |
| `MISSING` | Chain returns "not verified" — possible reorg or RPC corruption |
| `UNVERIFIABLE` | Mock gateway or RPC error (cannot make a determination — alarm the operator) |

`/reconciliation/health/` exposes the counters; alerting is `True` if any `DRIFT` or `MISSING`.

### D.4 Public verification (Tier 3 #7) — no-auth endpoints

- `GET /api/v1/blockchain/public/tx/<tx_hash>/` — anyone (consumer, importer, regulator without an account) can confirm a transaction is recorded on the platform and see any revocations attached to it.
- `GET /api/v1/blockchain/public/lot/<lot_uuid>/` — minimal **PII-free** lot summary: lot number, district, province, crop year, anchored event count, latest known Merkle batch.

These endpoints have no authentication and intentionally return no farmer name, no addresses, no GPS — only data that can be made public per the privacy policy.

### D.5 Bale-level signed passport (Tier 3 #8) — `apps/blockchain/passport_service.py`

**Goal.** A buyer in another country scans a bale QR and gets a one-tap confirmation that this bale's traceability is real, *without* depending on us to be online or trustworthy.

**Token format.** Two URL-safe base64 segments joined by `.`:
- `body` = canonical JSON `{schema, lot_id, lot_number, tobacco_type, bale_index, issued_at, anchor:{...}}`
- `sig`  = `HMAC-SHA256(BLOCKCHAIN_PASSPORT_HMAC_SECRET, body)`

QR text is `smart-tobacco://passport?token=<token>`.

Verification (`/api/v1/blockchain/public/passport/verify/?token=…`) checks the HMAC **and** re-checks the embedded anchor against the live DB (Merkle batch root or per-event receipt). HMAC was chosen over ECDSA here because passport tokens must be **short** to print on bale labels.

### D.6 Anchor revocation / dispute attestation (Tier 3 #9) — `apps/blockchain/revocation_service.py`

When an auditor/admin disputes a previously anchored receipt:

- a Solidity `revokeAnchor(originalAnchorId, reasonHash)` call emits `AnchorRevoked(originalAnchorId, revocationId, revoker, reasonHash, timestamp)`;
- DB row `AnchorRevocation` records the structured `reason_code` (FRAUD_SUSPECTED / DUPLICATE / DATA_CORRECTION / DISPUTE / OTHER) and `reason_text`;
- the **original anchor is never deleted** — both records sit on chain so the audit trail is complete.

### Architectural notes
- ECDSA signing keys are **per user**, lazily created, **never** exposed via API. Only the `address` is returned.
- The system runs end-to-end on the **MockBlockchainGateway** for development; flipping `BLOCKCHAIN_ENABLED=True` and pointing at Hardhat/anvil/testnet swaps in the real gateway with no other code changes.
- All new endpoints are wired into `apps/blockchain/urls.py` and exposed under `/api/v1/blockchain/…`.
- See `docs/BLOCKCHAIN_E2E_TEST_GUIDE.md` for a full step-by-step runthrough you can copy/paste.

## Operational notes for the dissertation / report

- Cite **ridge regression** (linear model + L2 penalty, closed-form solution) and **explicit feature design** for yield.  
- Cite **error propagation** for GIS: effective margin = administrative tolerance + device-reported accuracy.  
- Cite **Merkle trees** (binary hash trees with `O(log n)` inclusion proofs) and the academic gas-cost argument for batched anchoring.  
- External APIs remain for conversational assistant and primary vision grading; local paths are **documented fallbacks** and **org-statistical** models.
