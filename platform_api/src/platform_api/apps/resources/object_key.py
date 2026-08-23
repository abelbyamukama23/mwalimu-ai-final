"""Safe object-key generation for resources."""

from __future__ import annotations

import uuid


class ObjectKeyError(ValueError):
    """Raised when an object key is invalid or unsafe."""


def generate_resource_object_key(library_id: uuid.UUID, resource_id: uuid.UUID) -> str:
    """Return the canonical storage key for a resource's original binary.

    The key structure is deterministic and scoped to the owning library so that
    path traversal and cross-library key collisions are impossible.
    """
    return f"libraries/{library_id}/resources/{resource_id}/original"


def validate_object_key(key: str, library_id: uuid.UUID) -> None:
    """Raise ObjectKeyError if ``key`` does not belong to ``library_id``."""
    expected_prefix = f"libraries/{library_id}/"
    if not key.startswith(expected_prefix):
        raise ObjectKeyError("Object key does not belong to the library.")
    if ".." in key or key != key.replace("\\", "/"):
        raise ObjectKeyError("Object key contains unsafe path components.")
