"""
Comprehensive tests for WhatsApp operational channel:
- Contact/session management
- Farmer onboarding workflow
- Farm registration workflow
- Lot creation and event capture
- Document upload workflow
- Dispute creation workflow
- Buyer grading, sale, settlement workflows
- Intent routing (deterministic + role-aware)
- Webhook view
- Delivery status callback
- Media handling
- Notification service
"""
import pytest
from decimal import Decimal
from unittest.mock import patch, MagicMock

from django.test import RequestFactory
from django.utils import timezone

from apps.common.enums import (
    ConversationType,
    DisputeStatus,
    LotStatus,
    SettlementStatus,
    TraceEventType,
    UserRole,
    WhatsAppDeliveryStatus,
    WhatsAppDirection,
)
from apps.whatsapp.models import (
    WhatsAppContact,
    WhatsAppConversation,
    WhatsAppIntentLog,
    WhatsAppMessageLog,
    WhatsAppTemplateLog,
)
from apps.whatsapp.session_service import (
    advance_state,
    end_conversation,
    get_active_conversation,
    get_or_create_contact,
    start_conversation,
)
from apps.whatsapp.intent_router import detect_intent, route_message
from apps.whatsapp.twilio_service import MockWhatsAppProvider, send_whatsapp_message
from tests.factories import (
    BuyerFactory,
    FarmerFactory,
    FarmFactory,
    LotFactory,
    SaleFactory,
    SeasonFactory,
    SettlementFactory,
    TraceEventFactory,
)


# ─────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────

@pytest.fixture
def farmer(db):
    user = FarmerFactory(phone_number="+263771234567")
    return user


@pytest.fixture
def buyer(db):
    user = BuyerFactory(phone_number="+263772345678")
    return user


@pytest.fixture
def farmer_contact(db, farmer):
    return WhatsAppContact.objects.create(
        phone_number="+263771234567",
        user=farmer,
        display_name=farmer.full_name,
        linked_role=UserRole.SMALLHOLDER_FARMER,
        is_verified=True,
        consent_given=True,
    )


@pytest.fixture
def buyer_contact(db, buyer):
    return WhatsAppContact.objects.create(
        phone_number="+263772345678",
        user=buyer,
        display_name=buyer.full_name,
        linked_role=UserRole.BUYER_CONTRACTOR,
        is_verified=True,
        consent_given=True,
    )


@pytest.fixture
def unlinked_contact(db):
    return WhatsAppContact.objects.create(
        phone_number="+263779999999",
        display_name="+263779999999",
    )


# ─────────────────────────────────────────────────────
# Session service tests
# ─────────────────────────────────────────────────────

@pytest.mark.django_db
class TestSessionService:

    def test_get_or_create_contact_new(self):
        contact = get_or_create_contact("+263771111111")
        assert contact.phone_number == "+263771111111"
        assert contact.user is None

    def test_get_or_create_contact_existing_user(self, farmer):
        contact = get_or_create_contact("+263771234567")
        assert contact.user == farmer
        assert contact.is_verified is True

    def test_start_conversation(self, farmer_contact):
        conv = start_conversation(farmer_contact, ConversationType.FARM_REGISTRATION)
        assert conv.is_active is True
        assert conv.current_state == "INIT"
        assert conv.conversation_type == ConversationType.FARM_REGISTRATION

    def test_start_conversation_deactivates_old(self, farmer_contact):
        old = start_conversation(farmer_contact, ConversationType.GENERAL)
        new = start_conversation(farmer_contact, ConversationType.FARM_REGISTRATION)
        old.refresh_from_db()
        assert old.is_active is False
        assert new.is_active is True

    def test_advance_state(self, farmer_contact):
        conv = start_conversation(farmer_contact)
        advance_state(conv, "ASK_NAME", {"farm_name": "Test"})
        conv.refresh_from_db()
        assert conv.current_state == "ASK_NAME"
        assert conv.state_data["farm_name"] == "Test"

    def test_expired_conversation(self, farmer_contact):
        conv = start_conversation(farmer_contact)
        conv.expires_at = timezone.now() - timezone.timedelta(minutes=5)
        conv.save()
        assert get_active_conversation(farmer_contact) is None

    def test_end_conversation(self, farmer_contact):
        conv = start_conversation(farmer_contact)
        end_conversation(conv)
        conv.refresh_from_db()
        assert conv.is_active is False


