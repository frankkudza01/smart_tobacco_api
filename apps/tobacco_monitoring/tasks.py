"""Celery tasks for AgroMonitoring registration, polling, and WhatsApp alerts."""

from __future__ import annotations

import logging

from celery import shared_task
logger = logging.getLogger(__name__)


@shared_task(bind=True, ignore_result=True)
def register_polygon_with_agromonitoring_task(self, polygon_id: str) -> None:
    from apps.tobacco_monitoring.models import TobaccoFieldPolygon
    from apps.tobacco_monitoring.services.agromonitoring import AgroMonitoringError
    from apps.tobacco_monitoring.services.polygon_registration import register_polygon_with_provider

    polygon = TobaccoFieldPolygon.objects.filter(id=polygon_id).first()
    if not polygon:
        return
    if not polygon.is_active:
        return
    try:
        register_polygon_with_provider(polygon)
    except AgroMonitoringError as exc:
        msg = str(exc)
        if "AGROMONITORING_API_KEY" in msg and (
            "not configured" in msg or "not set" in msg.lower()
        ):
            logger.warning("AgroMonitoring registration skipped polygon=%s: %s", polygon_id, exc)
        else:
            logger.exception("AgroMonitoring registration failed polygon=%s", polygon_id)


@shared_task(bind=True, ignore_result=True)
def poll_all_active_polygons_task(self) -> dict:
    from apps.tobacco_monitoring.models import MonitoringStatus, TobaccoFieldPolygon
    from apps.tobacco_monitoring.services.agromonitoring import agromonitoring_api_configured
    from apps.tobacco_monitoring.services.polling import poll_polygon_imagery

    if not agromonitoring_api_configured():
        logger.debug("poll_all_active_polygons_task skipped: AGROMONITORING_API_KEY not set")
        return {"processed": 0, "errors": 0, "skipped": True, "reason": "api_key_not_configured"}

    qs = TobaccoFieldPolygon.objects.filter(
        is_active=True,
        agromonitoring_poly_id__gt="",
    ).exclude(monitoring_status=MonitoringStatus.ERROR)
    processed = 0
    errors = 0
    for p in qs.iterator(chunk_size=50):
        try:
            poll_polygon_imagery(p)
            processed += 1
        except Exception:
            logger.exception("poll failed polygon=%s", p.id)
            errors += 1
    return {"processed": processed, "errors": errors}


@shared_task(bind=True, ignore_result=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 2})
def poll_polygon_imagery_task(self, polygon_id: str) -> None:
    from apps.tobacco_monitoring.models import TobaccoFieldPolygon
    from apps.tobacco_monitoring.services.agromonitoring import agromonitoring_api_configured
    from apps.tobacco_monitoring.services.polling import poll_polygon_imagery

    if not agromonitoring_api_configured():
        logger.debug("poll_polygon_imagery_task skipped: AGROMONITORING_API_KEY not set polygon=%s", polygon_id)
        return

    p = TobaccoFieldPolygon.objects.filter(id=polygon_id).first()
    if p:
        poll_polygon_imagery(p)


def _recipient_language(user, polygon) -> str:
    from django.conf import settings

    lang = (polygon.default_alert_language or getattr(settings, "DEFAULT_ALERT_LANGUAGE", "en") or "en").lower()
    org_id = getattr(polygon.farm, "organization_id", None)
    if user is None or org_id is None:
        return lang
    try:
        from apps.worldready.models import UserPreference

        pref = (
            UserPreference.objects.filter(user=user, organization_id=org_id)
            .order_by("-updated_at")
            .first()
        )
        if pref and pref.preferred_language:
            lang = str(pref.preferred_language).lower()
    except Exception:
        pass
    return lang if lang in {"en", "sn", "nd"} else "en"


def _localized_message_for_recipient(event, *, lang: str, recipient_kind: str) -> str:
    from apps.tobacco_monitoring.models import CropStressEventType
    from apps.tobacco_monitoring.services.alert_messages import (
        render_moisture_stress_message,
        render_ndvi_drop_message,
    )

    pct_drop = abs(float(event.percentage_change or 0.0))
    if event.event_type == CropStressEventType.MOISTURE_STRESS:
        return render_moisture_stress_message(
            event.polygon,
            moisture_value=float(event.current_ndvi or 0.0),
            drop_pct=pct_drop,
            lang=lang,
            recipient_kind=recipient_kind,
        )
    return render_ndvi_drop_message(
        event.polygon,
        pct_drop=pct_drop,
        lang=lang,
        recipient_kind=recipient_kind,
    )


