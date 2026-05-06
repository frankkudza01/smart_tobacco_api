# AI-Enhanced Zimbabwe Tobacco Supply Chain Platform — Backend

Production-ready Django backend for the Zimbabwe tobacco supply chain traceability platform. Supports farmer onboarding, role-based access, traceability event capture, document hashing/verification, blockchain proof anchoring, AI assistant workflows, offline-first sync, and regulator-grade provenance queries.

## Tech Stack

- **Django 5.1** + Django REST Framework
- **PostgreSQL 16** — primary database
- **Redis 7** — cache + Celery broker
- **Celery** — async task processing
- **Web3.py** — blockchain integration (mock + real adapters)
- **LangChain + OpenAI** — agentic AI assistant
- **MinIO** — S3-compatible document storage
- **drf-spectacular** — OpenAPI documentation
- **Docker Compose** — full local deployment

## Quick Start

### 1. Clone & Setup Environment

```bash
cd backend
cp .env.example .env
```

### 2. Docker Compose (Recommended)

```bash
docker-compose up --build
```

This starts: Django, PostgreSQL, Redis, MinIO, Celery Worker, Celery Beat, Nginx.

### 3. Run Migrations

```bash
docker-compose exec web python manage.py migrate
```

### 4. Create Superuser

```bash
docker-compose exec web python manage.py createsuperuser
```

### 5. Seed Test Data

```bash
docker-compose exec web python manage.py seed_data
```

To remove seeded rows (dev/demo): `python manage.py unseed_data` (use `--dry-run` first). Identifiers are defined in `apps/accounts/seed_constants.py`.

This creates test users for all roles:


| Role | Email | Password |
|------|-------|----------|
| Farmer | tafadzwa@example.com | farmer12345 |
| Farmer | chipo@example.com | farmer12345 |
| Buyer | james@zlt.co.zw | buyer12345 |
| Auditor | grace@timb.gov.zw | auditor12345 |
| Admin | admin@tobacco.zw | admin12345 |


### 6. Access

- **API**: http://localhost:8000/api/v1/
- **Swagger Docs**: http://localhost:8000/api/docs/
- **Admin Panel**: http://localhost:8000/admin/
- **MinIO Console**: http://localhost:9001/

### Flutter / Android: device cannot reach `127.0.0.1`
On a **phone or emulator**, `http://127.0.0.1:8000` is the **device itself**, not your PC — the app will fail with a connection error (often shown as “no connectivity”).


| Where the app runs | Base URL for your Django PC |
|--------------------|-----------------------------|
| **Android Emulator** (Android Studio) | `http://10.0.2.2:8000` |
| **Physical Android phone** (same Wi‑Fi as PC) | `http://<YOUR_PC_LAN_IP>:8000` (e.g. `http://192.168.1.15:8000`) |

**Backend:**

1. Bind to all interfaces: `python manage.py runserver 0.0.0.0:8000` (not only `127.0.0.1`).
2. Add `10.0.2.2` and your PC’s LAN IP to `DJANGO_ALLOWED_HOSTS` in `.env` (see `.env.example`).
3. If Windows asks, allow **Python** through the firewall for port **8000**.

**Flutter:** point Dio / `baseUrl` at `10.0.2.2` or the LAN IP — not `127.0.0.1`.

