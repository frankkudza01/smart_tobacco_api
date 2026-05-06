"""
Strip secrets and provider URLs from strings that may be shown to clients or stored in logs.

Never pass raw HTTPError / request exception text to API responses.
"""

from __future__ import annotations

import re

# Google API keys in query strings (prefix AIza).
_GOOGLE_API_KEY_PARAM = re.compile(r"([?&])key=AIza[0-9A-Za-z\-_]+", re.IGNORECASE)
_OPENAI_SK = re.compile(r"sk-[a-zA-Z0-9]{20,}")
_BEARER = re.compile(r"Bearer\s+[A-Za-z0-9\-_.=]+", re.IGNORECASE)


def sanitize_ai_error_message(text: str | None, *, max_length: int = 400) -> str:
    if not text:
        return ""
    t = str(text).strip()
    t = _GOOGLE_API_KEY_PARAM.sub(r"\1key=<redacted>", t)
    t = _OPENAI_SK.sub("sk-<redacted>", t)
    t = _BEARER.sub("Bearer <redacted>", t)
    # Long provider URLs often carry repeated key material in error dumps.
    t = re.sub(
        r"https?://generativelanguage\.googleapis\.com[^\s]*",
        "https://generativelanguage.googleapis.com/<redacted>",
        t,
        flags=re.IGNORECASE,
    )
    t = re.sub(r"https?://api\.openai\.com[^\s]*", "https://api.openai.com/<redacted>", t, flags=re.IGNORECASE)
    if len(t) > max_length:
        t = t[: max_length - 1] + "…"
    return t
