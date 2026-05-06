from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.schema import EmptySchemaSerializer
from apps.sync.models import SyncRecord
from apps.sync.serializers import BatchSyncRequestSerializer, SyncResultSerializer
from apps.sync.services import process_batch_sync


def _run_batch(request, allowed_types: set[str] | None):
    serializer = BatchSyncRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    records = serializer.validated_data["records"]
    if allowed_types is not None:
        bad = [r["payload_type"] for r in records if r["payload_type"] not in allowed_types]
        if bad:
            return Response(
                {"detail": f"Invalid payload_type for this endpoint: {set(bad)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )
    results = process_batch_sync(records_data=records, actor=request.user)
    return Response(
        {"results": SyncResultSerializer(results, many=True).data},
        status=status.HTTP_200_OK,
    )


class BatchSyncView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = BatchSyncRequestSerializer

    def post(self, request):
        return _run_batch(request, allowed_types=None)


class EventsBatchSyncView(APIView):
    """Idempotent batch for trace / operational events (offline farmer sync)."""

    permission_classes = [IsAuthenticated]
    serializer_class = BatchSyncRequestSerializer

    def post(self, request):
        return _run_batch(request, allowed_types={"trace_event"})


class DocumentsBatchSyncView(APIView):
    """Idempotent batch for document metadata (+ optional small file base64)."""

    permission_classes = [IsAuthenticated]
    serializer_class = BatchSyncRequestSerializer

    def post(self, request):
        return _run_batch(request, allowed_types={"document_meta"})


class SyncChangesView(APIView):
    """
    Pull server-side sync outcomes since a timestamp (ISO 8601).
    Pagination: use `since` from the last `server_time` returned.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = EmptySchemaSerializer

    def get(self, request):
        since = request.query_params.get("since")
        limit = min(int(request.query_params.get("limit", 100)), 500)
        qs = SyncRecord.objects.filter(actor=request.user).order_by("updated_at")
        if since:
            dt = parse_datetime(since)
            if dt:
                qs = qs.filter(updated_at__gt=dt)
        rows = list(qs[:limit])
        data = [
            {
                "client_record_id": str(r.client_record_id),
                "idempotency_key": r.idempotency_key,
                "payload_type": r.payload_type,
                "status": r.status,
                "remote_object_id": str(r.remote_object_id) if r.remote_object_id else None,
                "remote_object_type": r.remote_object_type or None,
                "error_detail": r.error_detail or None,
                "updated_at": r.updated_at.isoformat(),
            }
            for r in rows
        ]
        return Response(
            {
                "results": data,
                "server_time": timezone.now().isoformat(),
                "pagination": {
                    "style": "since_timestamp",
                    "limit": limit,
                    "hint": "Pass since=server_time on the next call for incremental updates.",
                },
            }
        )
