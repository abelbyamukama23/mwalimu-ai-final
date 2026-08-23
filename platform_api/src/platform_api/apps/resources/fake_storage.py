"""In-memory fake object-storage backend for tests."""

from __future__ import annotations

from io import BytesIO
from typing import BinaryIO

from .storage import ObjectStorage, StoredObject


class FakeStorage(ObjectStorage):
    """In-memory object-storage backend.

    Stores object contents in a class-level dictionary so the backend can be
    used across multiple instances in the same process. Safe for unit tests;
    not for production.
    """

    _objects: dict[str, bytes] = {}

    def __init__(self) -> None:
        """Initialize a fake storage instance."""
        self.bucket_name = "fake-bucket"

    @classmethod
    def clear(cls) -> None:
        """Remove all stored objects."""
        cls._objects.clear()

    def upload(
        self,
        key: str,
        content: BinaryIO,
        content_type: str,
        size: int,
    ) -> StoredObject:
        """Upload ``content`` to ``key`` and return stored metadata."""
        data = content.read()
        self._objects[key] = data
        return StoredObject(content_type=content_type, size=len(data))

    def download(self, key: str) -> BinaryIO:
        """Return a readable stream for the object at ``key``."""
        if key not in self._objects:
            raise FileNotFoundError(f"Object not found: {key}")
        return BytesIO(self._objects[key])

    def delete(self, key: str) -> None:
        """Delete the object at ``key`` if it exists."""
        self._objects.pop(key, None)

    def exists(self, key: str) -> bool:
        """Return True if an object exists at ``key``."""
        return key in self._objects
