"""
Per-user ECDSA keypair management for off-chain co-signed custody transfers.

Why this exists
---------------
Custody transfers are non-repudiable real-world events ("I, the farmer, hand
this lot to that buyer"). To make the on-chain ``CustodyTransferred`` event
**provably** authorised by both parties — not just by the operator running the
backend — both parties' signatures over a canonical payload must be verifiable
afterwards. We use **secp256k1 ECDSA + EIP-191 personal_sign** so the
signatures are recoverable to their Ethereum-style addresses with the same
algorithm a regulator would use.

Storage
-------
Private keys are encrypted with **Fernet** at rest. The Fernet key is derived
from ``settings.SECRET_KEY`` via SHA-256 → urlsafe-base64, so no extra
secret-management dependency is required. If you rotate ``SECRET_KEY`` you
must also re-wrap every ``UserSigningKey``.
"""
from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.db import IntegrityError, transaction
from eth_account import Account
from eth_account.messages import encode_defunct

from apps.blockchain.models import UserSigningKey


def _fernet() -> Fernet:
    raw = settings.SECRET_KEY.encode("utf-8")
    key = base64.urlsafe_b64encode(hashlib.sha256(raw).digest())
    return Fernet(key)


def _create_keypair_for_user(user) -> UserSigningKey:
    acct = Account.create()
    encrypted = _fernet().encrypt(acct.key)
    try:
        return UserSigningKey.objects.create(
            user=user,
            address=acct.address,
            encrypted_private_key=encrypted,
        )
    except IntegrityError:
        # Race: another request created it concurrently.
        return UserSigningKey.objects.get(user=user)


def get_or_create_signing_key(user) -> UserSigningKey:
    """Return (and lazily create) the user's signing keypair."""
    with transaction.atomic():
        existing = UserSigningKey.objects.filter(user=user).first()
        if existing is not None:
            return existing
        return _create_keypair_for_user(user)


def get_address(user) -> str:
    return get_or_create_signing_key(user).address


def _decrypt_private_key(signing_key: UserSigningKey) -> bytes:
    try:
        return _fernet().decrypt(bytes(signing_key.encrypted_private_key))
    except InvalidToken as exc:
        raise ValueError(
            "Stored signing key cannot be decrypted with current SECRET_KEY. "
            "Did SECRET_KEY rotate without re-wrapping signing keys?"
        ) from exc


def sign_message_for_user(user, message: str) -> tuple[str, str]:
    """Sign ``message`` with the user's keypair using EIP-191 personal_sign.

    Returns ``(address, signature_hex)``. The signature can be verified
    standalone by anyone (including the smart contract) using the same library.
    """
    signing_key = get_or_create_signing_key(user)
    private_key = _decrypt_private_key(signing_key)
    signed = Account.sign_message(encode_defunct(text=message), private_key=private_key)
    sig_hex = signed.signature.hex()
    if not sig_hex.startswith("0x"):
        sig_hex = "0x" + sig_hex
    return signing_key.address, sig_hex


def verify_signature(*, message: str, signature: str, expected_address: str) -> bool:
    """Recover the signer address from ``signature`` over ``message`` and compare."""
    try:
        recovered = Account.recover_message(encode_defunct(text=message), signature=signature)
    except Exception:  # noqa: BLE001 — recovery raises a wide variety of errors
        return False
    return recovered.lower() == (expected_address or "").lower()


__all__ = [
    "get_or_create_signing_key",
    "get_address",
    "sign_message_for_user",
    "verify_signature",
]
