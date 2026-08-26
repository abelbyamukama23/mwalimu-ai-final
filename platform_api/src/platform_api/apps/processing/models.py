"""Data models for document processing, chunking, and vector indexing.

Models defined here:
- ProcessingRun: tracks pipeline execution, identity, status, versions.
- DocumentChunk: stores structured chunks derived from a ProcessingRun.
- ChunkEmbedding: stores dense vector representations versioned by model/version.
"""

from __future__ import annotations

import uuid

from django.db import models
from django.utils import timezone
from pgvector.django import HnswIndex, VectorField


class ProcessingStatus(models.TextChoices):
    """Lifecycle statuses for a processing run."""

    QUEUED = "queued", "Queued"
    PROCESSING = "processing", "Processing"
    READY = "ready", "Ready"
    FAILED = "failed", "Failed"


class ProcessingStage(models.TextChoices):
    """Observability stages within a processing run execution."""

    EXTRACT = "extract", "Extract"
    NORMALIZE = "normalize", "Normalize"
    CHUNK = "chunk", "Chunk"
    EMBED = "embed", "Embed"
    INDEX = "index", "Index"
    FINALIZE = "finalize", "Finalize"


class ProcessingRun(models.Model):
    """Execution of a document processing pipeline against a specific resource content.

    A run represents one execution of an extraction, normalization, chunking,
    and embedding pipeline for a specific source checksum and version configuration.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    resource = models.ForeignKey(
        "resources.Resource",
        on_delete=models.CASCADE,
        related_name="processing_runs",
    )
    library = models.ForeignKey(
        "libraries.Library",
        on_delete=models.CASCADE,
        related_name="processing_runs",
        db_index=True,
    )
    status = models.CharField(
        max_length=20,
        choices=ProcessingStatus.choices,
        default=ProcessingStatus.QUEUED,
        db_index=True,
    )
    current_stage = models.CharField(
        max_length=30,
        choices=ProcessingStage.choices,
        null=True,
        blank=True,
    )
    source_checksum = models.CharField(
        max_length=64,
        help_text="SHA-256 hex digest of the resource content at run creation.",
    )
    pipeline_version = models.CharField(
        max_length=50,
        default="1",
        help_text="Version of normalization and orchestration pipeline.",
    )
    extractor_version = models.CharField(
        max_length=50,
        help_text="Version of format-specific extractor module.",
    )
    chunker_version = models.CharField(
        max_length=50,
        default="1",
        help_text="Version and configuration of chunking parameters.",
    )
    embedding_model = models.CharField(
        max_length=100,
        help_text="Provider model identifier (e.g. text-embedding-3-small).",
    )
    embedding_version = models.CharField(
        max_length=50,
        default="1",
        help_text="Generation/version of embeddings for this model.",
    )
    embedding_dimensions = models.PositiveIntegerField(
        help_text="Dimension of embedding vectors produced by provider.",
    )
    is_active = models.BooleanField(
        default=False,
        db_index=True,
        help_text=(
            "True if this is the active searchable processing run for the resource."
        ),
    )
    celery_task_id = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="Celery task correlation ID for observability.",
    )
    attempt_count = models.PositiveIntegerField(
        default=0,
        help_text="Number of execution attempts.",
    )
    error_code = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        help_text="Machine-readable failure code.",
    )
    error_message = models.TextField(
        null=True,
        blank=True,
        help_text="Human-readable error details.",
    )
    queued_at = models.DateTimeField(
        default=timezone.now,
        editable=False,
    )
    started_at = models.DateTimeField(
        null=True,
        blank=True,
    )
    finished_at = models.DateTimeField(
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(
        default=timezone.now,
        editable=False,
    )
    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        """Model metadata and constraints."""

        db_table = "processing_run"
        ordering = ["-created_at"]
        verbose_name = "processing run"
        verbose_name_plural = "processing runs"
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "resource",
                    "source_checksum",
                    "pipeline_version",
                    "extractor_version",
                    "chunker_version",
                    "embedding_model",
                    "embedding_version",
                ],
                condition=~models.Q(status=ProcessingStatus.FAILED),
                name="processing_run_identity_non_failed_unique",
                violation_error_message=(
                    "A non-failed processing run with identical identity already "
                    "exists."
                ),
            ),
            models.UniqueConstraint(
                fields=["resource"],
                condition=models.Q(is_active=True),
                name="processing_run_active_unique",
                violation_error_message=(
                    "Only one processing run can be active per resource."
                ),
            ),
        ]

    def __str__(self) -> str:
        """Return human-readable representation."""
        return (
            f"ProcessingRun({self.id}, resource={self.resource_id}, "
            f"status={self.status}, active={self.is_active})"
        )


class DocumentChunk(models.Model):
    """A deterministic text segment derived from a ProcessingRun with provenance."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    processing_run = models.ForeignKey(
        ProcessingRun,
        on_delete=models.CASCADE,
        related_name="chunks",
    )
    resource = models.ForeignKey(
        "resources.Resource",
        on_delete=models.CASCADE,
        related_name="document_chunks",
        db_index=True,
    )
    library = models.ForeignKey(
        "libraries.Library",
        on_delete=models.CASCADE,
        related_name="document_chunks",
        db_index=True,
    )
    sequence = models.PositiveIntegerField(
        help_text="Zero-based sequence order within the processing run.",
    )
    text = models.TextField(
        help_text="Canonical normalized text content of the chunk.",
    )
    token_count = models.PositiveIntegerField(
        help_text="Estimated token count for budgeting.",
    )
    char_start = models.PositiveIntegerField(
        help_text="Start offset in the full normalized text.",
    )
    char_end = models.PositiveIntegerField(
        help_text="End offset in the full normalized text.",
    )
    page_start = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="First page number (1-indexed) containing this chunk.",
    )
    page_end = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Last page number (1-indexed) containing this chunk.",
    )
    section = models.CharField(
        max_length=500,
        null=True,
        blank=True,
        help_text="Nearest preceding section heading path.",
    )
    content_sha256 = models.CharField(
        max_length=64,
        help_text="SHA-256 hex digest of the chunk text.",
    )
    created_at = models.DateTimeField(
        default=timezone.now,
        editable=False,
    )

    class Meta:
        """Model metadata and constraints."""

        db_table = "document_chunk"
        ordering = ["processing_run", "sequence"]
        verbose_name = "document chunk"
        verbose_name_plural = "document chunks"
        constraints = [
            models.UniqueConstraint(
                fields=["processing_run", "sequence"],
                name="document_chunk_run_sequence_unique",
                violation_error_message=(
                    "Chunk sequence must be unique per processing run."
                ),
            ),
        ]
        indexes = [
            models.Index(fields=["library", "resource"]),
            models.Index(fields=["processing_run", "sequence"]),
        ]

    def __str__(self) -> str:
        """Return human-readable representation."""
        return (
            f"DocumentChunk(id={self.id}, run={self.processing_run_id}, "
            f"seq={self.sequence})"
        )


