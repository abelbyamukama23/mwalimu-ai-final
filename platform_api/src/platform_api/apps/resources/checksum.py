"""Content-checksum utilities for resources."""

from __future__ import annotations

import hashlib
from typing import BinaryIO


def sha256_checksum(content: BinaryIO, chunk_size: int = 8192) -> str:
    """Return the SHA-256 hex digest of ``content``.

    The stream is read from its current position and is not rewound.
    """
    hasher = hashlib.sha256()
    while True:
        chunk = content.read(chunk_size)
        if not chunk:
            break
        hasher.update(chunk)
    return hasher.hexdigest()
