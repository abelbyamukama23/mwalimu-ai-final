"""S3-compatible object-storage implementation."""

from __future__ import annotations

from io import BytesIO
from typing import Any, BinaryIO

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from django.conf import settings

from .storage import ObjectStorage, StoredObject


class S3Storage(ObjectStorage):
    """S3-compatible object-storage backend.

    Works with MinIO locally and remains compatible with AWS S3,
    Cloudflare R2, and other S3-compatible providers.
    """

    def __init__(self) -> None:
        """Initialize the S3 client from Django settings."""
        self.bucket_name: str = getattr(
            settings,
            "OBJECT_STORAGE_BUCKET",
            "mwalimu",
        )
        self.endpoint_url: str | None = getattr(
            settings,
            "OBJECT_STORAGE_ENDPOINT",
            None,
        )
        if self.endpoint_url == "":
            self.endpoint_url = None

        self.client = boto3.client(
            "s3",
            endpoint_url=self.endpoint_url,
            region_name=getattr(settings, "OBJECT_STORAGE_REGION", None) or None,
            aws_access_key_id=getattr(settings, "OBJECT_STORAGE_ACCESS_KEY", None),
            aws_secret_access_key=getattr(
                settings,
                "OBJECT_STORAGE_SECRET_KEY",
                None,
            ),
            config=Config(
                # Some S3-compatible providers (e.g., MinIO) do not support
                # virtual-hosted style requests on localhost.
                s3={"addressing_style": "path"},
            ),
        )

    def _client_kwargs(self) -> dict[str, Any]:
        """Return base kwargs for every S3 operation."""
        return {"Bucket": self.bucket_name}

    def upload(
        self,
        key: str,
        content: BinaryIO,
        content_type: str,
        size: int,
    ) -> StoredObject:
        """Upload ``content`` to ``key`` and return stored metadata."""
        self.client.upload_fileobj(
            content,
            self.bucket_name,
            key,
            ExtraArgs={"ContentType": content_type},
        )
        return StoredObject(content_type=content_type, size=size)

    def download(self, key: str) -> BinaryIO:
        """Return a readable stream for the object at ``key``."""
        buffer = BytesIO()
        self.client.download_fileobj(self.bucket_name, key, buffer)
        buffer.seek(0)
        return buffer

    def delete(self, key: str) -> None:
        """Delete the object at ``key`` if it exists."""
        try:
            self.client.delete_object(
                Bucket=self.bucket_name,
                Key=key,
            )
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code", "Unknown")
            if error_code != "NoSuchKey":
                raise

    def exists(self, key: str) -> bool:
        """Return True if an object exists at ``key``."""
        try:
            self.client.head_object(
                Bucket=self.bucket_name,
                Key=key,
            )
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code", "Unknown")
            if error_code in ("404", "NoSuchKey"):
                return False
            raise
        return True