class ChunkEmbedding(models.Model):
    """Dense vector representation for a DocumentChunk, versioned by model and version.

    A single DocumentChunk may have multiple versioned embeddings across model upgrades.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    chunk = models.ForeignKey(
        DocumentChunk,
        on_delete=models.CASCADE,
        related_name="embeddings",
    )
    vector = VectorField(
        dimensions=1536,
        help_text="Dense vector representation (1536 dims for MVP).",
    )
    embedding_model = models.CharField(
        max_length=100,
        db_index=True,
        help_text="Model identifier used to produce the vector.",
    )
    embedding_version = models.CharField(
        max_length=50,
        default="1",
        db_index=True,
        help_text="Generation/version of embeddings for this model.",
    )
    dimensions = models.PositiveIntegerField(
        help_text="Dimension of the vector as reported by the provider.",
    )
    created_at = models.DateTimeField(
        default=timezone.now,
        editable=False,
    )

    class Meta:
        """Model metadata and constraints."""

        db_table = "chunk_embedding"
        ordering = ["-created_at"]
        verbose_name = "chunk embedding"
        verbose_name_plural = "chunk embeddings"
        constraints = [
            models.UniqueConstraint(
                fields=["chunk", "embedding_model", "embedding_version"],
                name="chunk_embedding_identity_unique",
                violation_error_message=(
                    "An embedding for this chunk, model, and version already exists."
                ),
            ),
        ]
        indexes = [
            HnswIndex(
                name="chunk_embedding_vector_hnsw",
                fields=["vector"],
                opclasses=["vector_cosine_ops"],
                m=16,
                ef_construction=64,
            ),
        ]

    def __str__(self) -> str:
        """Return human-readable representation."""
        return (
            f"ChunkEmbedding(id={self.id}, chunk={self.chunk_id}, "
            f"model={self.embedding_model}, v={self.embedding_version})"
        )
