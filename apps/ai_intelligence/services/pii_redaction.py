"""
Redact PII before any outbound LLM call. Conservative patterns; extend for locale-specific IDs.
"""
from __future__ import annotations

import json
import re
from typing import Any

_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_PHONE = re.compile(
    r"(?:\+?\d{1,3}[-.\s]?)?(?:\(?\d{2,4}\)?[-.\s]?)?\d{3}[-.\s]?\d{3,4}[-.\s]?\d{3,6}\b"
)
_ZW_NATIONAL_ID = re.compile(r"\b\d{2}-\d{6,7}[A-Za-z]?\d?\b")
_ACCOUNT = re.compile(r"\b(?:account|acct|iban)[\s#:]*[A-Za-z0-9-]{8,}\b", re.I)
_STREETISH = re.compile(
    r"\b\d{1,5}\s+[A-Za-z0-9.'\-\s]{3,40}(?:street|st\.|road|rd\.|avenue|ave|close|drive|dr)\b",
    re.I,
)


def redact_text(text: str | None) -> str:
    if not text:
        return ""
    s = str(text)
    s = _EMAIL.sub("[REDACTED_EMAIL]", s)
    s = _PHONE.sub("[REDACTED_PHONE]", s)
    s = _ZW_NATIONAL_ID.sub("[REDACTED_ID]", s)
    s = _ACCOUNT.sub("[REDACTED_ACCOUNT]", s)
    s = _STREETISH.sub("[REDACTED_ADDRESS]", s)
    return s


def redact_structure(obj: Any, max_depth: int = 8) -> Any:
    """Recursively redact strings in dict/list structures."""
    if max_depth <= 0:
        return "[REDACTED_DEPTH]"
    if obj is None:
        return None
    if isinstance(obj, str):
        return redact_text(obj)
    if isinstance(obj, (int, float, bool)):
        return obj
    if isinstance(obj, dict):
        return {str(k): redact_structure(v, max_depth - 1) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [redact_structure(x, max_depth - 1) for x in obj]
    return obj


def redact_json_str(payload: str) -> str:
    try:
        data = json.loads(payload)
        return json.dumps(redact_structure(data))
    except (json.JSONDecodeError, TypeError):
        return redact_text(payload)


def looks_like_prompt_injection(text: str) -> bool:
    t = (text or "").lower()
    needles = (
        "ignore previous",
        "ignore all previous",
        "disregard previous",
        "system prompt",
        "you are now",
        "reveal the",
        "show me the database",
        "sql query",
        "api key",
        "openai_api",
        "password",
        "jwt secret",
        "other users",
        "dump all",
        "exfiltrate",
    )
    return any(n in t for n in needles)
