import hashlib
import re

import phonenumbers


def compute_sha256(file_obj) -> str:
    """Compute SHA-256 hash of a file-like object. Resets seek position after read."""
    sha = hashlib.sha256()
    file_obj.seek(0)
    for chunk in iter(lambda: file_obj.read(8192), b""):
        sha.update(chunk)
    file_obj.seek(0)
    return sha.hexdigest()


def compute_sha256_from_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def normalize_phone_number(phone: str, default_region: str = "ZW") -> str | None:
    """
    Normalize a phone number to E.164 format (+263771234567).
    Returns None if the number is invalid.
    """
    try:
        parsed = phonenumbers.parse(phone, default_region)
        if phonenumbers.is_valid_number(parsed):
            return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
    except phonenumbers.NumberParseException:
        pass
    return None


def format_whatsapp_number(e164_phone: str) -> str:
    """Convert E.164 number to Twilio WhatsApp format: whatsapp:+263..."""
    if e164_phone.startswith("whatsapp:"):
        return e164_phone
    return f"whatsapp:{e164_phone}"
