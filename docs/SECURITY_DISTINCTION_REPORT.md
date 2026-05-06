# Distinction — automated security regression (summary)

This artifact summarizes **what the automated suite is designed to prove**. Run after migrations:

```bash
cd backend
DJANGO_SETTINGS_MODULE=config.settings.test pytest tests/test_distinction_extensions.py -v
```

## Covered scenarios

1. **Tenant context for preferences** — Users without an organization context cannot read/write `GET/PATCH /api/v1/preferences/me/` (403).
2. **I18n surface** — Authenticated members receive non-empty string maps for `sn` (and other locales) from `GET /api/v1/i18n/strings/`.
3. **Monitoring RBAC** — `SMALLHOLDER_FARMER` receives 403 on `GET /api/v1/monitoring/metrics/`; `REGULATOR_AUDITOR` receives 200.
4. **Dispute analytics RBAC** — Farmers blocked from `GET /api/v1/analytics/disputes/summary/`; auditors succeed with `from`/`to` dates.
5. **Cross-tenant document access** — A document in organization A is not retrievable by a farmer whose membership is only in organization B (404).

## Not exhaustive

Penetration testing, dependency scanning, and production WAF rules are out of scope for this file. Extend `tests/test_distinction_extensions.py` for WhatsApp injection and assistant prompt-injection cases as those layers stabilize.
