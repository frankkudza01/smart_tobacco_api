"""HTTP helpers with timeouts and exponential backoff retries."""

from __future__ import annotations

import logging
import re
import time
from typing import Any

import requests
from requests import Response

logger = logging.getLogger(__name__)

_APPID_QUERY_RE = re.compile(r"([?&]appid=)[^&]*", re.IGNORECASE)


def redact_url_for_log(url: str) -> str:
    """Mask API keys in query strings before logging."""
    return _APPID_QUERY_RE.sub(r"\1***", url)


def request_with_retries(
    method: str,
    url: str,
    *,
    timeout: float,
    max_retries: int = 3,
    backoff_base: float = 0.5,
    log_label: str = "http",
    **kwargs: Any,
) -> Response:
    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            resp = requests.request(method, url, timeout=timeout, **kwargs)
            if resp.status_code in (429, 500, 502, 503, 504) and attempt < max_retries:
                wait = backoff_base * (2**attempt)
                logger.warning(
                    "%s retryable status=%s attempt=%s wait=%.2fs url=%s",
                    log_label,
                    resp.status_code,
                    attempt + 1,
                    wait,
                    redact_url_for_log(url),
                )
                time.sleep(wait)
                continue
            return resp
        except (requests.Timeout, requests.ConnectionError) as exc:
            last_exc = exc
            safe_url = redact_url_for_log(url)
            if attempt >= max_retries:
                logger.warning(
                    "%s transport failed after %s attempts url=%s err=%s",
                    log_label,
                    max_retries + 1,
                    safe_url,
                    exc,
                )
                raise
            wait = backoff_base * (2**attempt)
            logger.debug(
                "%s transport error attempt=%s/%s wait=%.2fs url=%s err=%s",
                log_label,
                attempt + 1,
                max_retries + 1,
                wait,
                safe_url,
                exc,
            )
            time.sleep(wait)
    if last_exc:
        raise last_exc
    raise RuntimeError("request_with_retries: unreachable")
