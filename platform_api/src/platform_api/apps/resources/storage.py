"""Object-storage abstraction for the Mwalimu Platform API.

The domain layer depends on the ``ObjectStorage`` interface, not on a concrete
S3 or MinIO implementation. This keeps the Resource domain portable across
S3-compatible providers.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import BinaryIO

from django.conf import settings
from django.utils.module_loading import import_string


@dataclass
class StoredObject:
    """Metadata returned after a successful storage operation."""

    content_type: str
    size: int
    checksum: str | None = None


class ObjectStorage(ABC):
    """Abstract object-storage backend.

    Implementations must be safe to instantiate from Django settings and must
    not leak credentials through exceptions or reprs.
    """

    @abstractmethod
    def upload(
        self,
        key: str,
        content: BinaryIO,
        content_type: str,
        size: int,
    ) -> StoredObject:
        """Upload ``content`` to ``key`` and return stored metadata."""

    @abstractmethod
    def download(self, key: str) -> BinaryIO:
        """Return a readable stream for the object at ``key``."""

    @abstractmethod
    def delete(self, key: str) -> None:
        """Delete the object at ``key``.

        Deleting a non-existent key should not raise an error.
        """

    @abstractmethod
    def exists(self, key: str) -> bool:
        """Return True if an object exists at ``key``."""


def get_object_storage() -> ObjectStorage:
    """Return the configured object-storage backend instance."""
    backend_path = getattr(
        settings,
        "OBJECT_STORAGE_BACKEND",
        "platform_api.apps.resources.s3_storage.S3Storage",
    )
    # Support both storage.S3Storage and s3_storage.S3Storage paths
    if backend_path == "platform_api.apps.resources.storage.S3Storage":
        backend_path = "platform_api.apps.resources.s3_storage.S3Storage"
    cls = import_string(backend_path)
    backend = cls()
    return backend  # type: ignore[no-any-return]


# Re-export for backwards compatibility
from .s3_storage import S3Storage  # noqa: E402

