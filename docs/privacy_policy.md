# Privacy-by-design policy (operational)

This document describes **measurable** privacy rules enforced in the smart tobacco API. Implementation lives in `apps.privacy_controls` (export/erasure requests, encryption helpers), `apps.common.access` / `access_control.py` (RBAC + tenant scoping), `apps.privacy_controls.sensitive_registry` (field classifications), and `apps.privacy_controls.safe_logging` (redacted structured logs).

## On-chain

- Store **only cryptographic hashes** and minimal opaque identifiers required by the chain adapter.
- **Never** anchor PII (names, phone numbers, national IDs, bank details, free-form addresses) on-chain.

## Off-chain

- Operational data is stored in PostgreSQL and object storage under **organization (tenant) isolation**.
- Sensitive fields are classified in code (`SensitiveFieldRegistry`); access is limited by **role** and **organization membership**.
- Where encryption is enabled (`PII_ENCRYPTION_KEY`), selected values are encrypted at rest; lookup uses **hashed tokens** where search is required (e.g. normalized phone).

## Channels (REST, WhatsApp, AI assistant)

- All reads and mutations go through the **same** service/queryset layers; client-supplied `org_id` is **not** trusted—tenant is taken from the authenticated user’s membership.
- AI and WhatsApp paths must **not** bypass RBAC; prompts and tool arguments are treated as **untrusted**; PII is redacted before external LLM calls where applicable.

## Retention and subject rights

- Users may request **export** or **erasure** via `POST /api/v1/privacy/me/export/` and `POST /api/v1/privacy/me/erasure/` (subject to policy completion in services).
- Audit logs are **append-only** for security events; log payloads use allow-listed keys without raw documents or full phone numbers.

## Review

This policy should be reviewed when new models or integrations are added; update `sensitive_registry.py` and serializers in the same change.
