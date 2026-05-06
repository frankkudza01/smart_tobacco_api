import logging

from django.db import connection
from django.core.cache import cache
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from apps.common.schema import EmptySchemaSerializer

logger = logging.getLogger(__name__)


class HealthCheckView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    serializer_class = EmptySchemaSerializer

    def get(self, request):
        return Response({"status": "healthy"}, status=status.HTTP_200_OK)


class ReadinessCheckView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    serializer_class = EmptySchemaSerializer

    def get(self, request):
        checks = {}
        try:
            connection.ensure_connection()
            checks["database"] = "ok"
        except Exception:
            checks["database"] = "unavailable"

        try:
            cache.set("_readiness_probe", "1", 5)
            val = cache.get("_readiness_probe")
            checks["cache"] = "ok" if val == "1" else "degraded"
        except Exception:
            checks["cache"] = "unavailable"

        all_ok = all(v == "ok" for v in checks.values())
        return Response(
            {"status": "ready" if all_ok else "degraded", "checks": checks},
            status=status.HTTP_200_OK if all_ok else status.HTTP_503_SERVICE_UNAVAILABLE,
        )


class LivenessCheckView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    serializer_class = EmptySchemaSerializer

    def get(self, request):
        return Response({"status": "alive"}, status=status.HTTP_200_OK)
