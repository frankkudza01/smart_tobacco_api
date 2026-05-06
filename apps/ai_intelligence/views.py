from __future__ import annotations

import sys
from uuid import UUID

from django.conf import settings
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import AllowAny, BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.ai_intelligence.serializers import (
    AnomalyRunSerializer,
    AssistantChatResponseSerializer,
    AssistantChatSerializer,
    EvaluationMetricSerializer,
    ForecastQuerySerializer,
    PriceForecastQuerySerializer,
    RetrainSerializer,
    ReviewLabelSerializer,
    SatelliteYieldOutlookSerializer,
)
from apps.ai_intelligence.services.anomaly_service import AnomalyService
from apps.ai_intelligence.services.forecast_service import ForecastService
from apps.ai_intelligence.tasks import retrain_forecasts_job, run_anomaly_detection_job
from apps.ai_intelligence.throttles import AssistantChatThrottle
from apps.common.enums import UserRole
from apps.common.org_utils import get_user_primary_organization, require_organization
from apps.common.ai_sanitize import sanitize_ai_error_message
from apps.common.schema import EmptySchemaSerializer
from apps.ai_intelligence.models import EvaluationMetricRun, ForecastRun, ReviewLabel
from apps.ai_intelligence.services.openai_safe import has_provider_credentials


class IsSystemAdmin(BasePermission):
    def has_permission(self, request, view):
        u = request.user
        return bool(u and u.is_authenticated and u.role == UserRole.SYSTEM_ADMIN)


class IsBuyerSystemAdminOrAuditor(BasePermission):
    def has_permission(self, request, view):
        u = request.user
        if not u or not u.is_authenticated:
            return False
        return u.role in (
            UserRole.BUYER_CONTRACTOR,
            UserRole.SYSTEM_ADMIN,
            UserRole.REGULATOR_AUDITOR,
        )


class IsAuditorOrAdmin(BasePermission):
    def has_permission(self, request, view):
        u = request.user
        return bool(u and u.is_authenticated and u.role in (UserRole.REGULATOR_AUDITOR, UserRole.SYSTEM_ADMIN))


