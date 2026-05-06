from rest_framework import serializers


class SyncItemSerializer(serializers.Serializer):
    client_record_id = serializers.UUIDField()
    idempotency_key = serializers.CharField(max_length=255)
    payload_type = serializers.ChoiceField(
        choices=["farm", "season", "lot", "trace_event", "document_meta", "dispute"]
    )
    payload = serializers.JSONField()


class BatchSyncRequestSerializer(serializers.Serializer):
    records = SyncItemSerializer(many=True)


class SyncResultSerializer(serializers.Serializer):
    client_record_id = serializers.UUIDField()
    idempotency_key = serializers.CharField()
    status = serializers.CharField()
    remote_object_id = serializers.UUIDField(allow_null=True)
    error_detail = serializers.CharField(allow_null=True, required=False)
