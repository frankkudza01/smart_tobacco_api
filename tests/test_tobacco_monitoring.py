import pytest
from django.test.utils import captureOnCommitCallbacks
from django.urls import reverse
from rest_framework import status
from unittest.mock import MagicMock, patch

from apps.tobacco_monitoring.models import (
    CropStressEvent,
    GrowthStage,
    MetricType,
    MonitoringStatus,
    PolygonObservation,
    TobaccoFieldPolygon,
)
from apps.tobacco_monitoring.services.anomaly import evaluate_ndvi_drop_for_polygon
from apps.tobacco_monitoring.services.polling import poll_polygon_imagery
from apps.tobacco_monitoring.validators import validate_geojson_polygon_payload, validate_supported_province
from apps.organizations.models import OrganizationMembership
from apps.common.enums import UserRole
from django.core.exceptions import ValidationError

from tests.factories import FarmFactory, FarmerFactory


def _sample_polygon_geojson():
    return {
        "type": "Polygon",
        "coordinates": [
            [
                [31.32, -17.35],
                [31.33, -17.35],
                [31.33, -17.34],
                [31.32, -17.34],
                [31.32, -17.35],
            ]
        ],
    }


@pytest.mark.django_db
class TestTobaccoValidators:
    def test_geojson_requires_closed_ring(self):
        bad = {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1]]]}
        with pytest.raises(ValidationError):
            validate_geojson_polygon_payload(bad)

    def test_geojson_polygon_ok(self):
        g = _sample_polygon_geojson()
        assert validate_geojson_polygon_payload(g)["type"] == "Polygon"

    def test_province_must_be_supported(self):
        with pytest.raises(ValidationError):
            validate_supported_province("Harare")
        validate_supported_province("Mashonaland Central")


