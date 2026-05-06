# Blockchain Traceability — End-to-End Test Guide

This guide walks you through exercising **every** Tier 1 / Tier 2 / Tier 3
blockchain feature against the running stack. Two paths:

* **Path A — automated tests** (fast, ~30 s, runs on the MockBlockchainGateway).
* **Path B — manual API walkthrough** (live, runs against a real `docker-compose up` stack — proves the endpoints work end-to-end).

> All `<...>` placeholders below are real values you copy from the previous
> response. Replace `localhost:8000` with your own host if different.

---

## 0. One-time setup

```bash
cd backend
docker-compose up --build -d
docker-compose exec web python manage.py migrate
docker-compose exec web python manage.py seed_data
```

Pick three test users from `apps/accounts/seed_constants.py`:

| Role | Email | Password |
|---|---|---|
| Farmer | `tafadzwa@example.com` | `farmer12345` |
| Buyer | one of the seeded buyers (e.g. `buyer1@example.com`) | `buyer12345` |
| Auditor | `auditor@example.com` | `auditor12345` |

Get a JWT for each:

```bash
TOKEN_FARMER=$(curl -s -X POST localhost:8000/api/v1/auth/login/ \
  -H 'Content-Type: application/json' \
  -d '{"email":"tafadzwa@example.com","password":"farmer12345"}' | jq -r .access)

TOKEN_BUYER=$(curl -s -X POST localhost:8000/api/v1/auth/login/ \
  -H 'Content-Type: application/json' \
  -d '{"email":"buyer1@example.com","password":"buyer12345"}' | jq -r .access)

TOKEN_AUDITOR=$(curl -s -X POST localhost:8000/api/v1/auth/login/ \
  -H 'Content-Type: application/json' \
  -d '{"email":"auditor@example.com","password":"auditor12345"}' | jq -r .access)
```

You'll need a real `lot_id` and the `farmer` user UUID — get them once and reuse:

```bash
LOT_ID=$(curl -s localhost:8000/api/v1/lots/ -H "Authorization: Bearer $TOKEN_FARMER" \
  | jq -r '.results[0].id')

BUYER_ID=$(curl -s localhost:8000/api/v1/auth/me/ -H "Authorization: Bearer $TOKEN_BUYER" \
  | jq -r .id)
```

---

## Path A — Automated tests (recommended first)

```bash
docker-compose exec web pytest apps/blockchain/tests/ -v
```

Expected: every test passes.