class SatelliteYieldOutlookView(APIView):
    """
    Farmer (and other farm viewers): NDVI-grounded yield outlook + optional LLM narrative.
    POST JSON ``{ "farm_id": "<uuid>", "season_id": null }``.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = SatelliteYieldOutlookSerializer

    def post(self, request):
        ser = SatelliteYieldOutlookSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        from apps.ai_intelligence.services.satellite_yield_outlook_service import (
            build_satellite_yield_outlook,
        )

        out = build_satellite_yield_outlook(
            request.user,
            farm_id=ser.validated_data["farm_id"],
            season_id=ser.validated_data.get("season_id"),
        )
        code = int(out.pop("status_code", 200))
        if code >= 400:
            return Response({"detail": out.get("detail", "error")}, status=code)
        return Response(out, status=status.HTTP_200_OK)


class ForecastYieldView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ForecastQuerySerializer

    def get(self, request):
        ser = ForecastQuerySerializer(data=request.query_params)
        ser.is_valid(raise_exception=True)
        data = ForecastService.list_yield_forecasts(
            request.user,
            season_id=ser.validated_data.get("season_id"),
            farm_id=ser.validated_data.get("farm_id"),
            lot_id=ser.validated_data.get("lot_id"),
            scope=ser.validated_data.get("scope") or None,
        )
        return Response({"results": data})


class ForecastPriceView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = PriceForecastQuerySerializer

    def get(self, request):
        ser = PriceForecastQuerySerializer(data=request.query_params)
        ser.is_valid(raise_exception=True)
        data = ForecastService.list_price_forecasts(
            request.user,
            season_id=ser.validated_data.get("season_id"),
            grade=ser.validated_data.get("grade") or None,
            scope=ser.validated_data.get("scope") or None,
        )
        return Response({"results": data})


class ForecastRetrainView(APIView):
    permission_classes = [IsAuthenticated, IsSystemAdmin]
    serializer_class = RetrainSerializer

    def post(self, request):
        ser = RetrainSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        org = require_organization(request.user)
        model_type = ser.validated_data["model_type"]
        retrain_forecasts_job.delay(str(org.id), model_type)
        return Response({"status": "queued", "organization_id": str(org.id), "model_type": model_type})


class AnomalyListView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = EmptySchemaSerializer

    def get(self, request):
        data = AnomalyService.list_alerts(
            request.user,
            status=request.query_params.get("status") or None,
            severity=request.query_params.get("severity") or None,
            alert_type=request.query_params.get("type") or None,
            subject=request.query_params.get("subject") or None,
        )
        return Response({"results": data})


class AnomalyRunView(APIView):
    permission_classes = [IsAuthenticated, IsBuyerSystemAdminOrAuditor]
    serializer_class = AnomalyRunSerializer

    def post(self, request):
        ser = AnomalyRunSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        org = require_organization(request.user)
        types = ser.validated_data.get("detection_types") or None
        run_anomaly_detection_job.delay(str(org.id), types)
        return Response({"status": "queued", "organization_id": str(org.id)})


class AnomalyLabelView(APIView):
    permission_classes = [IsAuthenticated, IsAuditorOrAdmin]
    serializer_class = ReviewLabelSerializer

    def post(self, request, alert_id):
        ser = ReviewLabelSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            aid = UUID(str(alert_id))
        except ValueError:
            return Response({"detail": "invalid id"}, status=status.HTTP_400_BAD_REQUEST)
        rl = AnomalyService.add_review_label(
            user=request.user,
            alert_id=aid,
            label=ser.validated_data["label"],
            notes=ser.validated_data.get("notes") or "",
        )
        if rl is None:
            return Response({"detail": "not found or forbidden"}, status=status.HTTP_404_NOT_FOUND)
        return Response({"id": str(rl.id), "label": rl.label})


class AnomalyCaseView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = EmptySchemaSerializer

    def get(self, request, alert_id):
        try:
            aid = UUID(str(alert_id))
        except ValueError:
            return Response({"detail": "invalid id"}, status=status.HTTP_400_BAD_REQUEST)
        packet = AnomalyService.case_packet(request.user, aid)
        if packet is None:
            return Response({"detail": "not found or forbidden"}, status=status.HTTP_404_NOT_FOUND)
        return Response(packet)


class AnomalyExportTokenView(APIView):
    """Auditor/admin: mint a short-lived signed URL to download the case packet JSON."""

    permission_classes = [IsAuthenticated, IsAuditorOrAdmin]
    serializer_class = EmptySchemaSerializer

    def get(self, request, alert_id):
        try:
            aid = UUID(str(alert_id))
        except ValueError:
            return Response({"detail": "invalid id"}, status=status.HTTP_400_BAD_REQUEST)
        packet = AnomalyService.case_packet(request.user, aid)
        if packet is None:
            return Response({"detail": "not found or forbidden"}, status=status.HTTP_404_NOT_FOUND)
        from apps.ai_intelligence.export_signed import (
            MAX_AGE_SECONDS,
            build_export_download_url,
            sign_export_payload,
        )

        token = sign_export_payload(alert_id=aid, user_id=request.user.id)
        url = build_export_download_url(request, token)
        return Response(
            {
                "export_url": url,
                "expires_seconds": MAX_AGE_SECONDS,
                "alert_id": str(aid),
            }
        )


class AnomalyExportDownloadView(APIView):
    """
    Public GET with signed token only. Re-validates user role and access at download time.
    """

    permission_classes = [AllowAny]
    authentication_classes = []
    serializer_class = EmptySchemaSerializer

    def get(self, request):
        from apps.ai_intelligence.export_signed import unsign_export_token

        token = request.query_params.get("t") or ""
        parsed = unsign_export_token(token)
        if not parsed:
            return Response({"detail": "invalid or expired link"}, status=status.HTTP_403_FORBIDDEN)
        alert_id, user_id_str = parsed
        from django.contrib.auth import get_user_model

        User = get_user_model()
        try:
            user = User.objects.get(pk=user_id_str)
        except (User.DoesNotExist, ValueError):
            return Response({"detail": "invalid link"}, status=status.HTTP_403_FORBIDDEN)
        if user.role not in (UserRole.REGULATOR_AUDITOR, UserRole.SYSTEM_ADMIN):
            return Response({"detail": "forbidden"}, status=status.HTTP_403_FORBIDDEN)
        packet = AnomalyService.case_packet(user, alert_id)
        if packet is None:
            return Response({"detail": "not found or forbidden"}, status=status.HTTP_404_NOT_FOUND)
        return Response(packet)


class AssistantChatView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [AssistantChatThrottle]
    serializer_class = AssistantChatSerializer

    def post(self, request):
        from apps.ai_intelligence.assistant_service import run_hardened_assistant_chat
        from apps.common.exceptions import AIServiceException

        ser = AssistantChatSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        conv = ser.validated_data.get("conversation_id")
        try:
            out = run_hardened_assistant_chat(
                user=request.user,
                prompt=ser.validated_data["prompt"],
                conversation_id=str(conv) if conv else None,
            )
        except AIServiceException as e:
            return Response(
                {"detail": sanitize_ai_error_message(str(e))},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response(AssistantChatResponseSerializer(out).data, status=status.HTTP_200_OK)


class AssistantLeafDiagnoseView(APIView):
    """
    Diagnose tobacco leaf issues from an uploaded image + user context.
    Returns concise agronomy guidance scoped to farmer safety.
    """

    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    serializer_class = EmptySchemaSerializer

    def post(self, request):
        from apps.ai_intelligence.services.openai_safe import chat_with_image_simple

        image = request.FILES.get("image")
        prompt = (request.data.get("prompt") or "").strip()
        if image is None:
            return Response({"detail": "image is required"}, status=status.HTTP_400_BAD_REQUEST)
        if not prompt:
            prompt = "Diagnose likely issue and suggest immediate practical actions."

        # Hard limit to avoid memory spikes on large uploads.
        if image.size and image.size > 8 * 1024 * 1024:
            return Response({"detail": "image too large (max 8MB)"}, status=status.HTTP_400_BAD_REQUEST)

        system = (
            "You are an agronomy assistant for Zimbabwe tobacco farmers. "
            "Use visual evidence + user text. Do not claim certainty when unsure. "
            "Provide: likely causes, immediate actions (24-72h), safe handling cautions, "
            "and what records to log in app. Avoid inventing unapproved chemical brands."
        )
        try:
            result = chat_with_image_simple(
                system_prompt=system,
                user_message=prompt,
                image_bytes=image.read(),
                mime_type=getattr(image, "content_type", None) or "image/jpeg",
            )
            return Response({"response": result, "mode": "image_analysis"}, status=status.HTTP_200_OK)
        except Exception as exc:
            return Response(
                {"detail": f"Leaf diagnosis failed: {sanitize_ai_error_message(str(exc))}"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )


class AIHealthView(APIView):
    """
    Lightweight assistant health endpoint (no secrets).
    Helps verify active provider/config/runtime used by assistant/chat.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = EmptySchemaSerializer

    def get(self, request):
        provider = (getattr(settings, "AI_PROVIDER", "openai") or "openai").strip().lower()
        fb = (getattr(settings, "AI_GEMINI_FALLBACK_MODEL", "") or "").strip()
        primary = (getattr(settings, "AI_MODEL_NAME", "") or "").strip()
        gemini_fb = fb if (fb and primary and fb.lower() != primary.lower()) else None
        return Response(
            {
                "ai_enabled": bool(getattr(settings, "AI_ENABLED", False)),
                "provider": provider,
                "model_name": getattr(settings, "AI_MODEL_NAME", ""),
                "gemini_fallback_model": gemini_fb,
                "gemini_max_http_retries": int(getattr(settings, "AI_GEMINI_MAX_HTTP_RETRIES", 10) or 10),
                "provider_api_key_configured": has_provider_credentials(),
                "force_fallback": bool(getattr(settings, "AI_FORCE_FALLBACK", False)),
                "python_version": ".".join(str(x) for x in sys.version_info[:3]),
                "langchain_runtime_supported": sys.version_info < (3, 14),
            }
        )