# ─────────────────────────────────────────────────────
# Intent detection tests
# ─────────────────────────────────────────────────────

@pytest.mark.django_db
class TestIntentDetection:

    def test_help_intent(self, farmer_contact):
        result = detect_intent("help", farmer_contact)
        assert result["type"] == "help"

    def test_cancel_intent(self, farmer_contact):
        result = detect_intent("cancel", farmer_contact)
        assert result["type"] == "cancel"

    def test_farmer_register_intent(self, farmer_contact):
        result = detect_intent("register farm", farmer_contact)
        assert result["type"] == "workflow"
        assert result["conv_type"] == ConversationType.FARM_REGISTRATION

    def test_farmer_create_lot_intent(self, farmer_contact):
        result = detect_intent("create lot", farmer_contact)
        assert result["type"] == "workflow"
        assert result["conv_type"] == ConversationType.LOT_CREATION

    def test_buyer_grading_intent(self, buyer_contact):
        result = detect_intent("record grading", buyer_contact)
        assert result["type"] == "workflow"
        assert result["conv_type"] == ConversationType.GRADING

    def test_settlement_lookup(self, farmer_contact):
        result = detect_intent("my settlements", farmer_contact)
        assert result["type"] == "lookup"
        assert result["intent"] == "lookup_settlements"

    def test_trace_lot_lookup(self, farmer_contact):
        result = detect_intent("trace lot LOT-001", farmer_contact)
        assert result["type"] == "lookup"
        assert result["intent"] == "lookup_trace_lot"
        assert result["match_groups"] == ("LOT-001",)

    def test_ai_fallback(self, farmer_contact):
        result = detect_intent("what is the best price for my tobacco", farmer_contact)
        assert result["type"] == "ai_query"
        assert result["confidence"] < 0.5

    def test_explicit_ai_query(self, farmer_contact):
        result = detect_intent("talk to assistant about my lots", farmer_contact)
        assert result["type"] == "ai_query"
        assert result["confidence"] >= 0.9

    def test_dispute_intent(self, farmer_contact):
        result = detect_intent("raise dispute", farmer_contact)
        assert result["type"] == "workflow"
        assert result["conv_type"] == ConversationType.DISPUTE_CREATION


# ─────────────────────────────────────────────────────
# Message routing tests
# ─────────────────────────────────────────────────────

@pytest.mark.django_db
class TestRouteMessage:

    @patch("apps.whatsapp.intent_router._handle_ai_query")
    def test_help_returns_menu(self, mock_ai, farmer_contact):
        reply = route_message(farmer_contact, "help")
        assert "Zimbabwe Tobacco Platform" in reply
        assert "REGISTER FARM" in reply

    def test_help_for_unlinked_contact(self, unlinked_contact):
        reply = route_message(unlinked_contact, "help")
        assert "REGISTER" in reply

    def test_cancel_ends_active_conversation(self, farmer_contact):
        start_conversation(farmer_contact, ConversationType.FARM_REGISTRATION)
        reply = route_message(farmer_contact, "cancel")
        assert "Zimbabwe Tobacco Platform" in reply
        assert get_active_conversation(farmer_contact) is None

    def test_settlement_lookup(self, farmer_contact, farmer):
        sale = SaleFactory(lot__farm__owner=farmer)
        SettlementFactory(sale=sale, farmer=farmer)
        reply = route_message(farmer_contact, "my settlements")
        assert "settlements" in reply.lower()

    def test_lot_lookup_not_found(self, farmer_contact):
        reply = route_message(farmer_contact, "trace lot UNKNOWN-LOT")
        assert "not found" in reply.lower()