def _build_alert_recipients(event) -> list[tuple[str, str, object | None]]:
    """Return [(phone, recipient_kind, user_or_none)] for farmer + buyers."""
    from apps.common.enums import UserRole
    from apps.organizations.models import OrganizationMembership

    polygon = event.polygon
    farm = polygon.farm
    recipients: list[tuple[str, str, object | None]] = []
    seen: set[str] = set()

    def _add(phone: str | None, kind: str, user_obj=None):
        raw = (phone or "").strip()
        digits = "".join(c for c in raw if c.isdigit())
        if not digits or digits in seen:
            return
        seen.add(digits)
        recipients.append((raw, kind, user_obj))

    # Preferred explicit polygon phone (often farmer field contact).
    _add(polygon.whatsapp_phone_e164, "farmer", getattr(farm, "owner", None))
    # Farm owner.
    owner = getattr(farm, "owner", None)
    if owner is not None:
        _add(getattr(owner, "phone_number", None), "farmer", owner)

    # Buyers in the same organization.
    org_id = getattr(farm, "organization_id", None)
    if org_id:
        buyers = (
            OrganizationMembership.objects.filter(
                organization_id=org_id,
                is_active=True,
                role=UserRole.BUYER_CONTRACTOR,
                user__is_active=True,
            )
            .select_related("user")
            .order_by("-is_primary", "-created_at")
        )
        for m in buyers:
            _add(getattr(m.user, "phone_number", None), "buyer", m.user)
    return recipients


@shared_task(bind=True, ignore_result=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 3})
def send_crop_stress_whatsapp_task(self, stress_event_id: str) -> None:
    from django.conf import settings

    from apps.tobacco_monitoring.models import (
        AlertDeliveryStatus,
        CropStressEvent,
        WhatsAppDeliveryLog,
    )
    from apps.tobacco_monitoring.services.meta_whatsapp import MetaWhatsAppError, send_text_message

    event = CropStressEvent.objects.select_related("polygon").filter(id=stress_event_id).first()
    if not event:
        return
    recipients = _build_alert_recipients(event)
    if not recipients:
        event.status = AlertDeliveryStatus.FAILED
        event.save(update_fields=["status", "updated_at"])
        WhatsAppDeliveryLog.objects.create(
            stress_event=event,
            to_phone_e164="",
            attempt_number=1,
            status=AlertDeliveryStatus.FAILED,
            error_code="missing_phone_recipients",
            error_body="No farmer/buyer phone recipients available for this polygon.",
        )
        return

    if not settings.META_WHATSAPP_ACCESS_TOKEN:
        logger.warning("Meta WhatsApp not configured; stress event %s — logging skipped send", event.id)
        for phone, _, _ in recipients:
            WhatsAppDeliveryLog.objects.create(
                stress_event=event,
                to_phone_e164=phone,
                attempt_number=1,
                status=AlertDeliveryStatus.FAILED,
                error_code="meta_not_configured",
                error_body="META_WHATSAPP_ACCESS_TOKEN is not set.",
            )
        event.status = AlertDeliveryStatus.FAILED
        event.save(update_fields=["status", "updated_at"])
        return

    event.status = AlertDeliveryStatus.QUEUED
    event.save(update_fields=["status", "updated_at"])
    sent_any = False
    last_error: MetaWhatsAppError | None = None
    for phone, recipient_kind, user_obj in recipients:
        attempt = event.whatsapp_deliveries.filter(to_phone_e164=phone).count() + 1
        lang = _recipient_language(user_obj, event.polygon)
        body = _localized_message_for_recipient(
            event,
            lang=lang,
            recipient_kind=recipient_kind,
        )
        try:
            resp = send_text_message(to_e164=phone, body=body)
            mid = ""
            if isinstance(resp, dict):
                mid = (resp.get("messages") or [{}])[0].get("id", "")
            WhatsAppDeliveryLog.objects.create(
                stress_event=event,
                to_phone_e164=phone,
                attempt_number=attempt,
                status=AlertDeliveryStatus.SENT,
                provider_message_id=str(mid)[:128],
                raw_response=resp if isinstance(resp, dict) else {},
            )
            sent_any = True
        except MetaWhatsAppError as exc:
            last_error = exc
            WhatsAppDeliveryLog.objects.create(
                stress_event=event,
                to_phone_e164=phone,
                attempt_number=attempt,
                status=AlertDeliveryStatus.FAILED,
                error_body=str(exc)[:2000],
            )

    event.status = AlertDeliveryStatus.SENT if sent_any else AlertDeliveryStatus.FAILED
    event.save(update_fields=["status", "updated_at"])
    if (not sent_any) and last_error is not None:
        raise last_error
