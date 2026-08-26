"""Data models for connectors, library connections, and synchronization jobs."""

from __future__ import annotations

import uuid
from typing import Any

from django.conf import settings
from django.db import models
from django.utils import timezone

from .crypto import decrypt_credentials, encrypt_credentials
from .validators import validate_data_against_schema, validate_json_schema_definition

# ---------------------------------------------------------------------------
# Choice Enums
# ---------------------------------------------------------------------------


class ConnectorType(models.TextChoices):
    """Supported external connector types."""

    WEB_CRAWLER = "web_crawler", "Web Crawler"
    GOOGLE_DRIVE = "google_drive", "Google Drive"
    NOTION = "notion", "Notion"
    S3 = "s3", "Amazon S3"
    FILE_SYSTEM = "file_system", "File System"
    CUSTOM = "custom", "Custom Adapter"


class ConnectorAuthType(models.TextChoices):
    """Authentication mechanisms required by connectors."""

    NONE = "none", "No Authentication"
    API_KEY = "api_key", "API Key"
    OAUTH2 = "oauth2", "OAuth 2.0"
    BASIC_AUTH = "basic_auth", "Basic Auth"
    BEARER_TOKEN = "bearer_token", "Bearer Token"


class ConnectionStatus(models.TextChoices):
    """Operational lifecycle statuses for a library connection."""

    ACTIVE = "active", "Active"
    INACTIVE = "inactive", "Inactive"
    ERROR = "error", "Error"
    SYNCING = "syncing", "Syncing"


class SyncFrequency(models.TextChoices):
    """Automated synchronization schedules for a connection."""

    MANUAL = "manual", "Manual"
    HOURLY = "hourly", "Hourly"
    DAILY = "daily", "Daily"
    WEEKLY = "weekly", "Weekly"


class SyncStatus(models.TextChoices):
    """Terminal outcomes of a connection sync operation."""

    SUCCESS = "success", "Success"
    PARTIAL = "partial", "Partial Success"
    FAILED = "failed", "Failed"