# ─────────────────────────────────────────────────────
# Farmer onboarding workflow tests
# ─────────────────────────────────────────────────────

@pytest.mark.django_db
class TestFarmerOnboardingWorkflow:

    @patch("apps.whatsapp.workflows.farmer_onboarding.otp_service.generate_otp")
    @patch("apps.whatsapp.tasks.send_otp_via_whatsapp_task.delay")
    def test_onboarding_starts_with_otp(self, mock_otp_task, mock_gen, unlinked_contact):
        mock_gen.return_value = ("123456", None)
        reply = route_message(unlinked_contact, "register")
        assert "verification code" in reply.lower()
        mock_otp_task.assert_called_once()

    @patch("apps.whatsapp.workflows.farmer_onboarding.otp_service.generate_otp")
    @patch("apps.whatsapp.workflows.farmer_onboarding.otp_service.verify_otp")
    @patch("apps.whatsapp.tasks.send_otp_via_whatsapp_task.delay")
    def test_onboarding_full_flow(self, mock_otp_task, mock_verify, mock_gen, unlinked_contact):
        mock_gen.return_value = ("123456", None)
        mock_verify.return_value = (True, "")

        route_message(unlinked_contact, "register")
        reply = route_message(unlinked_contact, "123456")
        assert "full name" in reply.lower()

        reply = route_message(unlinked_contact, "John Moyo")
        assert "national id" in reply.lower()

        reply = route_message(unlinked_contact, "63-123456-A-77")
        assert "district" in reply.lower()

        reply = route_message(unlinked_contact, "Mvurwi")
        assert "language" in reply.lower()

        reply = route_message(unlinked_contact, "1")
        assert "confirm" in reply.lower()
        assert "John" in reply

        reply = route_message(unlinked_contact, "yes")
        assert "welcome" in reply.lower()

        unlinked_contact.refresh_from_db()
        assert unlinked_contact.user is not None
        assert unlinked_contact.linked_role == UserRole.SMALLHOLDER_FARMER


# ─────────────────────────────────────────────────────
# Farm registration workflow tests
# ─────────────────────────────────────────────────────

@pytest.mark.django_db
class TestFarmRegistrationWorkflow:

    def test_farm_reg_requires_user(self, unlinked_contact):
        reply = route_message(unlinked_contact, "register farm")
        assert "registered first" in reply.lower()

    def test_farm_reg_full_flow(self, farmer_contact):
        reply = route_message(farmer_contact, "register farm")
        assert "farm name" in reply.lower()

        reply = route_message(farmer_contact, "Green Valley Farm")
        assert "district" in reply.lower()

        reply = route_message(farmer_contact, "Mvurwi")
        assert "location" in reply.lower()

        reply = route_message(farmer_contact, "Near Mvurwi town center")
        assert "hectares" in reply.lower()

        reply = route_message(farmer_contact, "5.5")
        assert "variety" in reply.lower()

        reply = route_message(farmer_contact, "1")
        assert "season" in reply.lower()

        reply = route_message(farmer_contact, "2")
        assert "confirm" in reply.lower()

        reply = route_message(farmer_contact, "yes")
        assert "registered successfully" in reply.lower()

        from apps.farms.models import Farm
        assert Farm.objects.filter(name="Green Valley Farm").exists()


# ─────────────────────────────────────────────────────
# Lot creation workflow tests
# ─────────────────────────────────────────────────────