| Test file | What it proves |
|---|---|
| `test_merkle.py` | Pure Merkle math: root, inclusion proof, tamper detection (Tier 1) |
| `test_merkle_service.py` | Build → anchor → audit → proof bundle round-trip; tamper detection at every layer (Tier 1) |
| `test_passport.py` | HMAC sign/verify, secret rotation invalidates old tokens (Tier 3 #8) |
| `test_custody_inspection_revocation.py` | Two-step ECDSA co-signed custody, inspection attestation, revocation, reconciliation status (Tier 2 #4/#5/#6, Tier 3 #9) |

Run a single feature group:

```bash
docker-compose exec web pytest apps/blockchain/tests/test_merkle_service.py -v
docker-compose exec web pytest apps/blockchain/tests/test_custody_inspection_revocation.py -v
```

---

## Path B — Manual API walkthrough

### Tier 1 — Merkle batch anchoring + audit + proof bundle

**1. Anchor today's batch** (auditor)

```bash
curl -s -X POST localhost:8000/api/v1/blockchain/batches/anchor-today/ \
  -H "Authorization: Bearer $TOKEN_AUDITOR" | jq
# → {"created":true, "batch":{"batch_label":"trace_events-2026-05-02", "merkle_root":"...", "tx_hash":"0x..."}}
```

**2. List all batches**

```bash
curl -s localhost:8000/api/v1/blockchain/batches/ \
  -H "Authorization: Bearer $TOKEN_AUDITOR" | jq
```

**3. Tamper-evidence audit for a lot**

```bash
curl -s localhost:8000/api/v1/blockchain/integrity/$LOT_ID/ \
  -H "Authorization: Bearer $TOKEN_FARMER" | jq
# → {"event_count":N, "events_intact":N, "events_tampered":0,
#    "chain_intact":true, "merkle_intact":true, "events":[...]}
```

**4. Download a proof bundle and verify it offline**

```bash
curl -s -OJ localhost:8000/api/v1/blockchain/proof-bundle/$LOT_ID/ \
  -H "Authorization: Bearer $TOKEN_FARMER"
# Saves: lot-<lot_number>.proof.json

# Verify with the standalone (no-Django) verifier:
docker-compose exec web python -c "
import json
from apps.blockchain.verifier import verify_proof_bundle
bundle = json.load(open('lot-XYZ.proof.json'))
print(json.dumps(verify_proof_bundle(bundle), indent=2))
# → {'ok': True, 'all_event_hashes_match': True, 'chain_intact': True, 'merkle_intact': True, ...}
"
```

**5. Tamper test (proves it works)**

Edit one byte of `canonical_payload.payload` in the JSON file, re-run the verifier:

```python
# Should print: {"ok": false, "all_event_hashes_match": false, "events":[{"hash_match": false,...}]}
```

---

### Tier 2 #4 — Co-signed custody transfer

**1. Provision signing addresses**

```bash
curl -s localhost:8000/api/v1/blockchain/custody/me/address/ \
  -H "Authorization: Bearer $TOKEN_FARMER" | jq
# → {"address":"0xAbc..."}
```

**2. Farmer initiates transfer to buyer**

```bash
TRANSFER_ID=$(curl -s -X POST localhost:8000/api/v1/blockchain/custody/initiate/ \
  -H "Authorization: Bearer $TOKEN_FARMER" -H 'Content-Type: application/json' \
  -d "{\"lot_id\":\"$LOT_ID\",\"to_user_id\":\"$BUYER_ID\",\"weight_kg\":\"500.0\",\"notes\":\"first hand-over\"}" \
  | jq -r .id)
echo $TRANSFER_ID

# Inspect: status=PENDING_ACCEPT, from_signature populated, to_signature empty.
curl -s localhost:8000/api/v1/blockchain/custody/$TRANSFER_ID/ \
  -H "Authorization: Bearer $TOKEN_FARMER" | jq
```

**3. Buyer accepts → ECDSA co-sign + on-chain anchor**

```bash
curl -s -X POST localhost:8000/api/v1/blockchain/custody/$TRANSFER_ID/accept/ \
  -H "Authorization: Bearer $TOKEN_BUYER" | jq
# → status: ANCHORED, anchor_tx_hash: 0x..., to_signature populated
```

**4. Verify both signatures live**

```bash
curl -s localhost:8000/api/v1/blockchain/custody/$TRANSFER_ID/ \
  -H "Authorization: Bearer $TOKEN_FARMER" | jq .verification
# → {"from_signature_valid":true,"to_signature_valid":true,"payload_hash_matches":true,"anchored":true,...}
```

**5. Negative checks (must fail)**

- Try accepting from the wrong account → expect `400 designated recipient`.
- Try cancelling as the buyer → expect `400 initiator`.
- Initiate a second transfer with the same farmer-as-recipient → expect `400 must differ`.

---

### Tier 2 #5 — Inspection attestation

```bash
curl -s -X POST localhost:8000/api/v1/blockchain/inspections/attest/ \
  -H "Authorization: Bearer $TOKEN_AUDITOR" -H 'Content-Type: application/json' \
  -d "{\"lot_id\":\"$LOT_ID\",\"score\":92,\"summary\":\"Visual + moisture pass\",\"notes_uri\":\"https://example.com/insp/123.pdf\"}" \
  | jq

# Inspections for this lot:
curl -s localhost:8000/api/v1/blockchain/inspections/lot/$LOT_ID/ \
  -H "Authorization: Bearer $TOKEN_AUDITOR" | jq
```

A non-auditor must get `403`:

```bash
curl -s -o /dev/null -w '%{http_code}\n' -X POST localhost:8000/api/v1/blockchain/inspections/attest/ \
  -H "Authorization: Bearer $TOKEN_FARMER" -H 'Content-Type: application/json' \
  -d "{\"lot_id\":\"$LOT_ID\",\"score\":50}"
# → 403
```

Score validation:

```bash
curl -s -X POST localhost:8000/api/v1/blockchain/inspections/attest/ \
  -H "Authorization: Bearer $TOKEN_AUDITOR" -H 'Content-Type: application/json' \
  -d "{\"lot_id\":\"$LOT_ID\",\"score\":150}"
# → 400 score must be between 0 and 100
```

---

### Tier 2 #6 — Reconciliation / chain-reorg detector

```bash
# Run a sweep manually:
curl -s -X POST localhost:8000/api/v1/blockchain/reconciliation/run/ \
  -H "Authorization: Bearer $TOKEN_AUDITOR" -H 'Content-Type: application/json' \
  -d '{"batch_size":50}' | jq
# Mock chain → expect "unverifiable":N (this is the operator-warning that real chain isn't enabled)

# Health (anyone authenticated):
curl -s localhost:8000/api/v1/blockchain/reconciliation/health/ \
  -H "Authorization: Bearer $TOKEN_FARMER" | jq
# → {"total_receipts":N,"by_status":{...},"alerting":false,"blockchain_enabled":false}
```

Once you flip `BLOCKCHAIN_ENABLED=True` (and Hardhat is running with the deployed contract), the same call should report `"ok": N` and `"blockchain_enabled": true`.

---

### Tier 3 #7 — Public no-auth verification

Pick any `tx_hash` from the previous steps (or the receipts list).

```bash
# Public, no auth header:
TX_HASH=$(curl -s localhost:8000/api/v1/blockchain/receipts/ \
  -H "Authorization: Bearer $TOKEN_AUDITOR" | jq -r '.results[0].tx_hash')

curl -s localhost:8000/api/v1/blockchain/public/tx/$TX_HASH/ | jq
# → {"verified":true, "tx_hash":"0x...", "reference_type":"...", "method_name":"...", "revocations":[...]}

# Public lot summary (no PII):
curl -s localhost:8000/api/v1/blockchain/public/lot/$LOT_ID/ | jq
# → {"verified":true,"lot":{"lot_number":"..."},"farm_district":"...","events_total":N,"events_anchored":N,"latest_known_batch":{...}}
```

Confirm there's no `Authorization` header — both endpoints return 200 anyway.

---

### Tier 3 #8 — Bale-level signed passport

```bash
# Issue a token for bale #1 of this lot (printer would convert qr_text to a QR):
PASSPORT=$(curl -s -X POST localhost:8000/api/v1/blockchain/passport/issue/ \
  -H "Authorization: Bearer $TOKEN_FARMER" -H 'Content-Type: application/json' \
  -d "{\"lot_id\":\"$LOT_ID\",\"bale_index\":1}")
echo "$PASSPORT" | jq

TOKEN=$(echo "$PASSPORT" | jq -r .token)
echo "QR will encode: $(echo "$PASSPORT" | jq -r .qr_text)"

# Public verify (no auth — this is what a buyer's scanner hits):
curl -s "localhost:8000/api/v1/blockchain/public/passport/verify/?token=$TOKEN" | jq
# → {"ok":true,"signature_valid":true,"lot_id":"...","bale_index":1,"on_chain_match":true|null,...}
```

Tamper test: replace the last 4 chars of `$TOKEN` with `XXXX` and re-call → expect `{"ok": false, "error":"signature_invalid"}`.

---

### Tier 3 #9 — Anchor revocation / dispute attestation

Pick any anchored receipt from the receipts list (e.g. the custody transfer's `BlockchainReceipt`):

```bash
RECEIPT_ID=$(curl -s "localhost:8000/api/v1/blockchain/receipts/?reference_type=custody_transfer" \
  -H "Authorization: Bearer $TOKEN_AUDITOR" | jq -r '.results[0].id')

curl -s -X POST localhost:8000/api/v1/blockchain/revocations/issue/ \
  -H "Authorization: Bearer $TOKEN_AUDITOR" -H 'Content-Type: application/json' \
  -d "{\"target_receipt_id\":\"$RECEIPT_ID\",\"reason_code\":\"DISPUTE\",\"reason_text\":\"Buyer disputes weight; investigation opened.\"}" \
  | jq
# → {"reason_code":"DISPUTE","reason_hash":"...","anchor_tx_hash":"0x...","anchor_status":"CONFIRMED",...}
```

Confirm the original receipt is *not* deleted, but the public verifier now lists the revocation:

```bash
TX_HASH=$(curl -s localhost:8000/api/v1/blockchain/receipts/$RECEIPT_ID/ \
  -H "Authorization: Bearer $TOKEN_AUDITOR" 2>/dev/null | jq -r .tx_hash)
# (Or just reuse the tx_hash from earlier.)

curl -s localhost:8000/api/v1/blockchain/public/tx/$TX_HASH/ | jq .revocations
# → [{"reason_code":"DISPUTE","created_at":"...","anchor_tx_hash":"0x..."}]
```

---

## Health-check checklist

When you have run all of the above, you should see:

| Capability | How to confirm |
|---|---|
| Daily Merkle batch anchored | `GET /blockchain/batches/` shows today's row, `anchor_status=CONFIRMED` |
| Tamper-evidence works | `GET /blockchain/integrity/<lot>/` returns `events_tampered:0, chain_intact:true, merkle_intact:true` |
| Proof bundle is independently verifiable | Standalone `verifier.verify_proof_bundle` returns `ok:true` on a downloaded bundle, `ok:false` after editing one byte |
| Custody transfer is co-signed end-to-end | After accept, `verification.from_signature_valid` AND `verification.to_signature_valid` are both `true` |
| Inspection is anchored | Receipt with `method_name=attestInspection` appears in `/receipts/?reference_type=inspection_attestation` |
| Reconciliation reports operator state honestly | On Mock chain returns `unverifiable:N`; on real chain returns `ok:N` |
| Public verification works without auth | Calls to `/public/tx/...` and `/public/lot/...` return 200 with no `Authorization` header |
| Passport QR round-trips | `/public/passport/verify/?token=…` returns `ok:true`; tampering one char returns `ok:false` |
| Revocation is additive (not destructive) | After `revocations/issue/` the original receipt is unchanged; revocation surfaces in `public/tx/<tx>` |

---

## Switching to the real chain (optional, for full demo)

```bash
cd hardhat
npx hardhat node                                  # terminal 1
npx hardhat run scripts/deploy.js --network localhost   # terminal 2; copy contract address
```

Then in `backend/.env`:

```
BLOCKCHAIN_ENABLED=True
BLOCKCHAIN_PROVIDER_URL=http://host.docker.internal:8545
BLOCKCHAIN_CHAIN_ID=31337
BLOCKCHAIN_PRIVATE_KEY=<one of the hardhat node keys>
BLOCKCHAIN_CONTRACT_ADDRESS=<the deployed address>
```

Restart `web` + `worker` and re-run any of the steps above. The transactions
will now hit the real Hardhat node and `verify_anchor` calls will return real
on-chain confirmations (so reconciliation moves from `UNVERIFIABLE → OK`).
