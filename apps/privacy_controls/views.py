from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.org_utils import require_organization
from apps.common.schema import EmptySchemaSerializer
from apps.privacy_controls.models import DataSubjectRequest, DataSubjectRequestStatus, DataSubjectRequestType
from apps.privacy_controls.services.export import build_user_export_payload


@extend_schema(tags=["privacy"])
class PrivacyExportMeView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = EmptySchemaSerializer

    def get(self, request):
        org = require_organization(request.user)
        payload = build_user_export_payload(user=request.user, organization=org)
        return Response(payload)


@extend_schema(tags=["privacy"])
class PrivacyErasureRequestView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = EmptySchemaSerializer

    def post(self, request):
        org = require_organization(request.user)
        DataSubjectRequest.objects.create(
            user=request.user,
            organization=org,
            request_type=DataSubjectRequestType.DELETE,
            status=DataSubjectRequestStatus.PENDING,
        )
        return Response({"status": "received"}, status=status.HTTP_202_ACCEPTED)
