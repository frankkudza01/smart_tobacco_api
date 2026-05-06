import threading
import uuid

_request_id_var = threading.local()


def get_request_id():
    return getattr(_request_id_var, "request_id", None)


class RequestIDMiddleware:
    """Attach a unique request_id to every request for tracing and audit correlation."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request.request_id = request_id
        _request_id_var.request_id = request_id
        response = self.get_response(request)
        response["X-Request-ID"] = request_id
        return response


class AuditMiddleware:
    """Lightweight middleware to stash actor info for downstream audit logging."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        return response
