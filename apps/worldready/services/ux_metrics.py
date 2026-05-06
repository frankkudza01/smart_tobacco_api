from __future__ import annotations

from django.utils import timezone

from apps.common.enums import UXChannel
from apps.worldready.models import SupportRequestLog, TaskCompletionLog


def log_task_completion(
    *,
    organization,
    user,
    channel: str,
    task_name: str,
    started_at,
    success: bool,
    completed_at=None,
    error_code: str = "",
):
    TaskCompletionLog.objects.create(
        organization=organization,
        user=user,
        channel=channel,
        task_name=task_name,
        started_at=started_at,
        completed_at=completed_at or timezone.now(),
        success=success,
        error_code=error_code[:64],
    )


def log_support_request(*, organization, user, channel: str, request_type: str, body_preview: str = ""):
    SupportRequestLog.objects.create(
        organization=organization,
        user=user,
        channel=channel,
        request_type=request_type[:64],
        body_preview=body_preview[:240],
    )
