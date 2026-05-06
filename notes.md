======= Run the backend locally (no Docker) ===============

You still need PostgreSQL, Redis, and (with default settings) MinIO for S3 uploads. Install those on Windows (or use small Docker containers only for those three if you want).


====================== Prerequisites ====================

Python 3.11+ (match what the project expects)
PostgreSQL — create a database and user (e.g. tobacco_db / tobacco_user)
Redis — default localhost:6379
MinIO — default in settings is http://localhost:9000 with bucket tobacco-documents (create the bucket in MinIO console)

DATABASE_URL=postgres://tobacco_user:tobacco_pass@127.0.0.1:5432/tobacco_db
REDIS_URL=redis://127.0.0.1:6379/0
CELERY_BROKER_URL=redis://127.0.0.1:6379/1
AWS_S3_ENDPOINT_URL=http://127.0.0.1:9000

================== Database & static setup ==================

$env:DJANGO_SETTINGS_MODULE = "config.settings.local"
python manage.py migrate
python manage.py createsuperuser

If the project has seed_data:

    python manage.py seed_data


Run processes (three terminals)
Terminal A — Django

cd c:\Users\Kudzai\Desktop\projects\smart_tobacco_api\backend
.\venv\Scripts\Activate.ps1
# If that fails, try: .\.venv\Scripts\Activate.ps1
$env:DJANGO_SETTINGS_MODULE = "config.settings.local"
python manage.py runserver 0.0.0.0:8000
Terminal B — Celery worker (needed for blockchain anchoring, WhatsApp sends, etc.)

cd c:\Users\Kudzai\Desktop\projects\smart_tobacco_api\backend
.\venv\Scripts\Activate.ps1
# If that fails, try: .\.venv\Scripts\Activate.ps1
$env:DJANGO_SETTINGS_MODULE = "config.settings.local"
celery -A config worker -l info
Terminal C — Celery beat (only if you rely on scheduled tasks)

celery -A config beat -l info


===================== Check it’s up ===========================
API: http://127.0.0.1:8000/api/v1/health/
Docs: http://127.0.0.1:8000/api/docs/

Your workflow (real chain tests)
cd c:\Users\Kudzai\Desktop\projects\smart_tobacco_api\backend\hardhat
npm install
npm run compile
npm run test:solidity
Terminal 1 (leave running):

npm run node [runs the chains]

Terminal 2 — deploy:

npm run deploy:local
Copy the printed block into backend/.env, for example:

BLOCKCHAIN_ENABLED=True
BLOCKCHAIN_PROVIDER_URL=http://127.0.0.1:8545
BLOCKCHAIN_CHAIN_ID=31337
BLOCKCHAIN_CONTRACT_ADDRESS=<from deploy output>
BLOCKCHAIN_PRIVATE_KEY=0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80

===========================================================
Docker (dev compose or VPS prod compose) — same roles as above

Use profile `blockchain` to run Hardhat like `npm run node`. Solidity compile + tests run when building that image.

  docker compose --env-file .env -f docker-compose.yml --profile blockchain up -d --build   # local Docker stack + Hardhat
  COMPOSE_PROFILES=blockchain bash deploy/vps-deploy.sh up -d --build                         # VPS prod stack + Hardhat

Deploy contract (equivalent to `npm run deploy:local`):

  bash deploy/deploy-hardhat-contract.sh
  # Dev compose: COMPOSE_FILE=docker-compose.yml ENV_FILE=.env bash deploy/deploy-hardhat-contract.sh

Set Django/Celery RPC inside Compose to `http://hardhat:8545` (see `.env.production.example`). Production HTTP API remains Gunicorn+Nginx (not `runserver`).

See deploy/USAGE.txt for the full mapping (worker, beat, TLS).

===========================================================

WhatsApp First-Class Operational Channel — Complete Implementation
Architecture Decisions
State Machine Conversations: Every multi-step workflow (onboarding, farm registration, grading, sale, etc.) is a state machine with handle_<state>() methods, stored in WhatsAppConversation.state_data. Sessions expire after 30 minutes and are resumable.

Provider Abstraction: WhatsAppProvider base class with TwilioWhatsAppProvider, MetaWhatsAppProvider (placeholder), and MockWhatsAppProvider. The system is never tightly coupled to Twilio.

Two-Phase Intent Routing: Deterministic keyword matching first, LangChain AI fallback for free-text. Intents are role-aware (farmers see farm commands, buyers see grading/sale commands).

Media Pipeline: Inbound media is fetched from Twilio, validated, hashed (SHA-256), stored in S3/MinIO, linked as a Document, and queued for blockchain anchoring — all asynchronously via Celery.

New/Updated Files (19 files in apps/whatsapp/)
File	Purpose
models.py	5 models: WhatsAppContact, WhatsAppConversation, WhatsAppMessageLog, WhatsAppIntentLog, WhatsAppTemplateLog
session_service.py	Contact resolution, conversation lifecycle, state management
intent_router.py	Role-aware intent detection, lookup routing, AI fallback, help menus
twilio_service.py	Provider abstraction (WhatsAppProvider, Twilio, Meta, Mock)
media_service.py	Media download, validation, hashing, document storage
notification_service.py	15+ outbound notification functions for business events
tasks.py	5 Celery tasks: message send, OTP send, media processing, template notifications, bulk reminders
views.py	Webhook view + delivery status callback
admin.py	Admin registrations for all 5 models
workflows/base.py	Base workflow state machine with Reply tuple and utility methods
workflows/farmer_onboarding.py	8-state self-registration: OTP → name → national ID → district → language → confirm
workflows/farm_registration.py	9-state flow: name → district → location → size → variety → optional season → confirm
workflows/lot_and_events.py	LotCreationWorkflow (6 states) + EventCaptureWorkflow (5 states) with blockchain anchoring
workflows/document_upload.py	Handles both guided upload and unsolicited media with doc type and lot linking
workflows/dispute_workflow.py	6-state dispute creation with context selection, reason, explanation, optional evidence
workflows/buyer_workflows.py	4 buyer workflows: BuyerGradingWorkflow, BuyerSaleWorkflow, BuyerSettlementUpdateWorkflow, BuyerDisputeResponseWorkflow
Farmer Journeys Supported
Self-registration via OTP
Farm registration with optional season creation
Lot creation linked to seasons
Traceability event capture (planting, harvesting, curing, etc.)
Document/photo upload with hashing and blockchain anchoring
Settlement/payment status checks
Dispute creation with evidence
AI assistant Q&A in natural language
All lookups (lots, documents, provenance, trace)
Buyer Journeys Supported
Lot grading with grade record + trace event
Sale recording with automatic settlement creation + farmer notification
Settlement payment status updates with farmer notification
Dispute response (accept/reject/comment) with farmer notification
Provenance checks, operational summaries, pending action summaries
Test Coverage
tests/test_whatsapp_workflows.py — 40+ test cases across:

Session service (create, expire, advance, end)
Intent detection (farmer/buyer keywords, lookups, AI fallback)
Full farmer onboarding flow
Full farm registration flow
Lot creation flow
Event capture flow
Dispute creation flow
Buyer grading flow
Buyer sale flow
Webhook validation (valid, invalid, with media)
Delivery status callbacks
Notification service
Role-based help menus
Migration Required
Run python manage.py makemigrations whatsapp and python manage.py migrate to create the 5 new tables.

