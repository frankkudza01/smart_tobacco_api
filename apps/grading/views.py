from django.db import transaction
from rest_framework import generics, status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.enums import LotStatus, UserRole
from apps.common.permissions import IsBuyerContractor
from apps.grading.grading_ai_service import NonTobaccoLeafError, suggest_grade_from_leaf_image
from apps.grading.models import GradeRecord
from apps.grading.serializers import GradeRecordSerializer
from apps.grading.zimbabwe_grades import allowed_grades_sorted
from apps.lots.models import Lot
from apps.sales.services import create_or_refresh_sale_from_grading


class GradeRecordListCreateView(generics.ListCreateAPIView):
    serializer_class = GradeRecordSerializer
    filterset_fields = ["lot", "grade"]
    ordering_fields = ["graded_at", "created_at"]

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsBuyerContractor()]
        return [IsAuthenticated()]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return GradeRecord.objects.none()
        user = self.request.user
        qs = GradeRecord.objects.select_related("lot", "graded_by")
        if user.role == UserRole.SMALLHOLDER_FARMER:
            return qs.filter(lot__farm__owner=user)
        if user.role == UserRole.BUYER_CONTRACTOR:
            org_ids = user.memberships.values_list("organization_id", flat=True)
            return qs.filter(lot__farm__organization_id__in=org_ids)
        return qs

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        lot = serializer.validated_data["lot"]
        existing_events = GradeRecord.objects.filter(lot=lot).count()
        bale_count = int(getattr(lot, "bale_count", 0) or 0)
        if bale_count <= 0:
            return Response(
                {"detail": "Lot bale_count must be greater than zero before grading."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if existing_events >= bale_count:
            return Response(
                {
                    "detail": (
                        f"Lot already has {existing_events} grading event(s), "
                        f"which matches bale_count={bale_count}. No more grading events allowed."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        grade_record = serializer.save()
        total_events = existing_events + 1
        if total_events >= bale_count:
            lot.status = LotStatus.GRADED
            lot.save(update_fields=["status", "updated_at"])
            create_or_refresh_sale_from_grading(lot=lot, buyer=request.user)
        return Response(
            GradeRecordSerializer(grade_record).data,
            status=status.HTTP_201_CREATED,
        )


class GradeRecordDetailView(generics.RetrieveAPIView):
    serializer_class = GradeRecordSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = "pk"
    queryset = GradeRecord.objects.select_related("lot", "graded_by")


class GradeCatalogView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({"grades": allowed_grades_sorted()}, status=status.HTTP_200_OK)


class GradeSuggestView(APIView):
    """
    Buyer-only grade suggestion for Zimbabwe-style flue-cured leaf photographs.

    **Provider order (default):** ``local_histogram_v1`` → ``openai_vision`` → ``gemini_vision``.

    The local on-server histogram model is the **primary** path. External vision
    LLMs are consulted only as fallbacks (when local errors out) or when the
    caller sends ``prefer_api=true`` (multipart form field).

    Send ``defer_remote_fallback=true`` to run **only** the local model first.
    If it hits an unexpected error, the response returns ``needs_remote_fallback`` so the client can confirm before repeating without ``defer_remote_fallback`` (typically with ``prefer_api=true``).

    The response always includes ``provider``, ``provider_chain`` and ``hallucination_guards`` when applicable so the UI can show which path produced the answer.
    """

    permission_classes = [IsBuyerContractor]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        image = request.FILES.get("image")
        if image is None:
            return Response({"detail": "image is required (multipart field 'image')"}, status=status.HTTP_400_BAD_REQUEST)
        if image.size and image.size > 12 * 1024 * 1024:
            return Response({"detail": "image too large (max 12MB)"}, status=status.HTTP_400_BAD_REQUEST)

        lot_uuid = (request.data.get("lot") or "").strip()
        lot_number = None
        tobacco_type = None
        if lot_uuid:
            try:
                lot = Lot.objects.select_related("farm").get(pk=lot_uuid)
            except Lot.DoesNotExist:
                return Response({"detail": "lot not found"}, status=status.HTTP_404_NOT_FOUND)
            org_ids = set(request.user.memberships.values_list("organization_id", flat=True))
            lot_org_id = getattr(lot.farm, "organization_id", None)
            if lot_org_id not in org_ids:
                return Response({"detail": "not allowed to use this lot"}, status=status.HTTP_403_FORBIDDEN)
            lot_number = lot.lot_number
            tobacco_type = lot.tobacco_type

        moisture_raw = request.data.get("moisture_percent")
        moisture: float | None = None
        if moisture_raw not in (None, ""):
            try:
                moisture = float(moisture_raw)
            except (TypeError, ValueError):
                return Response({"detail": "moisture_percent must be a number"}, status=status.HTTP_400_BAD_REQUEST)

        prefer_api_raw = (request.data.get("prefer_api") or "").strip().lower()
        prefer_api = prefer_api_raw in ("1", "true", "yes", "on")

        defer_raw = (request.data.get("defer_remote_fallback") or "").strip().lower()
        defer_remote_fallback = defer_raw in ("1", "true", "yes", "on")

        mime = getattr(image, "content_type", None) or "image/jpeg"
        try:
            body = image.read()
        except Exception as exc:
            return Response({"detail": f"could not read image: {exc}"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            out = suggest_grade_from_leaf_image(
                image_bytes=body,
                mime_type=mime,
                lot_number=lot_number,
                tobacco_type=tobacco_type,
                moisture_percent=moisture,
                prefer_api=prefer_api,
                defer_remote_fallback=defer_remote_fallback,
            )
        except NonTobaccoLeafError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            return Response(
                {"detail": f"grading suggestion failed: {exc}"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response(out, status=status.HTTP_200_OK)
