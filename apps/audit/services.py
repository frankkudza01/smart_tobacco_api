import logging

from apps.audit.models import AuditLog
from apps.common.middleware import get_request_id

logger = logging.getLogger(__name__)


def log_audit(*, actor=None, action: str, resource_type: str, resource_id: str = "",
              description: str = "", changes: dict | None = None, request=None):
    ip_address = None
    user_agent = ""
    request_id = get_request_id() or ""

    if request:
        ip_address = _get_client_ip(request)
        user_agent = request.META.get("HTTP_USER_AGENT", "")[:500]
        request_id = getattr(request, "request_id", request_id)

    AuditLog.objects.create(
        actor=actor,
        action=action,
        resource_type=resource_type,
        resource_id=str(resource_id),
        description=description,
        changes=changes or {},
        ip_address=ip_address,
        user_agent=user_agent,
        request_id=request_id,
    )


def _get_client_ip(request):
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")