**HTTP cleartext:** Android 9+ may block plain `http://` in release builds; for **debug**, enable cleartext in `AndroidManifest.xml` (`android:usesCleartextTraffic="true"` on the application tag) or use a `networkSecurityConfig` during development.

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `POST /api/v1/auth/register/` | Register new user |
| `POST /api/v1/auth/login/` | JWT login |
| `POST /api/v1/auth/refresh/` | Refresh JWT token |
| `GET /api/v1/auth/me/` | Current user profile |
| `GET /api/v1/farms/` | List farms |
| `POST /api/v1/farms/` | Register farm (farmer) |
| `POST /api/v1/farms/<uuid>/location-check/` | GPS vs stored boundary (`latitude`, `longitude`, optional `horizontal_accuracy_m`) |
| `GET /api/v1/seasons/` | List seasons |
| `GET /api/v1/lots/` | List lots |
| `POST /api/v1/trace-events/` | Record trace event |
| `POST /api/v1/documents/` | Upload document |
| `POST /api/v1/documents/{id}/verify/` | Verify document |
| `GET /api/v1/grading/` | List grade records |
| `POST /api/v1/grading/` | Create grade record (buyer) |
| `POST /api/v1/grading/suggest/` | Leaf-grade suggestion (**local histogram** primary → OpenAI vision → Gemini fallback). Pass `prefer_api=true` to invert the chain for one call. |
| `GET /api/v1/ai/health/evaluation/` | Per-model summary: provider chain, hallucination guards, latest ridge yield metrics |
| `GET /api/v1/sales/` | List sales |
| `GET /api/v1/settlements/` | List settlements |
| `GET /api/v1/disputes/` | List disputes |
| `GET /api/v1/provenance/lots/{id}/` | Lot provenance |
| `POST /api/v1/sync/` | Batch sync |
| `GET /api/v1/notifications/` | User notifications |
| `POST /api/v1/ai/query/` | AI assistant query |
| `GET /api/v1/blockchain/receipts/` | Blockchain receipts |
| `GET /api/v1/blockchain/batches/` | List daily Merkle anchor batches (~100× cheaper than per-event anchoring) |
| `GET /api/v1/blockchain/batches/<uuid>/` | Single batch incl. ordered leaves (auditor) |
| `POST /api/v1/blockchain/batches/anchor-today/` | Manually trigger today's batch anchor (auditor/admin) |
| `GET /api/v1/blockchain/integrity/<lot_uuid>/` | Tamper-evidence audit: re-derive every event hash, verify Merkle inclusion, report drift |
| `GET /api/v1/blockchain/proof-bundle/<lot_uuid>/` | Download a self-contained verifiable JSON proof bundle for one lot |
| `GET /api/v1/blockchain/custody/me/address/` | Lazily provision and return the caller's ECDSA signing address |
| `POST /api/v1/blockchain/custody/initiate/` | Initiate a co-signed custody transfer (current holder signs) |
| `POST /api/v1/blockchain/custody/<uuid>/accept/` | Recipient signs + on-chain `CustodyTransferred` event emitted |
| `POST /api/v1/blockchain/custody/<uuid>/decline/` | Recipient refuses a pending transfer |
| `POST /api/v1/blockchain/custody/<uuid>/cancel/` | Initiator cancels a pending transfer |
| `GET /api/v1/blockchain/custody/<uuid>/` | Detail incl. live re-verification of both ECDSA signatures |
| `GET /api/v1/blockchain/custody/lot/<lot_uuid>/` | Custody chain for one lot |
| `POST /api/v1/blockchain/inspections/attest/` | Auditor anchors a TIMB inspection (`InspectionAttested` event) |
| `GET /api/v1/blockchain/inspections/lot/<lot_uuid>/` | All inspections for a lot |
| `POST /api/v1/blockchain/reconciliation/run/` | Manual sweep: re-read on-chain state, flag drift / missing / unverifiable |
| `GET /api/v1/blockchain/reconciliation/health/` | Drift counters + `blockchain_enabled` flag |
| `GET /api/v1/blockchain/public/tx/<tx_hash>/` | **Public, no auth**: confirm a tx exists on platform + list any revocations |
| `GET /api/v1/blockchain/public/lot/<lot_uuid>/` | **Public, no auth**: minimal anchored summary (no PII) |
| `POST /api/v1/blockchain/passport/issue/` | Issue an HMAC-signed bale passport token (+ `qr_text`) |
| `GET /api/v1/blockchain/public/passport/verify/?token=…` | **Public, no auth**: verify a scanned passport token |
| `POST /api/v1/blockchain/revocations/issue/` | Auditor issues a structured revocation against an anchored receipt |
| `GET /api/v1/blockchain/revocations/` | List all revocations (filterable) |
| `GET /api/v1/weather/zimbabwe/regions/` | Zimbabwe provinces + districts (`?kind=province` \| `district`) with lat/lon |
| `GET /api/v1/weather/zimbabwe/forecast/` | Current + 5-day/3h forecast + irrigation hint (`region`, `lat`+`lon`, or `farm_id`) |
| `GET /api/v1/health/` | Health check |
| `GET /api/v1/readiness/` | Readiness check |
| `GET/PATCH /api/v1/preferences/me/` | Language, guided mode, voice flag (tenant-scoped) |
| `GET /api/v1/i18n/strings/` | Localized strings (en/sn/nd + org overrides) |
| `GET /api/v1/ux/guided-forms/` | Guided form schemas for Flutter/WhatsApp |
| `GET /api/v1/monitoring/metrics/` | Daily ML metrics (auditor/admin) |
| `GET /api/v1/monitoring/drift/` | Drift records (auditor/admin) |
| `POST /api/v1/privacy/me/export/` | Data subject export request |
| `POST /api/v1/privacy/me/erasure/` | Erasure request |
| `GET /api/v1/analytics/disputes/summary/` | Dispute volume + resolution-time stats |
| `GET /api/v1/documents/suspects/` | Near-duplicate review queue (auditor/admin) |

