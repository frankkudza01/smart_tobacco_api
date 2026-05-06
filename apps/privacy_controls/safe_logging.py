"""Structured logs with allowlist — never log raw PII buckets."""
from __future__ import annotations

import logging
import re

logger = logging.getLogger("apps.privacy.safe")

_SAFE_KEY_RE = re.compile(r"^(org_id|user_id|task|status|duration_ms|tool_name|request_id)$")


def log_event(event: str, **kwargs):
    safe = {}
    for k, v in kwargs.items():
        if _SAFE_KEY_RE.match(k):
            safe[k] = v
        elif k.endswith("_id") and len(str(v)) < 80:
            safe[k] = str(v)
    logger.info("%s %s", event, safe)