@pytest.mark.django_db
class TestLotCreationWorkflow:

    def test_lot_creation_no_seasons(self, farmer_contact):
        reply = route_message(farmer_contact, "create lot")
        assert "no seasons" in reply.lower()

    def test_lot_creation_full_flow(self, farmer_contact, farmer):
        farm = FarmFactory(owner=farmer)
        SeasonFactory(farm=farm)

        reply = route_message(farmer_contact, "create lot")
        assert "select a season" in reply.lower()

        reply = route_message(farmer_contact, "1")
        assert "lot number" in reply.lower()

        reply = route_message(farmer_contact, "LOT-WA-001")
        assert "description" in reply.lower()

        reply = route_message(farmer_contact, "Test lot via WhatsApp")
        assert "weight" in reply.lower()

        reply = route_message(farmer_contact, "250")
        assert "confirm" in reply.lower()

        reply = route_message(farmer_contact, "yes")
        assert "created" in reply.lower()

        from apps.lots.models import Lot
        assert Lot.objects.filter(lot_number="LOT-WA-001").exists()


# ─────────────────────────────────────────────────────
# Event capture workflow tests
# ─────────────────────────────────────────────────────

@pytest.mark.django_db
class TestEventCaptureWorkflow:

    @patch("apps.blockchain.tasks.anchor_event_hash.delay")
    def test_event_capture_full_flow(self, mock_anchor, farmer_contact, farmer):
        farm = FarmFactory(owner=farmer)
        season = SeasonFactory(farm=farm)
        LotFactory(season=season, created_by=farmer)

        reply = route_message(farmer_contact, "add event")
        assert "select a lot" in reply.lower()

        reply = route_message(farmer_contact, "1")
        assert "type of event" in reply.lower()

        reply = route_message(farmer_contact, "1")
        assert "notes" in reply.lower()

        reply = route_message(farmer_contact, "Planted Virginia tobacco")
        assert "confirm" in reply.lower()

        reply = route_message(farmer_contact, "yes")
        assert "recorded" in reply.lower()
        mock_anchor.assert_called_once()


# ─────────────────────────────────────────────────────
# Dispute creation workflow tests
# ─────────────────────────────────────────────────────

@pytest.mark.django_db
class TestDisputeWorkflow:

    def test_dispute_no_sales(self, farmer_contact):
        reply = route_message(farmer_contact, "raise dispute")
        assert "no sales" in reply.lower()

    def test_dispute_full_flow(self, farmer_contact, farmer):
        sale = SaleFactory(lot__farm__owner=farmer)
        SettlementFactory(sale=sale, farmer=farmer)

        reply = route_message(farmer_contact, "raise dispute")
        assert "dispute" in reply.lower()

        reply = route_message(farmer_contact, "1")
        assert "reason" in reply.lower()

        reply = route_message(farmer_contact, "3")
        assert "describe" in reply.lower()

        reply = route_message(farmer_contact, "I was paid less than the agreed amount")
        assert "evidence" in reply.lower()

        reply = route_message(farmer_contact, "2")
        assert "confirm" in reply.lower()

        reply = route_message(farmer_contact, "yes")
        assert "submitted" in reply.lower()

        from apps.disputes.models import Dispute
        assert Dispute.objects.filter(raised_by=farmer).exists()


# ─────────────────────────────────────────────────────
# Buyer grading workflow tests
# ─────────────────────────────────────────────────────

@pytest.mark.django_db
class TestBuyerGradingWorkflow:

    def test_grading_full_flow(self, buyer_contact, buyer):
        farm = FarmFactory()
        season = SeasonFactory(farm=farm)
        LotFactory(season=season, status=LotStatus.CURED)

        reply = route_message(buyer_contact, "record grading")
        assert "select a lot" in reply.lower()

        reply = route_message(buyer_contact, "1")
        assert "grade" in reply.lower()

        reply = route_message(buyer_contact, "A1")
        assert "weight" in reply.lower()

        reply = route_message(buyer_contact, "450")
        assert "bales" in reply.lower()

        reply = route_message(buyer_contact, "10")
        assert "notes" in reply.lower()

        reply = route_message(buyer_contact, "Good quality leaf")
        assert "confirm" in reply.lower()

        reply = route_message(buyer_contact, "yes")
        assert "recorded" in reply.lower()

        from apps.grading.models import GradeRecord
        assert GradeRecord.objects.filter(graded_by=buyer, grade="A1").exists()


