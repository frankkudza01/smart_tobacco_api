import pytest

from apps.blockchain.gateway import MockBlockchainGateway


class TestMockBlockchainGateway:
    def test_anchor_hash_returns_tx(self):
        gateway = MockBlockchainGateway()
        result = gateway.anchor_hash(
            data_hash="abc123def456",
            reference_type="trace_event",
            reference_id="some-uuid",
        )
        assert "tx_hash" in result
        assert result["tx_hash"].startswith("0x")
        assert result["status"] == "CONFIRMED"
        assert result["block_number"] == 12345

    def test_verify_anchor(self):
        gateway = MockBlockchainGateway()
        result = gateway.verify_anchor("0x" + "a" * 64)
        assert result["verified"] is True

    def test_get_receipt(self):
        gateway = MockBlockchainGateway()
        result = gateway.get_receipt("0x" + "b" * 64)
        assert result["status"] == "CONFIRMED"


@pytest.mark.django_db
class TestBlockchainTasks:
    def test_anchor_event_hash_task(self, lot):
        from apps.traceability.models import TraceEvent
        from apps.common.enums import TraceEventType, BlockchainAnchorStatus
        from django.utils import timezone

        event = TraceEvent.objects.create(
            lot=lot,
            actor=lot.farm.owner,
            event_type=TraceEventType.PLANTING,
            timestamp=timezone.now(),
        )

        from apps.blockchain.tasks import anchor_event_hash
        anchor_event_hash(str(event.id))

        event.refresh_from_db()
        assert event.anchor_status == BlockchainAnchorStatus.CONFIRMED
        assert event.anchor_tx_hash.startswith("0x")
