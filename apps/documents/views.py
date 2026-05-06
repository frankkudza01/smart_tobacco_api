from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.ai_intelligence.models import AnomalyAlert
from apps.common.access import can_attach_document_to_lot, can_view_document
from apps.common.access_control import documents_queryset_for_org
from apps.common.enums import AnomalyAlertType, UserRole
from apps.common.schema import EmptySchemaSerializer
from apps.documents.models import Document
from apps.documents.serializers import (
    DocumentSerializer,
    DocumentUploadSerializer,
    DocumentVerificationResultSerializer,
    DocumentVerifyRequestSerializer,
)
from apps.documents.services import upload_document, verify_document
from apps.documents.verification_pipeline import verify_hash_for_user, verify_upload_for_user
from apps.lots.models import Lot


class IsAuditorOrAdmin(BasePermission):
    def has_permission(self, request, view):
        u = request.user
        return bool(u and u.is_authenticated and u.role in (UserRole.REGULATOR_AUDITOR, UserRole.SYSTEM_ADMIN))


class DocumentListCreateView(generics.ListCreateAPIView):
    serializer_class = DocumentSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ["lot", "document_type", "anchor_status", "verification_state"]
    search_fields = ["title", "file_name"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Document.objects.none()
        user = self.request.user
        qs = documents_queryset_for_org(user)
        if user.role == UserRole.SMALLHOLDER_FARMER:
            return qs.filter(uploaded_by=user)
        if user.role == UserRole.BUYER_CONTRACTOR:
            return qs
        return qs

    def create(self, request, *args, **kwargs):
        serializer = DocumentUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        lot = None
        if data.get("lot"):
            lot = get_object_or_404(Lot, pk=data["lot"])
            if not can_attach_document_to_lot(request.user, lot):
                return Response({"detail": "Forbidden."}, status=status.HTTP_403_FORBIDDEN)

        doc = upload_document(
            lot=lot,
            uploaded_by=request.user,
            document_type=data["document_type"],
            title=data["title"],
            description=data.get("description", ""),
            file=data["file"],
        )
        return Response(
            DocumentSerializer(doc).data,
            status=status.HTTP_201_CREATED,
        )


class DocumentDetailView(generics.RetrieveAPIView):
    serializer_class = DocumentSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = "pk"

    def get_queryset(self):
        return documents_queryset_for_org(self.request.user)


class DocumentVerifyView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = EmptySchemaSerializer

    def post(self, request, pk):
        try:
            document = Document.objects.get(pk=pk)
        except Document.DoesNotExist:
            return Response({"detail": "Document not found."}, status=status.HTTP_404_NOT_FOUND)

        if not can_view_document(request.user, document):
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

        result = verify_document(document)
        serializer = DocumentVerificationResultSerializer(result)
        return Response(serializer.data, status=status.HTTP_200_OK)


@extend_schema(tags=["documents"])
class DocumentGlobalVerifyView(APIView):
    """Verify by SHA-256 or uploaded file (role-scoped matches)."""

    permission_classes = [IsAuthenticated]
    serializer_class = DocumentVerifyRequestSerializer

    def post(self, request):
        ser = DocumentVerifyRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        h = ser.validated_data.get("doc_hash") or ""
        f = ser.validated_data.get("file")
        if f:
            out = verify_upload_for_user(user=request.user, file=f)
        elif h:
            out = verify_hash_for_user(user=request.user, sha256_hex=h.strip().lower())
        else:
            return Response({"detail": "Provide doc_hash or file"}, status=status.HTTP_400_BAD_REQUEST)
        return Response(out)


@extend_schema(tags=["documents"])
class DocumentSuspectListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated, IsAuditorOrAdmin]
    serializer_class = DocumentSerializer

    def get_queryset(self):
        from apps.common.org_utils import get_user_primary_organization

        org = get_user_primary_organization(self.request.user)
        if org is None:
            return Document.objects.none()
        qs = documents_queryset_for_org(self.request.user)
        dup_ids = list(
            AnomalyAlert.objects.filter(
                organization_id=org.id,
                alert_type__in=[
                    AnomalyAlertType.DOC_DUPLICATE_NEAR,
                    AnomalyAlertType.DOC_DUPLICATE_EXACT,
                ],
            ).values_list("document_id", flat=True)
        )
        dup_ids = [x for x in dup_ids if x]
        return qs.filter(id__in=dup_ids).distinct()
