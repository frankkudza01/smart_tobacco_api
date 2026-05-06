# Distinction evidence — metrics to collect

Use this checklist to demonstrate production-grade inclusion, privacy, fraud detection, ML lifecycle, and dispute governance.

## UX and inclusion (Extension A)

| Metric | Source | Notes |
|--------|--------|--------|
| Task completion rate | `TaskCompletionLog` (`channel`, `task_name`, `success`) | Compare Flutter vs WhatsApp; segment by role. |
| Time-to-complete | `started_at` / `completed_at` | Median and p95 per task. |
| Support volume | `SupportRequestLog` | By `request_type` and channel. |
| SUS score | `SusSurveyResponse.scores_json` | Standard System Usability Scale aggregation. |
| Language mix | `UserPreference.preferred_language` | en / sn / nd adoption. |

**APIs:** `GET /api/v1/analytics/ux/tasks/`, preference and i18n endpoints under `/api/v1/`.

## Privacy (Extension B)

| Metric | Source | Notes |
|--------|--------|--------|
| Encryption coverage | Fields listed in `sensitive_registry` + ciphertext presence | Spot-check in non-prod only. |
| Export/erasure SLA | `DataSubjectRequest.status` timestamps | Time to `completed`. |
| Leakage regression | `tests/test_distinction_extensions.py` + future security suite | Must stay green in CI. |

## Documents and near-duplicates (Extension C)

| Metric | Source | Notes |
|--------|--------|--------|
| Exact verify rate | Document verify endpoint + `Document.verification_state` | True/false positive at hash level. |
| Near-duplicate precision/recall | Anomaly labels + `GET .../analytics/anomalies/duplicates/export-labels/` | Confirmed vs false positive counts. |
| Reviewer throughput | `POST .../anomalies/{id}/label/` volume | Queue depth over time. |

## Model monitoring (Extension D)

| Metric | Source | Notes |
|--------|--------|--------|
| MAPE / AUROC trends | `DailyMetrics` | `mape_yield`, `mape_price`, `auroc_anomaly`, duplicate precision/recall. |
| Drift events | `DriftMetrics.triggered`, `reason` | PSI/KS-style JSON in `feature_drift_json`. |
| Retrain triggers | Audit events + Celery task logs | When MAPE or drift thresholds breach policy. |

**APIs:** `GET /api/v1/monitoring/metrics/`, `/monitoring/drift/`, `/monitoring/retrain/history/`.

## Disputes (Extension E)

| Metric | Source | Notes |
|--------|--------|--------|
| Median / p95 resolution time | `Dispute.created_at` vs `resolved_at` | Exposed via `GET /api/v1/analytics/disputes/summary/`. |
| Volume by status | Same summary endpoint | Trends by day. |
| Case packet usage | Access logs / audit for `case-packet` downloads | Optional deep link analytics. |

## Reporting

Export aggregates periodically (Power BI, Metabase, or CSV) using the analytics endpoints above. Keep exports **aggregated** or **redacted** for non-admin audiences.