See `docs/DISTINCTION_EVIDENCE.md` and `docs/privacy_policy.md` for metrics and privacy rules.

**Local ML & GIS robustness (supervisor requirements):** see `docs/PROJECT_REQUIREMENTS_APPENDIX.md` — on-server ridge yield when enough historical `actual_yield_kg` rows exist, histogram fallback for leaf grading without vision APIs, and GPS tolerance fields plus `location-check` for boundaries.

**Blockchain traceability (Merkle batching, tamper-evidence, downloadable proofs):** see `docs/PROJECT_REQUIREMENTS_APPENDIX.md` § C — daily `MerkleAnchorBatch` rolls up many off-chain hashes into one on-chain root via `TobaccoTraceability.anchorBatchRoot`, each event keeps an `O(log n)` inclusion proof, and `apps/blockchain/verifier.py` lets any third party verify a downloaded proof bundle offline.

## Running Tests

```bash
docker-compose exec web pytest
```

Or locally:

```bash
pip install -r requirements/local.txt
DJANGO_SETTINGS_MODULE=config.settings.test pytest
```

**Login 500 / `ConnectionError` to `127.0.0.1:6379`:** DRF throttles use the default cache. With `config.settings.local`, set `USE_REDIS_CACHE=false` in `.env` (default in `.env.example`) so Django uses **LocMem** and you do not need Redis on the host. Alternatively start Redis (e.g. `docker compose up redis -d` or install Redis for Windows) and set `USE_REDIS_CACHE=true`. Production-style settings still use Redis; `IGNORE_EXCEPTIONS` on the Redis client avoids hard 500s if Redis drops briefly.

## WhatsApp smoke test (end-to-end quick check)

Run a fast operational check for WhatsApp config, webhook routes, and command routing:

```bash
python manage.py whatsapp_smoke_test
```

Optional: send one real outbound test message through your configured provider:

```bash
python manage.py whatsapp_smoke_test --send-live-to +2637XXXXXXXX
```

## Celery on Windows

The default **prefork** pool often hits `PermissionError` / `WinError 5` on billiard semaphores. This project sets **`worker_pool=solo`** automatically when `sys.platform == "win32"` in `config/celery_app.py` (single process, one task at a time — fine for local dev).

If you start the worker manually and still see prefork in the banner, run:

```powershell
celery -A config worker -l info --pool=solo
```

Linux/macOS Docker/production keep the normal prefork pool.

## Architecture

Modular monolith with 21+ domain apps:

```
apps/
  common/           — Base models, enums, utils, middleware, access_control exports
  accounts/         — Custom User, profiles, JWT auth
  organizations/    — Orgs, memberships, RBAC
  farms/            — Farm registration
  seasons/          — Season management
  lots/             — Lot/bale tracking
  traceability/     — Append-only trace events
  documents/        — Upload, hashing, verification, fingerprints / near-duplicate hooks
  grading/          — Grade records
  sales/            — Sale records
  settlements/      — Payment tracking
  disputes/         — Dispute lifecycle, case packets, analytics summary
  provenance/       — Timeline assembly & audit queries
  sync/             — Offline-first batch sync
  notifications/    — In-app notifications
  ai_assistant/     — Legacy AI interaction log wiring
  ai_intelligence/  — Forecasting, anomaly detection, hardened assistant (RBAC tools)
  blockchain/       — Adapter pattern, async anchoring
  audit/            — Immutable audit logs
  whatsapp/         — Twilio webhook, multilingual command router
  worldready/       — i18n, preferences, UX metrics, SUS hooks
  ml_monitoring/    — ModelRun, DailyMetrics, DriftMetrics, dashboard APIs
  privacy_controls/ — Sensitive registry helpers, export/erasure requests
```

## AI intelligence — forecasting, anomalies, hardened assistant

**App:** `apps.ai_intelligence` (models, detectors, Celery tasks, REST + assistant).

