"""Fernet field encryption helpers (versioned keys via PII_ENCRYPTION_KEY)."""
from __future__ import annotations

import base64
import hashlib
import os

from django.conf import settings


def _fernet():
    from cryptography.fernet import Fernet

    key = getattr(settings, "PII_ENCRYPTION_KEY", "") or os.environ.get("PII_ENCRYPTION_KEY", "")
    if not key:
        return None
    raw = key.encode() if isinstance(key, str) else key
    if len(raw) != 44:
        raw = base64.urlsafe_b64encode(hashlib.sha256(raw).digest())
    return Fernet(raw)


def encrypt_value(plain: str) -> str | None:
    if plain is None or plain == "":
        return plain
    f = _fernet()
    if f is None:
        return None
    return f.encrypt(plain.encode("utf-8")).decode("ascii")


def decrypt_value(token: str) -> str | None:
    if not token:
        return token
    f = _fernet()
    if f is None:
        return None
    return f.decrypt(token.encode("ascii")).decode("utf-8")


def hash_lookup_token(normalized_phone: str) -> str:
    return hashlib.sha256(f"phone:{normalized_phone}".encode()).hexdigest()