# ─────────────────────────────────────────────────────
# Buyer sale workflow tests
# ─────────────────────────────────────────────────────

@pytest.mark.django_db
class TestBuyerSaleWorkflow:

    @patch("apps.whatsapp.tasks.send_whatsapp_message_task.delay")
    def test_sale_full_flow(self, mock_send, buyer_contact, buyer):
        farm = FarmFactory()
        season = SeasonFactory(farm=farm)
        LotFactory(season=season, status=LotStatus.GRADED)

        reply = route_message(buyer_contact, "record sale")
        assert "select a" in reply.lower()

        reply = route_message(buyer_contact, "1")
        assert "price" in reply.lower()

        reply = route_message(buyer_contact, "4.50")
        assert "total weight" in reply.lower()

        reply = route_message(buyer_contact, "450")
        assert "confirm" in reply.lower()
        assert "$2025" in reply

        reply = route_message(buyer_contact, "yes")
        assert "recorded" in reply.lower()

        from apps.sales.models import Sale
        assert Sale.objects.filter(buyer=buyer).exists()


# ─────────────────────────────────────────────────────
# Webhook view tests
# ─────────────────────────────────────────────────────

@pytest.mark.django_db
class TestWhatsAppWebhookView:

    def test_webhook_valid_message(self, client, farmer):
        with patch("apps.whatsapp.views.get_whatsapp_provider") as mock_gw:
            mock_provider = MockWhatsAppProvider()
            mock_gw.return_value = mock_provider

            with patch("apps.whatsapp.tasks.send_whatsapp_message_task.delay"):
                resp = client.post(
                    "/api/v1/whatsapp/webhook/",
                    data={
                        "From": "whatsapp:+263771234567",
                        "Body": "help",
                        "MessageSid": "SM123456",
                    },
                )

        assert resp.status_code == 200
        assert WhatsAppMessageLog.objects.filter(
            phone_number="+263771234567",
            direction=WhatsAppDirection.INBOUND,
        ).exists()

    def test_webhook_invalid_signature(self, client):
        with patch("apps.whatsapp.views.get_whatsapp_provider") as mock_gw:
            mock_provider = MagicMock()
            mock_provider.validate_webhook_signature.return_value = False
            mock_gw.return_value = mock_provider

            resp = client.post("/api/v1/whatsapp/webhook/", data={"Body": "test"})
        assert resp.status_code == 403

    def test_webhook_with_media(self, client, farmer):
        with patch("apps.whatsapp.views.get_whatsapp_provider") as mock_gw:
            mock_provider = MockWhatsAppProvider()
            mock_gw.return_value = mock_provider

            with patch("apps.whatsapp.tasks.send_whatsapp_message_task.delay"):
                resp = client.post(
                    "/api/v1/whatsapp/webhook/",
                    data={
                        "From": "whatsapp:+263771234567",
                        "Body": "",
                        "MessageSid": "SM789",
                        "NumMedia": "1",
                        "MediaUrl0": "https://example.com/media.jpg",
                        "MediaContentType0": "image/jpeg",
                    },
                )

        assert resp.status_code == 200
        msg = WhatsAppMessageLog.objects.filter(phone_number="+263771234567").first()
        assert msg.message_type == "media"


# ─────────────────────────────────────────────────────
# Delivery status callback tests
# ─────────────────────────────────────────────────────

@pytest.mark.django_db
class TestDeliveryStatusView:

    def test_delivery_status_update(self, client, farmer_contact):
        msg_log = WhatsAppMessageLog.objects.create(
            phone_number="+263771234567",
            direction=WhatsAppDirection.OUTBOUND,
            provider_message_id="SM_TEST_123",
            delivery_status=WhatsAppDeliveryStatus.QUEUED,
        )

        with patch("apps.whatsapp.views.get_whatsapp_provider") as mock_gw:
            mock_provider = MockWhatsAppProvider()
            mock_gw.return_value = mock_provider

            resp = client.post(
                "/api/v1/whatsapp/status/",
                data={
                    "MessageSid": "SM_TEST_123",
                    "MessageStatus": "delivered",
                },
            )

        assert resp.status_code == 200
        msg_log.refresh_from_db()
        assert msg_log.delivery_status == WhatsAppDeliveryStatus.DELIVERED


