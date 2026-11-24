"""Authenticated encryption for stored datasource credentials.

Unprefixed values are legacy XOR records. They remain readable only so an
operator can migrate them without silently losing existing connections.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import get_settings

_PREFIX = "aesgcm:v1:"
_AAD = b"knowledge:datasource:credential:v1"
_NONCE_BYTES = 12
SENSITIVE_PARAM_KEYS = frozenset({"password", "pwd", "credential", "secret", "token"})


def _derive_key(secret: str | None = None) -> bytes:
    raw = (secret if secret is not None else get_settings().crypto_key).encode()
    return hashlib.sha256(raw).digest()


def is_legacy_ciphertext(ciphertext: str) -> bool:
    return not ciphertext.startswith(_PREFIX)


def encrypt(plaintext: str, *, key: str | None = None) -> str:
    """Encrypt with a fresh nonce and authenticate the ciphertext and format."""
    nonce = os.urandom(_NONCE_BYTES)
    encrypted = AESGCM(_derive_key(key)).encrypt(nonce, plaintext.encode(), _AAD)
    return _PREFIX + base64.b64encode(nonce + encrypted).decode()


def decrypt(ciphertext: str, *, key: str | None = None) -> str:
    """Read current AES-GCM records or legacy XOR records awaiting migration."""
    try:
        if ciphertext.startswith(_PREFIX):
            payload = base64.b64decode(ciphertext[len(_PREFIX) :], validate=True)
            if len(payload) < _NONCE_BYTES + 16:
                raise ValueError("Invalid credential ciphertext")
            plaintext = AESGCM(_derive_key(key)).decrypt(
                payload[:_NONCE_BYTES], payload[_NONCE_BYTES:], _AAD
            )
            return plaintext.decode()
        legacy = base64.b64decode(ciphertext, validate=True)
        derived = _derive_key(key)
        plaintext = bytes(b ^ derived[i % len(derived)] for i, b in enumerate(legacy))
        return plaintext.decode()
    except (binascii.Error, UnicodeDecodeError, InvalidTag) as exc:
        raise ValueError("Invalid credential ciphertext") from exc


def mask_credential(params: dict) -> dict:
    """Mask legacy embedded secrets until their migration is applied."""
    return {
        name: "***" if name.lower() in SENSITIVE_PARAM_KEYS else value
        for name, value in params.items()
    }
