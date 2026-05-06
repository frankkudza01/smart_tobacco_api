from __future__ import annotations

from datetime import timedelta

from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.enums import UserRole
from apps.common.org_utils import get_user_primary_organization, require_organization
from apps.common.schema import EmptySchemaSerializer
from apps.worldready.models import SusSurveyResponse, UserPreference
from apps.worldready.serializers import SusSurveySerializer, UserPreferenceSerializer, UserPreferenceWriteSerializer
from apps.worldready.services.guided_forms import guided_forms_for_role
from apps.worldready.services.translation import get_strings_for_locale
from apps.worldready.services.ux_metrics import log_support_request


class IsAuditorOrAdmin(BasePermission):
    def has_permission(self, request, view):
        u = request.user
        return bool(u and u.is_authenticated and u.role in (UserRole.REGULATOR_AUDITOR, UserRole.SYSTEM_ADMIN))


@extend_schema(tags=["preferences"])
class UserPreferenceMeView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = UserPreferenceWriteSerializer

    def get(self, request):
        org = require_organization(request.user)
        pref, _ = UserPreference.objects.get_or_create(
            user=request.user,
            organization=org,
            defaults={},
        )
        return Response(UserPreferenceSerializer(pref).data)

    def patch(self, request):
        org = require_organization(request.user)
        pref, _ = UserPreference.objects.get_or_create(user=request.user, organization=org, defaults={})
        ser = UserPreferenceWriteSerializer(pref, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(UserPreferenceSerializer(pref).data)


@extend_schema(
    tags=["i18n"],
    parameters=[OpenApiParameter("lang", str, required=False)],
)
class I18nStringsView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = EmptySchemaSerializer

    def get(self, request):
        lang = request.query_params.get("lang") or "en"
        org = get_user_primary_organization(request.user)
        oid = org.id if org else None
        strings = get_strings_for_locale(organization_id=oid, lang=lang)
        return Response({"lang": lang, "strings": strings})


@extend_schema(
    tags=["ux"],
    parameters=[
        OpenApiParameter("role", str, required=False),
        OpenApiParameter("lang", str, required=False),
    ],
)
class GuidedFormsSchemaView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = EmptySchemaSerializer

    def get(self, request):
        role = request.query_params.get("role") or request.user.role
        lang = request.query_params.get("lang") or "en"
        return Response(guided_forms_for_role(role=role, lang=lang))


@extend_schema(
    tags=["analytics"],
    parameters=[
        OpenApiParameter("from", str, required=False),
        OpenApiParameter("to", str, required=False),
    ],
)
class AnalyticsUxTasksExportView(APIView):
    permission_classes = [IsAuthenticated, IsAuditorOrAdmin]
    serializer_class = EmptySchemaSerializer

    def get(self, request):
        from apps.worldready.models import TaskCompletionLog

        org = require_organization(request.user)
        qs = TaskCompletionLog.objects.filter(organization=org)
        p_from = request.query_params.get("from")
        p_to = request.query_params.get("to")
        if p_from:
            qs = qs.filter(started_at__gte=p_from)
        if p_to:
            qs = qs.filter(started_at__lte=p_to)
        rows = qs.order_by("-started_at")[:5000]
        data = [
            {
                "task_name": r.task_name,
                "channel": r.channel,
                "success": r.success,
                "error_code": r.error_code,
                "started_at": r.started_at.isoformat(),
                "completed_at": r.completed_at.isoformat() if r.completed_at else None,
            }
            for r in rows
        ]
        return Response({"results": data, "count": len(data)})


@extend_schema(tags=["surveys"])
class SusSurveySendHookView(APIView):
    """Record SUS delivery intent + optional immediate response."""

    permission_classes = [IsAuthenticated]
    serializer_class = EmptySchemaSerializer

    def post(self, request):
        org = require_organization(request.user)
        log_support_request(
            organization=org,
            user=request.user,
            channel=request.data.get("channel") or "flutter",
            request_type="SUS_SEND",
            body_preview="survey_invite",
        )
        return Response({"status": "logged", "message": "Deliver survey link via your messaging channel."})


@extend_schema(tags=["surveys"])
class SusSurveyResponseView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = SusSurveySerializer

    def post(self, request):
        org = require_organization(request.user)
        ser = SusSurveySerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        SusSurveyResponse.objects.create(
            organization=org,
            user=request.user,
            channel=ser.validated_data.get("channel") or "flutter",
            scores_json=ser.validated_data.get("scores_json") or {},
        )
        return Response({"status": "ok"}, status=status.HTTP_201_CREATED)