# ─────────────────────────────────────────────────────
# Twilio service tests
# ─────────────────────────────────────────────────────

@pytest.mark.django_db
class TestTwilioService:

    def test_mock_provider_send(self):
        provider = MockWhatsAppProvider()
        result = provider.send_message("+263771234567", "Test message")
        assert result["status"] == "sent"
        assert len(provider.sent_messages) == 1

    def test_mock_provider_media(self):
        provider = MockWhatsAppProvider()
        result = provider.send_media_message("+263771234567", "Image", "http://img.jpg")
        assert result["status"] == "sent"

    def test_mock_webhook_always_valid(self):
        provider = MockWhatsAppProvider()
        assert provider.validate_webhook_signature(None) is True

    def test_send_whatsapp_message_logs(self, db):
        with patch("apps.whatsapp.twilio_service.get_whatsapp_provider") as mock_gw:
            mock_gw.return_value = MockWhatsAppProvider()
            log = send_whatsapp_message(to="+263771234567", body="Hello")

        assert log.direction == WhatsAppDirection.OUTBOUND
        assert log.delivery_status == WhatsAppDeliveryStatus.QUEUED
        assert log.message_body == "Hello"


# ─────────────────────────────────────────────────────
# Intent log tests
# ─────────────────────────────────────────────────────

@pytest.mark.django_db
class TestIntentLogging:

    @patch("apps.whatsapp.intent_router._handle_ai_query", return_value="AI response")
    def test_intent_logged(self, mock_ai, farmer_contact):
        route_message(farmer_contact, "my settlements")
        assert WhatsAppIntentLog.objects.filter(detected_intent="lookup_settlements").exists()


# ─────────────────────────────────────────────────────
# Template notification tests
# ─────────────────────────────────────────────────────

@pytest.mark.django_db
class TestNotificationService:

    @patch("apps.whatsapp.tasks.send_template_notification_task.delay")
    def test_notify_settlement_created(self, mock_task, farmer):
        sale = SaleFactory(lot__farm__owner=farmer)
        settlement = SettlementFactory(sale=sale, farmer=farmer)

        from apps.whatsapp.notification_service import notify_settlement_created
        notify_settlement_created(farmer, settlement)
        mock_task.assert_called_once()

    @patch("apps.whatsapp.tasks.send_template_notification_task.delay")
    def test_notify_dispute_opened(self, mock_task, farmer):
        from apps.disputes.models import Dispute
        dispute = Dispute.objects.create(
            raised_by=farmer,
            title="Test dispute",
            description="Test",
            status=DisputeStatus.OPEN,
        )
        from apps.whatsapp.notification_service import notify_dispute_opened
        notify_dispute_opened(farmer, dispute)
        mock_task.assert_called_once()

    def test_notify_no_phone_does_nothing(self):
        from apps.whatsapp.notification_service import notify_reminder
        from unittest.mock import MagicMock
        user = MagicMock()
        user.phone_number = ""
        notify_reminder(user, "Test")


# ─────────────────────────────────────────────────────
# Buyer help menu tests
# ─────────────────────────────────────────────────────

@pytest.mark.django_db
class TestBuyerHelpMenu:

    def test_buyer_sees_buyer_commands(self, buyer_contact):
        reply = route_message(buyer_contact, "help")
        assert "RECORD GRADING" in reply
        assert "RECORD SALE" in reply
        assert "UPDATE SETTLEMENT" in reply

    def test_farmer_does_not_see_buyer_commands(self, farmer_contact):
        reply = route_message(farmer_contact, "help")
        assert "REGISTER FARM" in reply
        assert "RECORD GRADING" not in reply
