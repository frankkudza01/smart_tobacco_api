import logging

from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.views import exception_handler

logger = logging.getLogger(__name__)


class ServiceException(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "A service error occurred."
    default_code = "service_error"


class ConflictException(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "Resource conflict."
    default_code = "conflict"


class BlockchainException(APIException):
    status_code = status.HTTP_502_BAD_GATEWAY
    default_detail = "Blockchain operation failed."
    default_code = "blockchain_error"


class AIServiceException(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "AI service unavailable."
    default_code = "ai_service_error"


def custom_exception_handler(exc, context):
    from apps.common.api_envelope import drf_errors_to_list, error_envelope

    response = exception_handler(exc, context)
    request = context.get("request")
    request_id = getattr(request, "request_id", None) if request else None
    meta = {"request_id": request_id} if request_id else {}

    if response is not None:
        status_code = response.status_code
        raw = response.data
        if isinstance(raw, dict) and "success" in raw and "errors" in raw:
            if request_id and "request_id" not in raw.get("meta", {}):
                raw.setdefault("meta", {})["request_id"] = request_id
            return response

        errors: list[dict]
        if isinstance(raw, dict):
            if "detail" in raw and len(raw) <= 3:
                detail = raw["detail"]
                if not isinstance(detail, str):
                    detail = str(detail)
                code = getattr(exc, "default_code", None) or "api_error"
                errors = [{"code": str(code), "message": detail, "field": None}]
            else:
                errors = drf_errors_to_list(raw)
        elif isinstance(raw, list):
            errors = [
                {"code": "api_error", "message": str(item), "field": None}
                for item in raw
            ]
        else:
            errors = [{"code": "api_error", "message": str(raw), "field": None}]

        response.data = error_envelope(
            errors,
            meta=meta,
            status_code=status_code,
        )
        return response

    logger.exception("Unhandled exception in %s", context.get("view"))
    return response