class AIEvaluationSummaryView(APIView):
    """
    Read-only summary of how every AI surface is constrained against hallucination,
    plus the latest measured accuracy for the local trainable model (ridge yield).

    Designed for academic / supervisor demonstration: every model surface should
    appear here with its guards and (when applicable) numeric accuracy.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = EmptySchemaSerializer

    def get(self, request):
        from apps.ai_intelligence.assistant_service import (
            ASSISTANT_HALLUCINATION_GUARDS,
            SYSTEM_PROMPT_VERSION,
        )
        from apps.ai_intelligence.services.forecast_service import (
            PRICE_HALLUCINATION_GUARDS,
            YIELD_HALLUCINATION_GUARDS,
        )
        from apps.grading.grading_ai_service import PROVIDER_CHAIN_LOCAL_FIRST
        from apps.grading.local_leaf_histogram import _LOCAL_GUARDS as LOCAL_HIST_GUARDS
        from apps.grading.zimbabwe_grades import GRADES_VERSION

        org = get_user_primary_organization(request.user)
        ridge_summary: dict[str, Any] = {
            "available": False,
            "reason": "no_organization_context" if org is None else "no_run_yet",
        }
        if org is not None:
            latest_run = (
                ForecastRun.objects.filter(organization=org, model_type="yield")
                .order_by("-trained_at")
                .first()
            )
            if latest_run is not None:
                ridge_summary = {
                    "available": True,
                    "model_version": latest_run.model_version,
                    "trained_at": latest_run.trained_at.isoformat() if latest_run.trained_at else None,
                    "metrics": latest_run.metrics_json or {},
                }

        return Response(
            {
                "policy": {
                    "tobacco_only_scope": True,
                    "rbac_enforced_in_tools": True,
                    "pii_redaction_pre_llm": True,
                },
                "models": {
                    "assistant_chat": {
                        "kind": "external_llm_with_tool_calling",
                        "system_prompt_version": SYSTEM_PROMPT_VERSION,
                        "hallucination_guards": list(ASSISTANT_HALLUCINATION_GUARDS),
                        "accuracy_method": (
                            "Per-response 'grounding' block reports tool_count/grounded; offline "
                            "labelling done via review_label endpoint and surfaced in metrics."
                        ),
                    },
                    "vision_grading": {
                        "kind": "local_first_with_api_fallback",
                        "provider_chain_default": list(PROVIDER_CHAIN_LOCAL_FIRST),
                        "primary": "local_histogram_v1",
                        "fallbacks": ["openai_vision", "gemini_vision"],
                        "allowed_grades_version": GRADES_VERSION,
                        "hallucination_guards": [
                            "json_schema_strict",
                            "is_tobacco_leaf_check",
                            "allowed_grades_snap",
                            "confidence_clamped_0_to_1",
                            "local_first_then_external_api_fallback",
                        ],
                        "local_primary_guards": list(LOCAL_HIST_GUARDS),
                        "notes": (
                            "Local on-server histogram model runs first; OpenAI / Gemini "
                            "vision are only consulted when local raises a non-validation "
                            "error or when the caller sends prefer_api=true."
                        ),
                    },
                    "yield_forecast": {
                        "kind": "local_ridge_regression_no_external_api",
                        "uses_external_api": False,
                        "hallucination_guards": list(YIELD_HALLUCINATION_GUARDS),
                        "latest_run": ridge_summary,
                    },
                    "price_forecast": {
                        "kind": "deterministic_basket_band_no_external_api",
                        "uses_external_api": False,
                        "hallucination_guards": list(PRICE_HALLUCINATION_GUARDS),
                    },
                },
            }
        )


class EvaluationMetricIngestView(APIView):
    """Offline AUROC / MAPE hooks — auditors and admins only."""

    permission_classes = [IsAuthenticated, IsAuditorOrAdmin]
    serializer_class = EvaluationMetricSerializer

    def get(self, request):
        org = get_user_primary_organization(request.user)
        if org is None:
            return Response({"results": []})
        qs = EvaluationMetricRun.objects.filter(organization=org).order_by("-evaluated_at")[:100]
        data = [
            {
                "id": str(r.id),
                "metric_name": r.metric_name,
                "model_key": r.model_key,
                "model_version": r.model_version,
                "value": str(r.value) if r.value is not None else None,
                "evaluated_at": r.evaluated_at.isoformat(),
            }
            for r in qs
        ]
        return Response({"results": data})

    def post(self, request):
        ser = EvaluationMetricSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        org = require_organization(request.user)
        v = ser.validated_data.get("value")
        row = EvaluationMetricRun.objects.create(
            organization=org,
            metric_name=ser.validated_data["metric_name"],
            model_key=ser.validated_data["model_key"],
            model_version=ser.validated_data.get("model_version") or "",
            value=v,
            metrics_json=ser.validated_data.get("metrics_json") or {},
            evaluated_at=timezone.now(),
            notes=(ser.validated_data.get("notes") or "")[:2000],
        )
        return Response({"id": str(row.id)})


@extend_schema(tags=["analytics"])
class DuplicateLabelsExportView(APIView):
    """Export reviewer labels for duplicate/near-duplicate precision-recall analysis."""

    permission_classes = [IsAuthenticated, IsAuditorOrAdmin]
    serializer_class = EmptySchemaSerializer

    def get(self, request):
        org = require_organization(request.user)
        qs = (
            ReviewLabel.objects.filter(organization=org)
            .select_related("alert", "reviewer")
            .order_by("-created_at")[:5000]
        )
        rows = []
        for r in qs:
            a = r.alert
            if not a or a.alert_type not in (
                "DOC_DUPLICATE_EXACT",
                "DOC_DUPLICATE_NEAR",
            ):
                continue
            rows.append(
                {
                    "review_id": str(r.id),
                    "alert_id": str(a.id),
                    "alert_type": a.alert_type,
                    "label": r.label,
                    "created_at": r.created_at.isoformat(),
                }
            )
        tp = sum(1 for x in rows if x["label"] == "confirmed")
        fp = sum(1 for x in rows if x["label"] == "false_positive")
        denom = tp + fp
        precision = (tp / denom) if denom else None
        return Response(
            {
                "results": rows,
                "summary": {
                    "confirmed": tp,
                    "false_positive": fp,
                    "precision_estimate": round(precision, 4) if precision is not None else None,
                },
            }
        )
