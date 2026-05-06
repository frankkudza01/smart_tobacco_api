# Flutter, WhatsApp, and AI integration

## Auth / session (`GET /api/v1/auth/me/`)

The user payload now includes **`organization_id`** and **`organization_name`** (primary membership via `get_user_primary_organization`). The API **does not trust** a client-sent `org_id` for authorization; always derive scope from the authenticated user and memberships.

## Standard error envelope

DRF errors are wrapped as:

```json
{
  "success": false,
  "data": null,
  "meta": { "status_code": 400, "request_id": "..." },
  "errors": [{ "code": "...", "message": "...", "field": "..." }]
}
```

Successful responses for existing endpoints largely keep their shapes (e.g. `{ "results": [...] }`). Use `apps.common.api_envelope.success_envelope()` when adding new endpoints that should follow the full success envelope.

## AI forecasting & anomalies

| Path | Notes |
|------|--------|
| `GET /api/v1/ai/forecasts/yield/` | Role-scoped via `ForecastService` |
| `GET /api/v1/ai/forecasts/price/` | Role-scoped |
| `GET /api/v1/ai/anomalies/` | List with optional `status`, `severity`, `type`, `subject` |
| `GET /api/v1/ai/anomalies/<id>/case/` | Case packet + redacted evidence for farmer/buyer |
| `POST /api/v1/ai/assistant/chat/` | Hardened tool-calling assistant (throttled) |
| `GET /api/v1/ai/anomalies/<id>/export-link/` | **Auditor/admin** — returns `export_url` (signed, short-lived) |
| `GET /api/v1/ai/exports/anomaly/?t=...` | Download JSON case packet (validates token + role) |

On **new** `AnomalyAlert` rows, the server creates in-app `Notification` rows and sends **FCM data** pushes when `FCM_LEGACY_SERVER_KEY` is set (payload: `type`, `anomaly_id`, `deep_link` only).

## Device registration (push)

`POST /api/v1/devices/register/`  
Body: `{ "token": "<fcm_token>", "platform": "android" | "ios" | "web" }`  
Associates the token with the current user and primary org (denormalized).

## Offline sync

| Path | Purpose |
|------|---------|
| `POST /api/v1/sync/` | Full batch (all supported `payload_type` values) |
| `POST /api/v1/sync/events/batch/` | Only `trace_event` |
| `POST /api/v1/sync/documents/batch/` | Only `document_meta` |
| `GET /api/v1/sync/changes/?since=<iso>&limit=<n>` | Incremental sync outcomes for the current user |

`document_meta` accepts optional `file_base64` for small files; otherwise a placeholder file is stored so the row can exist and be hash-anchored later.

## WhatsApp

- **Webhook (Twilio):** `POST /api/v1/whatsapp/webhook/` or `POST /whatsapp/webhook/` (alias).
- **Signature:** validated by the configured provider (`apps.whatsapp.twilio_service`).
- **Replay:** `MessageSid` is deduplicated in cache (~48h).
- **Rate limit:** per normalized phone, per minute (`WHATSAPP_WEBHOOK_RATE_LIMIT_PER_MINUTE`).
- **Farmer-style commands:** `FORECAST`, `MY ALERTS`, `EXPLAIN ALERT <uuid>`, plus existing flows.
- **Buyer:** `PORTFOLIO FORECAST`, `PORTFOLIO ALERTS`, `OPEN CASE <uuid>`.
- **Auditor:** `SEARCH ANOMALIES`, `EXPORT CASE <uuid>` (needs `PUBLIC_API_BASE_URL` for absolute links).

Deep links use `APP_DEEP_LINK_SCHEME` (default `app`), e.g. `app://anomaly/<id>`.

## Environment variables

| Variable | Purpose |
|----------|---------|
| `APP_DEEP_LINK_SCHEME` | Flutter custom scheme |
| `PUBLIC_API_BASE_URL` | Absolute API base for WhatsApp export URLs |
| `FCM_LEGACY_SERVER_KEY` | Optional; enables legacy FCM HTTP push |
| `WHATSAPP_WEBHOOK_RATE_LIMIT_PER_MINUTE` | Default 60 |

## How to test (backend)

```bash
cd backend
python manage.py migrate
python manage.py test tests.test_ai_intelligence.AnomalyExportSignedTests -v2
```

Pytest-based tests require a working Postgres test database as configured in `config.settings.test`.
