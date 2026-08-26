"""Cryptographic encryption and decryption for sensitive connection credentials."""

from __future__ import annotations

import base64
import hashlib
import json
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


class CredentialEncryptionError(Exception):
    """Raised when credential encryption fails."""


class CredentialDecryptionError(Exception):
    """Raised when credential decryption fails or tamper detection triggers."""


def _derive_fernet_key() -> bytes:
    """Derive a URL-safe base64-encoded 32-byte Fernet key from Django SECRET_KEY."""
    secret_key = getattr(
        settings,
        "CONNECTOR_SECRET_KEY",
        getattr(settings, "SECRET_KEY", "insecure-default-key"),
    )
    # Derive deterministic 32-byte key via SHA-256
    digest = hashlib.sha256(secret_key.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def encrypt_credentials(credentials: dict[str, Any] | None) -> str:
    """Encrypt a dictionary of credentials into a Fernet ciphertext string.

    Args:
        credentials: Dictionary of sensitive key-values (e.g. API keys, secrets).

    Returns:
        Encrypted base64-encoded ciphertext string, or empty string if empty.
    """
    if not credentials:
        return ""
    try:
        raw_json = json.dumps(credentials, sort_keys=True)
        fernet = Fernet(_derive_fernet_key())
        ciphertext = fernet.encrypt(raw_json.encode("utf-8"))
        return ciphertext.decode("utf-8")
    except Exception as exc:
        raise CredentialEncryptionError(
            f"Failed to encrypt connection credentials: {exc}"
        ) from exc


def decrypt_credentials(encrypted_text: str | None) -> dict[str, Any]:
    """Decrypt a Fernet ciphertext string back into the credentials dictionary.

    Args:
        encrypted_text: Fernet ciphertext string.

    Returns:
        Decrypted credentials dictionary.

    Raises:
        CredentialDecryptionError: If decryption or HMAC integrity verification fails.
    """
    if not encrypted_text:
        return {}
    try:
        fernet = Fernet(_derive_fernet_key())
        decrypted_bytes = fernet.decrypt(encrypted_text.encode("utf-8"))
        data = json.loads(decrypted_bytes.decode("utf-8"))
        if isinstance(data, dict):
            return data
        return {}
    except InvalidToken as exc:
        raise CredentialDecryptionError(
            "Tampered or invalid encrypted credentials payload."
        ) from exc
    except Exception as exc:
        raise CredentialDecryptionError(
            f"Failed to decrypt credentials payload: {exc}"
        ) from exc
