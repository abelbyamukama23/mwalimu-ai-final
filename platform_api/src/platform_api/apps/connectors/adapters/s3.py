"""Amazon S3 connector adapter for bucket knowledge ingestion."""

from __future__ import annotations

import hashlib
import io
import logging
from typing import TYPE_CHECKING, Any

import boto3
from botocore.exceptions import ClientError

from platform_api.apps.processing.services import enqueue_processing
from platform_api.apps.resources.models import Resource, ResourceStatus, ResourceType
from platform_api.apps.resources.object_key import generate_resource_object_key
from platform_api.apps.resources.storage import get_object_storage

from .base import BaseConnectorAdapter, SyncResult

if TYPE_CHECKING:
    from platform_api.apps.connectors.models import Connection, ConnectionSyncJob

logger = logging.getLogger(__name__)


def _infer_resource_type(filename: str) -> tuple[str, str]:
    """Infer ResourceType and content_type from file extension."""
    lower = filename.lower()
    if lower.endswith(".pdf"):
        return ResourceType.PDF, "application/pdf"
    elif lower.endswith(".docx"):
        return (
            ResourceType.DOCX,
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    return ResourceType.TXT, "text/plain; charset=utf-8"


class S3Adapter(BaseConnectorAdapter):
    """Adapter to ingest documents and files from an AWS S3 bucket."""

    def __init__(self, s3_client: Any | None = None) -> None:
        """Initialize adapter with optional client injection for testing."""
        self._custom_client = s3_client

    def _get_client(
        self, config: dict[str, Any], creds: dict[str, Any]
    ) -> Any:
        """Construct boto3 S3 client."""
        if self._custom_client is not None:
            return self._custom_client

        region = config.get("region", "us-east-1")
        access_key = creds.get("aws_access_key_id") or creds.get("access_key")
        secret_key = creds.get("aws_secret_access_key") or creds.get("secret_key")

        client_kwargs: dict[str, Any] = {"region_name": region}
        if access_key and secret_key:
            client_kwargs["aws_access_key_id"] = access_key
            client_kwargs["aws_secret_access_key"] = secret_key

        return boto3.client("s3", **client_kwargs)

    def test_connection(self, connection: Connection) -> bool:
        """Validate bucket reachability and credentials."""
        config = connection.configuration or {}
        bucket_name = config.get("bucket_name")
        if not bucket_name:
            return False

        creds = connection.get_credentials()
        try:
            client = self._get_client(config, creds)
            client.head_bucket(Bucket=bucket_name)
            return True
        except Exception as exc:
            logger.warning("S3 connection test failed for bucket '%s': %s", bucket_name, exc)
            return False

    def sync(
        self,
        connection: Connection,
        sync_job: ConnectionSyncJob,
    ) -> SyncResult:
        """Scan S3 bucket prefix and ingest supported documents into library."""
        config = connection.configuration or {}
        bucket_name = config.get("bucket_name")
        prefix = config.get("prefix", "")
        if not bucket_name:
            return SyncResult(
                error_code="INVALID_CONFIG",
                error_message="Missing required 'bucket_name' in connection configuration.",
            )

        creds = connection.get_credentials()
        storage = get_object_storage()
        library = connection.library
        creator = connection.created_by or library.institution.users.first()
        result = SyncResult()

        try:
            client = self._get_client(config, creds)
            paginator = client.get_paginator("list_objects_v2")
            page_iterator = paginator.paginate(Bucket=bucket_name, Prefix=prefix)

            for page in page_iterator:
                for obj in page.get("Contents", []):
                    key = obj.get("Key", "")
                    # Skip directory markers
                    if key.endswith("/") or not key:
                        continue

                    # Filter for supported document types (.pdf, .docx, .txt)
                    if not any(
                        key.lower().endswith(ext) for ext in (".pdf", ".docx", ".txt")
                    ):
                        continue

                    result.resources_discovered += 1

                    # Download object binary
                    try:
                        resp = client.get_object(Bucket=bucket_name, Key=key)
                        file_bytes = resp["Body"].read()
                    except ClientError as client_err:
                        logger.warning("Failed to download S3 object '%s': %s", key, client_err)
                        continue

                    checksum = hashlib.sha256(file_bytes).hexdigest()
                    res_type, content_type = _infer_resource_type(key)

                    # Extract readable file basename
                    base_name = key.split("/")[-1]
                    display_name = f"[S3] {base_name}"[:255]
                    key_hash = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
                    safe_filename = f"s3_{key_hash}_{base_name}"

                    # Check for existing resource
                    existing_resource = Resource.objects.filter(
                        library=library,
                        original_filename=safe_filename,
                    ).first()

                    if existing_resource:
                        if existing_resource.checksum == checksum:
                            continue  # Idempotent skip

                        existing_resource.name = display_name
                        existing_resource.size = len(file_bytes)
                        existing_resource.checksum = checksum
                        existing_resource.status = ResourceStatus.READY
                        existing_resource.save(
                            update_fields=[
                                "name",
                                "size",
                                "checksum",
                                "status",
                                "updated_at",
                            ]
                        )

                        storage.upload(
                            existing_resource.object_key,
                            io.BytesIO(file_bytes),
                            content_type=content_type,
                            size=len(file_bytes),
                        )
                        enqueue_processing(existing_resource)
                        result.resources_updated += 1
                    else:
                        new_resource = Resource.objects.create(
                            library=library,
                            name=display_name,
                            resource_type=res_type,
                            original_filename=safe_filename,
                            content_type=content_type,
                            size=len(file_bytes),
                            object_key="pending",
                            checksum=checksum,
                            status=ResourceStatus.READY,
                            created_by=creator,
                        )
                        new_resource.object_key = generate_resource_object_key(
                            library.id, new_resource.id
                        )
                        new_resource.save(update_fields=["object_key"])

                        storage.upload(
                            new_resource.object_key,
                            io.BytesIO(file_bytes),
                            content_type=content_type,
                            size=len(file_bytes),
                        )
                        enqueue_processing(new_resource)
                        result.resources_created += 1

        except Exception as exc:
            logger.exception(
                "S3 sync failed for connection %s: %s", connection.id, exc
            )
            return SyncResult(
                resources_discovered=result.resources_discovered,
                resources_created=result.resources_created,
                resources_updated=result.resources_updated,
                resources_deleted=result.resources_deleted,
                error_code="SYNC_FAILED",
                error_message=str(exc),
            )

        return result
