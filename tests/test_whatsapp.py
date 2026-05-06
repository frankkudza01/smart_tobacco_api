"""
Test suite for WhatsApp webhook, intent routing, Twilio service, and message logging.
"""
import pytest
from unittest.mock import patch, MagicMock
from django.urls import reverse
from rest_framework import status

from apps.accounts.models import User
from apps.common.enums import UserRole, WhatsAppDirection
from apps.whatsapp.intent_router import route_inbound_message
from apps.whatsapp.models import WhatsAppMessageLog
from apps.whatsapp.twilio_service import MockWhatsAppProvider, send_whatsapp_message


@pytest.fixture
def farmer_wa(db):
    return User.objects.create_user(
        email="wafarmer@test.com", password="pass12345",
        first_name="WhatsApp", last_name="Farmer",
        role=UserRole.SMALLHOLDER_FARMER,
        phone_number="+263771234567",
    )


class TestMockGateway:
    def test_mock_send_message(self):
        gw = MockWhatsAppProvider()
        result = gw.send_message("+263771234567", "Hello test")
        assert result["sid"].startswith("MOCK_")
        assert result["status"] == "sent"

    def test_mock_validate_signature(self):
        gw = MockWhatsAppProvider()
        assert gw.validate_webhook_signature(MagicMock()) is True


@pytest.mark.django_db
class TestSendWhatsAppMessage:
    def test_send_creates_log(self, farmer_wa):
        log = send_whatsapp_message(
            to="+263771234567", body="Test message", user=farmer_wa,
        )
        assert log.direction == WhatsAppDirection.OUTBOUND
        assert log.phone_number == "+263771234567"
        assert log.message_body == "Test message"
        assert WhatsAppMessageLog.objects.count() == 1


@pytest.mark.django_db
class TestIntentRouter:
    def test_help_command(self, farmer_wa):
        reply = route_inbound_message("+263771234567", "help")
        assert "Commands:" in reply
        assert "Zimbabwe" in reply

    def test_hello_command(self, farmer_wa):
        reply = route_inbound_message("+263771234567", "hello")
        assert "WhatsApp" in reply

    def test_settlements_no_data(self, farmer_wa):
        reply = route_inbound_message("+263771234567", "my settlements")
        assert "no settlements" in reply.lower()

    def test_register_existing_user(self, farmer_wa):
        reply = route_inbound_message("+263771234567", "register")
        assert "already registered" in reply.lower()

    def test_register_unknown_user(self):
        reply = route_inbound_message("+263779999999", "register")
        assert "download" in reply.lower()

    def test_unknown_phone(self):
        reply = route_inbound_message("+263779999999", "my settlements")
        assert "not linked" in reply.lower()

    def test_trace_lot_not_found(self, farmer_wa):
        reply = route_inbound_message("+263771234567", "trace lot FAKE-001")
        assert "not found" in reply.lower()


@pytest.mark.django_db
class TestWhatsAppWebhook:
    @patch("apps.whatsapp.views.get_whatsapp_provider")
    @patch("apps.whatsapp.tasks.send_whatsapp_message_task.delay")
    def test_inbound_webhook_logs_message(self, mock_send, mock_gw, api_client, farmer_wa):
        mock_gateway = MagicMock()
        mock_gateway.validate_webhook_signature.return_value = True
        mock_gateway.webhook_expects_json.return_value = False
        mock_gateway.get_media_url.return_value = None
        mock_gw.return_value = mock_gateway

        url = reverse("whatsapp-webhook")
        resp = api_client.post(url, {
            "From": "whatsapp:+263771234567",
            "Body": "help",
            "MessageSid": "SM_test_123",
        })
        assert resp.status_code == 200
        assert WhatsAppMessageLog.objects.filter(
            direction=WhatsAppDirection.INBOUND,
            phone_number="+263771234567",
        ).exists()
        mock_send.assert_called_once()

    @patch("apps.whatsapp.views.get_whatsapp_provider")
    def test_invalid_signature_rejected(self, mock_gw, api_client):
        mock_gateway = MagicMock()
        mock_gateway.validate_webhook_signature.return_value = False
        mock_gw.return_value = mock_gateway

        url = reverse("whatsapp-webhook")
        resp = api_client.post(url, {"From": "whatsapp:+263771234567", "Body": "hi"})
        assert resp.status_code == 403

    @patch("apps.whatsapp.views.get_whatsapp_provider")
    @patch("apps.whatsapp.tasks.send_whatsapp_message_task.delay")
    def test_waapi_json_webhook(self, mock_send, mock_gw, api_client, farmer_wa):
        mock_provider = MagicMock()
        mock_provider.validate_webhook_signature.return_value = True
        mock_provider.webhook_expects_json.return_value = True
        mock_provider.parse_inbound_to_twilio_shape.return_value = {
            "From": "whatsapp:+263771234567",
            "Body": "help",
            "MessageSid": "waapi_msg_1",
        }
        mock_provider.get_media_url.return_value = None
        mock_gw.return_value = mock_provider

        resp = api_client.post(
            "/api/v1/whatsapp/webhook/",
            data={"event": "message"},
            format="json",
        )
        assert resp.status_code == 200
        assert WhatsAppMessageLog.objects.filter(
            direction=WhatsAppDirection.INBOUND,
            phone_number="+263771234567",
        ).exists()
        mock_send.assert_called_once()


@pytest.mark.django_db
class TestDevOTPLogging:
    @patch("apps.whatsapp.tasks.send_otp_via_whatsapp_task.delay")
    def test_otp_logging_in_dev_mode(self, mock_task, api_client, farmer_wa, settings):
        settings.ENABLE_DEV_OTP_LOGGING = True
        url = reverse("auth-request-otp")
        with patch("apps.accounts.otp_service.logger") as mock_logger:
            resp = api_client.post(url, {"phone_number": "+263771234567"})
            assert resp.status_code == status.HTTP_200_OK
            mock_logger.warning.assert_called()
            log_msg = mock_logger.warning.call_args[0][0]
            assert "[DEV OTP]" in log_msg
