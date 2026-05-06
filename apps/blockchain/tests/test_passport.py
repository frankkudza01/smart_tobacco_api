"""Pure-function tests for the HMAC-signed bale passport (no DB / chain needed)."""
from __future__ import annotations

import json

import pytest
from django.conf import settings


@pytest.fixture(autouse=True)
def _passport_secret(settings):
    settings.BLOCKCHAIN_PASSPORT_HMAC_SECRET = "test-passport-secret"
    yield


def test_sign_and_verify_round_trip():
    """A token signed by the service must verify true with the same secret."""
    from apps.blockchain.passport_service import _sign_payload, _verify_signature

    payload = {
        "schema": "smart-tobacco.passport.v1",
        "lot_id": "00000000-0000-0000-0000-000000000001",
        "bale_index": 3,
    }
    token = _sign_payload(payload)
    decoded, ok = _verify_signature(token)
    assert ok is True
    assert decoded == payload


def test_tampered_payload_fails_verification():
    """Mutating the payload section invalidates the HMAC."""
    from apps.blockchain.passport_service import _sign_payload, _verify_signature

    token = _sign_payload({"lot_id": "abc"})
    body_b64, sig_b64 = token.split(".", 1)
    forged = "X" + body_b64[1:] + "." + sig_b64
    _, ok = _verify_signature(forged)
    assert ok is False


def test_tampered_signature_fails_verification():
    from apps.blockchain.passport_service import _sign_payload, _verify_signature

    token = _sign_payload({"lot_id": "abc"})
    body_b64, sig_b64 = token.split(".", 1)
    forged = body_b64 + "." + ("A" * len(sig_b64))
    _, ok = _verify_signature(forged)
    assert ok is False


def test_secret_change_invalidates_token(settings):
    """If the operator rotates the HMAC secret, old tokens must stop verifying."""
    from apps.blockchain.passport_service import _sign_payload, _verify_signature

    token = _sign_payload({"lot_id": "abc"})
    settings.BLOCKCHAIN_PASSPORT_HMAC_SECRET = "rotated-secret"
    _, ok = _verify_signature(token)
    assert ok is False
