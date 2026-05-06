"""
Redis-backed OTP service for phone-based authentication.

Redis key schema:
  otp:{phone}:code      -> the hashed OTP code (TTL = OTP_TTL_SECONDS)
  otp:{phone}:attempts  -> attempt counter (TTL = OTP_TTL_SECONDS)
  otp:{phone}:cooldown  -> cooldown flag (TTL = OTP_RESEND_COOLDOWN_SECONDS)
"""
import hashlib
import logging
import secrets

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

PREFIX = "otp"


def _key(phone: str, suffix: str) -> str:
    return f"{PREFIX}:{phone}:{suffix}"


def generate_otp(phone: str) -> tuple[str, str | None]:
    """
    Generate and store an OTP for the given phone number.
    Returns (otp_code, error_message).
    error_message is None on success.
    """
    cooldown_key = _key(phone, "cooldown")
    if cache.get(cooldown_key):
        remaining = cache.ttl(cooldown_key) if hasattr(cache, "ttl") else settings.OTP_RESEND_COOLDOWN_SECONDS
        return "", f"Please wait {remaining}s before requesting a new OTP."

    code_length = settings.OTP_CODE_LENGTH
    code = "".join(secrets.choice("0123456789") for _ in range(code_length))

    code_hash = _hash_code(code)
    ttl = settings.OTP_TTL_SECONDS

    cache.set(_key(phone, "code"), code_hash, timeout=ttl)
    cache.set(_key(phone, "attempts"), 0, timeout=ttl)
    cache.set(cooldown_key, "1", timeout=settings.OTP_RESEND_COOLDOWN_SECONDS)

    if settings.ENABLE_DEV_OTP_LOGGING:
        logger.warning(
            "[DEV OTP] phone=%s code=%s expires_in=%ds  *** NON-PRODUCTION ONLY ***",
            phone, code, ttl,
        )

    return code, None


def verify_otp(phone: str, code: str) -> tuple[bool, str]:
    """
    Verify the OTP code for the given phone number.
    Returns (success, error_message).
    """
    code_key = _key(phone, "code")
    attempts_key = _key(phone, "attempts")

    stored_hash = cache.get(code_key)
    if stored_hash is None:
        return False, "OTP expired or not requested. Please request a new one."

    current_attempts = cache.get(attempts_key) or 0
    if int(current_attempts) >= settings.OTP_MAX_ATTEMPTS:
        _clear_otp(phone)
        return False, "Maximum verification attempts exceeded. Please request a new OTP."

    cache.incr(attempts_key)

    if _hash_code(code) != stored_hash:
        remaining = settings.OTP_MAX_ATTEMPTS - int(current_attempts) - 1
        return False, f"Invalid OTP code. {remaining} attempt(s) remaining."

    _clear_otp(phone)
    return True, ""


def has_active_otp(phone: str) -> bool:
    return cache.get(_key(phone, "code")) is not None


def is_on_cooldown(phone: str) -> bool:
    return cache.get(_key(phone, "cooldown")) is not None


def _clear_otp(phone: str):
    cache.delete(_key(phone, "code"))
    cache.delete(_key(phone, "attempts"))


def _hash_code(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()