@pytest.mark.django_db
class TestTobaccoPolygonAPI:
    def test_farmer_can_create_polygon(self, authenticated_farmer_client, farm):
        url = reverse("tobacco-polygon-list")
        data = {
            "farm": str(farm.id),
            "field_name": "Tobacco A",
            "province": "Mashonaland Central",
            "district": "Bindura",
            "season": "2025",
            "growth_stage": GrowthStage.VEGETATIVE,
            "geometry_geojson": _sample_polygon_geojson(),
            "whatsapp_phone_e164": "+263771234567",
        }
        with patch(
            "apps.tobacco_monitoring.tasks.register_polygon_with_agromonitoring_task.delay",
            MagicMock(),
        ):
            response = authenticated_farmer_client.post(url, data, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert TobaccoFieldPolygon.objects.filter(farm=farm).count() == 1

    def test_buyer_cannot_create_polygon(self, authenticated_buyer_client, farm, organization):
        OrganizationMembership.objects.get_or_create(
            user=farm.owner,
            organization=organization,
            defaults={"role": UserRole.SMALLHOLDER_FARMER, "is_primary": True},
        )
        farm.organization = organization
        farm.save()
        url = reverse("tobacco-polygon-list")
        data = {
            "farm": str(farm.id),
            "field_name": "X",
            "province": "Mashonaland Central",
            "geometry_geojson": _sample_polygon_geojson(),
        }
        response = authenticated_buyer_client.post(url, data, format="json")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_buyer_lists_polygons_for_org_farms(self, authenticated_buyer_client, farm, buyer_user):
        m = buyer_user.memberships.select_related("organization").first()
        assert m is not None
        farm.organization = m.organization
        farm.save()
        TobaccoFieldPolygon.objects.create(
            farm=farm,
            field_name="F1",
            province="Mashonaland Central",
            geometry_geojson=_sample_polygon_geojson(),
        )
        url = reverse("tobacco-polygon-list")
        response = authenticated_buyer_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1


@pytest.mark.django_db
class TestAgroMonitoringRegistration:
    def test_register_persists_poly_id(self, farm):
        poly = TobaccoFieldPolygon.objects.create(
            farm=farm,
            field_name="Reg",
            province="Mashonaland Central",
            geometry_geojson=_sample_polygon_geojson(),
            monitoring_status=MonitoringStatus.PENDING,
        )
        fake = MagicMock()
        fake.create_polygon.return_value = {
            "id": "aabbccddeeff001122334455",
            "area": 12.5,
        }

        with patch(
            "apps.tobacco_monitoring.services.polygon_registration.AgroMonitoringClient",
            return_value=fake,
        ):
            from apps.tobacco_monitoring.services.polygon_registration import (
                register_polygon_with_provider,
            )

            register_polygon_with_provider(poly)
        poly.refresh_from_db()
        assert poly.agromonitoring_poly_id == "aabbccddeeff001122334455"
        assert poly.monitoring_status == MonitoringStatus.ACTIVE


@pytest.mark.django_db
class TestPollingAndAnomaly:
    def test_poll_idempotent_ndvi(self, farm):
        poly = TobaccoFieldPolygon.objects.create(
            farm=farm,
            field_name="P",
            province="Mashonaland Central",
            geometry_geojson=_sample_polygon_geojson(),
            agromonitoring_poly_id="aabbccddeeff001122334455",
            growth_stage=GrowthStage.VEGETATIVE,
        )
        ndvi_rows = [
            {"dt": 1700000000, "source": "s2", "cl": 0.1, "data": {"mean": 0.5}},
            {"dt": 1700600000, "source": "s2", "cl": 0.1, "data": {"mean": 0.35}},
        ]
        fake = MagicMock()
        fake.ndvi_history.return_value = ndvi_rows
        fake.soil_history.return_value = []

        with patch(
            "apps.tobacco_monitoring.services.polling.AgroMonitoringClient",
            return_value=fake,
        ):
            poll_polygon_imagery(poly)
            poll_polygon_imagery(poly)

        assert PolygonObservation.objects.filter(polygon=poly, metric_type=MetricType.NDVI).count() == 2

    def test_anomaly_creates_stress_event(self, farm, settings):
        settings.NDVI_STRESS_DROP_THRESHOLD = 10.0
        poly = TobaccoFieldPolygon.objects.create(
            farm=farm,
            field_name="Stress",
            province="Mashonaland Central",
            geometry_geojson=_sample_polygon_geojson(),
            agromonitoring_poly_id="x",
            growth_stage=GrowthStage.VEGETATIVE,
        )
        PolygonObservation.objects.create(
            polygon=poly,
            observation_date="2025-01-01",
            metric_type=MetricType.NDVI,
            metric_value=0.5,
        )
        PolygonObservation.objects.create(
            polygon=poly,
            observation_date="2025-01-10",
            metric_type=MetricType.NDVI,
            metric_value=0.35,
        )
        with captureOnCommitCallbacks(execute=True), patch(
            "apps.tobacco_monitoring.tasks.send_crop_stress_whatsapp_task.delay",
            MagicMock(),
        ):
            ev = evaluate_ndvi_drop_for_polygon(poly)
        assert ev is not None
        assert CropStressEvent.objects.filter(id=ev.id).count() == 1


@pytest.mark.django_db
class TestWhatsAppDispatch:
    def test_send_skips_without_phone(self, farm):
        from apps.tobacco_monitoring.models import AlertDeliveryStatus
        from apps.tobacco_monitoring.tasks import send_crop_stress_whatsapp_task

        poly = TobaccoFieldPolygon.objects.create(
            farm=farm,
            field_name="No phone",
            province="Mashonaland Central",
            geometry_geojson=_sample_polygon_geojson(),
            whatsapp_phone_e164="",
        )
        ev = CropStressEvent.objects.create(
            polygon=poly,
            event_type="ndvi_drop",
            severity="medium",
            observation_date="2025-02-01",
            dedupe_key="u1",
            localized_message="test",
            raw_reason="r",
            status=AlertDeliveryStatus.PENDING,
        )
        send_crop_stress_whatsapp_task.apply(args=[str(ev.id)])
        ev.refresh_from_db()
        assert ev.status == AlertDeliveryStatus.FAILED

    def test_send_meta_success(self, farm, settings):
        settings.META_WHATSAPP_ACCESS_TOKEN = "tok"
        settings.META_WHATSAPP_PHONE_NUMBER_ID = "123"
        from apps.tobacco_monitoring.models import AlertDeliveryStatus
        from apps.tobacco_monitoring.tasks import send_crop_stress_whatsapp_task

        poly = TobaccoFieldPolygon.objects.create(
            farm=farm,
            field_name="With phone",
            province="Mashonaland Central",
            geometry_geojson=_sample_polygon_geojson(),
            whatsapp_phone_e164="+263771111111",
        )
        ev = CropStressEvent.objects.create(
            polygon=poly,
            event_type="ndvi_drop",
            severity="medium",
            observation_date="2025-02-02",
            dedupe_key="u2",
            localized_message="Hello",
            raw_reason="r",
            status=AlertDeliveryStatus.PENDING,
        )
        with patch(
            "apps.tobacco_monitoring.services.meta_whatsapp.send_text_message",
            return_value={"messages": [{"id": "mid"}]},
        ):
            send_crop_stress_whatsapp_task.apply(args=[str(ev.id)])
        ev.refresh_from_db()
        assert ev.status == AlertDeliveryStatus.SENT


@pytest.mark.django_db
class TestBuyerSummary:
    def test_buyer_summary_endpoint(self, authenticated_buyer_client, farm, buyer_user):
        m = buyer_user.memberships.select_related("organization").first()
        assert m is not None
        farm.organization = m.organization
        farm.save()
        TobaccoFieldPolygon.objects.create(
            farm=farm,
            field_name="B1",
            province="Mashonaland Central",
            geometry_geojson=_sample_polygon_geojson(),
            area_hectares=10,
            agromonitoring_poly_id="p",
        )
        url = reverse("tobacco-summary-buyer")
        response = authenticated_buyer_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["total_contracted_polygons"] == 1
        assert response.data["total_monitored_hectares"] == 10.0
        assert "planting_verification_breakdown" in response.data


@pytest.mark.django_db
class TestRegionalSummaryScope:
    def test_buyer_regional_excludes_other_farms(self, authenticated_buyer_client, farm, buyer_user):
        m = buyer_user.memberships.select_related("organization").first()
        assert m is not None
        farm.organization = m.organization
        farm.save()
        geo = _sample_polygon_geojson()
        TobaccoFieldPolygon.objects.create(
            farm=farm,
            field_name="Linked",
            province="Mashonaland Central",
            geometry_geojson=geo,
            agromonitoring_poly_id="linked",
        )
        other_farm = FarmFactory()
        TobaccoFieldPolygon.objects.create(
            farm=other_farm,
            field_name="Unlinked",
            province="Mashonaland Central",
            geometry_geojson=geo,
            agromonitoring_poly_id="unlinked",
        )
        url = reverse("tobacco-summary-regional")
        response = authenticated_buyer_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        mc = response.data["regions"]["Mashonaland Central"]
        assert mc["polygon_count"] == 1


@pytest.mark.django_db
class TestPolygonPollEndpoint:
    def test_poll_returns_202(self, authenticated_farmer_client, farm):
        poly = TobaccoFieldPolygon.objects.create(
            farm=farm,
            field_name="Poll me",
            province="Mashonaland Central",
            geometry_geojson=_sample_polygon_geojson(),
            agromonitoring_poly_id="aabbccddeeff001122334466",
        )
        url = reverse("tobacco-polygon-poll", kwargs={"polygon_pk": poly.id})
        with patch(
            "apps.tobacco_monitoring.views.poll_polygon_imagery_task.delay",
            MagicMock(),
        ) as m_delay:
            response = authenticated_farmer_client.post(url)
        assert response.status_code == status.HTTP_202_ACCEPTED
        assert response.data.get("status") == "queued"
        m_delay.assert_called_once()

    def test_poll_sync_registers_when_missing_provider_id(
        self, authenticated_farmer_client, farm
    ):
        poly = TobaccoFieldPolygon.objects.create(
            farm=farm,
            field_name="No provider",
            province="Mashonaland Central",
            geometry_geojson=_sample_polygon_geojson(),
            agromonitoring_poly_id="",
        )
        url = reverse("tobacco-polygon-poll", kwargs={"polygon_pk": poly.id})

        def _fake_register(p):
            TobaccoFieldPolygon.objects.filter(id=p.id).update(
                agromonitoring_poly_id="bbccddeeffaa001122334455",
                monitoring_status=MonitoringStatus.ACTIVE,
            )

        with patch(
            "apps.tobacco_monitoring.views.register_polygon_with_provider",
            side_effect=_fake_register,
        ):
            with patch(
                "apps.tobacco_monitoring.views.poll_polygon_imagery_task.delay",
                MagicMock(),
            ) as m_delay:
                response = authenticated_farmer_client.post(url)
        assert response.status_code == status.HTTP_202_ACCEPTED
        assert response.data.get("registered_with_provider_now") is True
        assert response.data.get("status") == "queued"
        poly.refresh_from_db()
        assert poly.agromonitoring_poly_id == "bbccddeeffaa001122334455"
        m_delay.assert_called_once()


@pytest.mark.django_db
class TestMetaWhatsAppSkipped:
    def test_logs_when_meta_not_configured(self, farm, settings):
        settings.META_WHATSAPP_ACCESS_TOKEN = ""
        from apps.tobacco_monitoring.models import AlertDeliveryStatus, WhatsAppDeliveryLog
        from apps.tobacco_monitoring.tasks import send_crop_stress_whatsapp_task

        poly = TobaccoFieldPolygon.objects.create(
            farm=farm,
            field_name="W",
            province="Mashonaland Central",
            geometry_geojson=_sample_polygon_geojson(),
            whatsapp_phone_e164="+263772222222",
        )
        ev = CropStressEvent.objects.create(
            polygon=poly,
            event_type="ndvi_drop",
            severity="low",
            observation_date="2025-03-01",
            dedupe_key="u-meta-skip",
            localized_message="m",
            raw_reason="r",
            status=AlertDeliveryStatus.PENDING,
        )
        send_crop_stress_whatsapp_task.apply(args=[str(ev.id)])
        ev.refresh_from_db()
        assert ev.status == AlertDeliveryStatus.PENDING
        log = WhatsAppDeliveryLog.objects.filter(stress_event=ev).latest("created_at")
        assert log.error_code == "meta_not_configured"