class SyncJobStatus(models.TextChoices):
    """Execution status of an individual sync job run."""

    QUEUED = "queued", "Queued"
    RUNNING = "running", "Running"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"
    CANCELLED = "cancelled", "Cancelled"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class Connector(models.Model):
    """Global, platform-wide catalog specification of an external knowledge source.

    A Connector contains ZERO credentials. It is a reusable definition of how
    to communicate with an external system, defining configuration schemas,
    authentication types, and adapter specifications.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True, db_index=True)
    description = models.TextField(blank=True, default="")
    connector_type = models.CharField(
        max_length=50,
        choices=ConnectorType.choices,
        db_index=True,
    )
    auth_type = models.CharField(
        max_length=50,
        choices=ConnectorAuthType.choices,
        default=ConnectorAuthType.NONE,
    )
    config_schema = models.JSONField(
        default=dict,
        blank=True,
        help_text="JSON Schema defining connection-level configuration requirements.",
    )
    auth_schema = models.JSONField(
        default=dict,
        blank=True,
        help_text="JSON Schema defining required authentication credentials.",
    )
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        help_text="Whether this connector is available for new library connections.",
    )
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        """Model metadata."""

        db_table = "connectors_connector"
        ordering = ["name"]
        verbose_name = "connector"
        verbose_name_plural = "connectors"
        indexes = [
            models.Index(fields=["connector_type", "is_active"]),
        ]

    def clean(self) -> None:
        """Validate JSON Schema definitions."""
        super().clean()
        if self.config_schema:
            validate_json_schema_definition(
                self.config_schema, field_name="config_schema"
            )
        if self.auth_schema:
            validate_json_schema_definition(self.auth_schema, field_name="auth_schema")

    def __str__(self) -> str:
        """Return the connector display name."""
        return f"{self.name} ({self.connector_type})"


class Connection(models.Model):
    """An instantiated, authenticated link scoped to a specific Library.

    A Connection references a Connector and holds encrypted credentials and
    connection-specific configurations. It belongs to exactly one Library.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    library = models.ForeignKey(
        "libraries.Library",
        on_delete=models.CASCADE,
        related_name="connections",
        db_index=True,
    )
    connector = models.ForeignKey(
        Connector,
        on_delete=models.PROTECT,
        related_name="connections",
        db_index=True,
    )
    name = models.CharField(max_length=255)
    status = models.CharField(
        max_length=20,
        choices=ConnectionStatus.choices,
        default=ConnectionStatus.ACTIVE,
        db_index=True,
    )
    configuration = models.JSONField(
        default=dict,
        blank=True,
        help_text="Connection-specific settings conforming to Connector.config_schema.",
    )
    encrypted_credentials = models.TextField(
        blank=True,
        default="",
        help_text="Encrypted credentials payload.",
    )
    sync_frequency = models.CharField(
        max_length=20,
        choices=SyncFrequency.choices,
        default=SyncFrequency.MANUAL,
    )
    last_synced_at = models.DateTimeField(null=True, blank=True)
    last_sync_status = models.CharField(
        max_length=20,
        choices=SyncStatus.choices,
        null=True,
        blank=True,
    )
    last_sync_error = models.TextField(blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_connections",
    )
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        """Model metadata."""

        db_table = "connectors_connection"
        ordering = ["-created_at"]
        verbose_name = "connection"
        verbose_name_plural = "connections"
        constraints = [
            models.UniqueConstraint(
                fields=["library", "name"],
                name="connectors_connection_library_name_unique",
                violation_error_message=(
                    "A connection with this name already exists in this library."
                ),
            ),
        ]
        indexes = [
            models.Index(fields=["library", "-created_at"]),
            models.Index(fields=["connector", "status"]),
        ]

    def set_credentials(self, credentials: dict[str, Any] | None) -> None:
        """Encrypt and store credentials."""
        self.encrypted_credentials = encrypt_credentials(credentials)

    def get_credentials(self) -> dict[str, Any]:
        """Decrypt and return credentials dictionary."""
        return decrypt_credentials(self.encrypted_credentials)

    @property
    def has_credentials(self) -> bool:
        """Return True if credentials have been configured."""
        return bool(self.encrypted_credentials and self.encrypted_credentials.strip())

    def clean(self) -> None:
        """Validate configuration against connector schema."""
        super().clean()
        if self.connector and self.connector.config_schema:
            validate_data_against_schema(
                self.configuration,
                self.connector.config_schema,
                field_name="configuration",
            )

    def __str__(self) -> str:
        """Return connection display representation."""
        return f"{self.name} [{self.connector.name}] @ {self.library.name}"


class ConnectionSyncJob(models.Model):
    """Observability and execution record of an asynchronous connection sync task."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    connection = models.ForeignKey(
        Connection,
        on_delete=models.CASCADE,
        related_name="sync_jobs",
        db_index=True,
    )
    status = models.CharField(
        max_length=20,
        choices=SyncJobStatus.choices,
        default=SyncJobStatus.QUEUED,
        db_index=True,
    )
    celery_task_id = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="Celery correlation task ID.",
    )
    resources_discovered = models.PositiveIntegerField(
        default=0,
        help_text="Count of remote resources discovered during sync.",
    )
    resources_created = models.PositiveIntegerField(
        default=0,
        help_text="Count of new resources imported.",
    )
    resources_updated = models.PositiveIntegerField(
        default=0,
        help_text="Count of existing resources updated.",
    )
    resources_deleted = models.PositiveIntegerField(
        default=0,
        help_text="Count of stale resources removed.",
    )
    error_code = models.CharField(max_length=100, null=True, blank=True)
    error_message = models.TextField(blank=True, default="")
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        """Model metadata."""

        db_table = "connectors_sync_job"
        ordering = ["-created_at"]
        verbose_name = "connection sync job"
        verbose_name_plural = "connection sync jobs"
        indexes = [
            models.Index(fields=["connection", "-created_at"]),
            models.Index(fields=["status", "-created_at"]),
        ]

    def __str__(self) -> str:
        """Return sync job display description."""
        return (
            f"SyncJob({self.id}, connection={self.connection_id}, status={self.status})"
        )