**Tenant + RBAC:** `apps.common.access` (`can_view_farm`, `can_view_lot`, `can_view_document`, `can_view_settlement`, `can_view_anomaly_alert`) and `apps.common.org_utils.get_user_primary_organization` are the single source of truth. Buyer access unions `BuyerLotAssignment` and `Sale.buyer` within the same `organization_id`.

**REST (under `/api/v1/ai/`):**

| Method | Path | Notes |
|--------|------|--------|
| GET | `forecasts/yield/` | Role-scoped forecast points (`model_version` contains `yield`) |
| GET | `forecasts/price/` | Role-scoped price band points (`model_version` contains `price`) |
| POST | `forecasts/retrain/` | `SYSTEM_ADMIN` only — queues `retrain_forecasts_job` |
| GET | `anomalies/` | Filter `status`, `severity`, `type`, `subject` |
| POST | `anomalies/run/` | Buyer / auditor / admin — queues `run_anomaly_detection_job` |
| POST | `anomalies/<uuid>/label/` | Auditor / admin — `ReviewLabel` |
| GET | `anomalies/<uuid>/case/` | Case packet JSON (evidence PII-redacted for farmer/buyer) |
| POST | `assistant/chat/` | Hardened chat; throttle scope `assistant_chat` (default 30/min) |
| POST | `query/` | Same assistant as `assistant/chat` (legacy) |
| GET/POST | `metrics/evaluation/` | Ingest/list offline AUROC / MAPE-style metrics (auditor/admin) |

**Celery tasks:** `ai_intelligence.retrain_forecasts_job`, `ai_intelligence.run_anomaly_detection_job`, `ai_intelligence.record_evaluation_metric`.

**Jobs (manual):**

```bash
celery -A config call ai_intelligence.retrain_forecasts_job --args='["<org-uuid>","yield"]'
celery -A config call ai_intelligence.run_anomaly_detection_job --args='["<org-uuid>",["document","trace","grading","yield"]]'
```

**Evaluating MAPE / AUROC:** Train/score offline; persist rows via `POST /api/v1/ai/metrics/evaluation/` or `record_evaluation_metric` task. `ForecastRun.metrics_json` stores per-retrain MVP metrics.

**Tests:** `tests/test_ai_intelligence.py`, `tests/test_ai_redaction.py` (run with `config.settings.test` and PostgreSQL as in project test settings).

**Env (optional):** `AI_OPENAI_TIMEOUT_SECONDS`, `AI_OPENAI_MAX_RETRIES`, `AI_CIRCUIT_BREAKER_THRESHOLD`, `AI_CIRCUIT_BREAKER_COOLDOWN_SECONDS` (see `config/settings/base.py`).

## Key Design Decisions

- **UUID primary keys** for offline-first client UUID generation
- **Append-only TraceEvents** — never updated or deleted
- **Blockchain adapter pattern** — `MockBlockchainGateway` for dev, `Web3BlockchainGateway` for production
- **All blockchain writes async** via Celery — API never blocks on chain confirmation
- **Organization-scoped querysets** — no accidental cross-org data leaks
- **SHA-256 hashing** for documents and events — tamper evidence
- **Idempotency keys** on sync — duplicate-safe offline record processing

## Hardhat — real local chain for anchoring tests

The `hardhat/` directory runs a local Ethereum node and deploys the same contract the Django `Web3BlockchainGateway` calls (ABI-encoded `anchorEventHash` / `anchorDocumentHash`).

```bash
cd hardhat
npm install
npm run compile
npm run test:solidity
```

Terminal A (keep open): `npm run node` → RPC at `http://127.0.0.1:8545`, chain ID **31337**.

Terminal B: `npm run deploy:local` → copy printed env vars into `backend/.env`, set `BLOCKCHAIN_ENABLED=True`, restart Django and Celery.

Details: [hardhat/README.md](hardhat/README.md).

Optional Django↔chain integration tests (with node + deploy running):

```bash
set INTEGRATE_HARDHAT=1
set BLOCKCHAIN_CONTRACT_ADDRESS=0x...from_deploy
set BLOCKCHAIN_PRIVATE_KEY=0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80
pytest tests/test_blockchain_hardhat.py -v
```

## Solidity Contract

See `contracts/TobaccoTraceability.sol` for the on-chain anchoring contract supporting:
- Digital twin registration
- Event hash anchoring
- Document hash anchoring
- Proof verification
