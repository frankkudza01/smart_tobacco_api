# Tobacco satellite monitoring and WhatsApp alerts

This module (`apps.tobacco_monitoring`) adds Zimbabwe-focused satellite monitoring (AgroMonitoring), NDVI/soil moisture time series, rule-based crop stress detection, and Meta WhatsApp Cloud API alerts. Field boundaries are stored as **GeoJSON** in PostgreSQL (`JSONField`). Enabling **PostGIS + GeoDjango** later is supported by migrating `geometry_geojson` into a geometry column without changing API payloads.

## Architecture

- **Models**: `TobaccoFieldPolygon`, `SatelliteImageryRecord`, `PolygonObservation`, `CropStressEvent`, `WhatsAppDeliveryLog`, `PlantingVerificationRecord`.
- **Services**: `services/agromonitoring.py` (HTTP + retries), `services/polling.py` (idempotent ingest), `services/anomaly.py` (NDVI drop rule), `services/planting_verification.py` (heuristic emergence), `services/yield_proxy.py` (buyer/regional rollups), `services/meta_whatsapp.py` (outbound messages).
- **Celery**: thin tasks in `tasks.py` delegate to services.
- **API**: `/api/v1/tobacco-monitoring/` — see `urls.py`.
- **Access**: mirrors `apps.farms` — farmers see own farms’ polygons; buyers see polygons on farms linked to their `OrganizationMembership` orgs; admins/auditors see all.

## Environment variables

| Variable | Purpose |
|----------|---------|
| `AGROMONITORING_API_KEY` | AgroMonitoring `appid` |
| `AGROMONITORING_BASE_URL` | Default `http://api.agromonitoring.com/agro/1.0` |
| `AGROMONITORING_TIMEOUT_SECONDS` | HTTP timeout |
| `AGROMONITORING_MAX_RETRIES` | Retries with backoff (client helper) |
| `META_WHATSAPP_ACCESS_TOKEN` | Meta Graph API token |
| `META_WHATSAPP_PHONE_NUMBER_ID` | WhatsApp phone number id |
| `META_WHATSAPP_BASE_URL` | Default `https://graph.facebook.com/v21.0` |
| `META_WHATSAPP_TIMEOUT_SECONDS` / `META_WHATSAPP_MAX_RETRIES` | Outbound reliability |
| `SATELLITE_POLL_CRON` | Documentary default; schedules live in **django-celery-beat** DB |
| `NDVI_STRESS_DROP_THRESHOLD` | Percent drop (e.g. `10`) triggering stress in vegetative stage |
| `DEFAULT_ALERT_LANGUAGE` | e.g. `en` (templates structured for sn/nd later) |
| `DEFAULT_COUNTRY_CODE` | Phone parse region, default `ZW` |
| `TOBACCO_DEFAULT_CROP` | Default crop type string |
| `TOBACCO_SUPPORTED_PROVINCES` | CSV list for validation |
| `TOBACCO_YIELD_PROXY_COEFFICIENT` | Scalar in yield proxy tonnes estimate |
| `TOBACCO_PLANTING_NDVI_THRESHOLD` | NDVI proxy for auto planting status |

## Celery beat

Migration **`tobacco_monitoring.0002_satellite_poll_periodic_task`** creates a **django-celery-beat** entry (idempotent):

- **Name**: `tobacco-monitoring-satellite-poll`
- **Task**: `apps.tobacco_monitoring.tasks.poll_all_active_polygons_task`
- **Schedule**: daily at **06:00** `Africa/Harare` (aligned with `CELERY_TIMEZONE` / Zimbabwe operations)

To recreate or repair the schedule after DB restores:

```bash
python manage.py setup_tobacco_monitoring_beat
```

You can still change cadence or disable the task in **Django Admin → Periodic tasks**. `SATELLITE_POLL_CRON` in settings remains a **documentary default** (decouple string); the live schedule is the beat row above unless you add more tasks.

### Manual poll (single field)

`POST /api/v1/tobacco-monitoring/polygons/{polygon_id}/poll/` queues `poll_polygon_imagery_task` (HTTP **202**) for anyone who can already view that polygon. Requires `agromonitoring_poly_id` set.

## Flows

1. **Polygon registration**: Farmer `POST /tobacco-monitoring/polygons/`. On commit, `register_polygon_with_agromonitoring_task` calls AgroMonitoring `POST /polygons`, stores `agromonitoring_poly_id` and optional area from API.
2. **Polling**: `poll_polygon_imagery` loads `ndvi/history` and `soil/history`, upserts `PolygonObservation` rows unique on `(polygon, observation_date, metric_type)`, and `SatelliteImageryRecord` by `idempotency_key`.
3. **Anomaly**: In vegetative stage, if NDVI drops by ≥ `NDVI_STRESS_DROP_THRESHOLD` % vs prior observation, creates `CropStressEvent` with dedupe key `{polygon}:{date}:ndvi_drop`, then `send_crop_stress_whatsapp_task` on commit.
4. **WhatsApp**: Meta Cloud API text send; logs in `WhatsAppDeliveryLog`. Missing phone marks event failed without raising in the monitoring loop path.
5. **Planting verification**: Auto record from mean NDVI over recent window; buyers can add manual `PlantingVerificationRecord` via API.
6. **Regional reporting**: `GET .../summaries/regional/` returns `regions` keyed by supported province. **Buyers** only see polygons (and stress events) in their **organization scope**; **admins and auditors** see national totals for those provinces.

## Example payloads

**Create polygon** `POST /api/v1/tobacco-monitoring/polygons/`

```json
{
  "farm": "<uuid>",
  "field_name": "Block 3",
  "province": "Mashonaland Central",
  "district": "Bindura",
  "season": "2025",
  "growth_stage": "vegetative",
  "geometry_geojson": {
    "type": "Polygon",
    "coordinates": [[[31.32, -17.35], [31.33, -17.35], [31.33, -17.34], [31.32, -17.34], [31.32, -17.35]]]
  },
  "whatsapp_phone_e164": "+263771234567"
}
```

**Buyer summary** `GET /api/v1/tobacco-monitoring/summaries/buyer/?season=2025`

```json
{
  "total_contracted_polygons": 42,
  "total_monitored_hectares": 610.5,
  "planted_verified_hectares_proxy": 520.0,
  "stress_event_count": 7,
  "expected_yield_proxy_tonnes": 12.345,
  "yield_proxy_coefficient": 0.25,
  "by_province": { "Mashonaland Central": { "polygons": 20, "hectares": 300.0, "stress_events": 3 } },
  "planting_verification_breakdown": { "established": 30, "not_detected": 5 }
}
```

## Flutter client

`lib/features/tobacco_monitoring/data/tobacco_monitoring_repository.dart` exposes list/create polygon, observations, latest status, queue poll, stress events, buyer + regional summaries, and planting verifications. Use `tobaccoMonitoringRepositoryProvider` with your existing `dioProvider` (JWT interceptors apply automatically).
