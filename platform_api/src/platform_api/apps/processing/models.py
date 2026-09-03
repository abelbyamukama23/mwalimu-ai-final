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


class StructureNodeType(models.TextChoices):
    """Supported structural node classifications for document hierarchy."""

    DOCUMENT = "document", "Document"
    PART = "part", "Part"
    CHAPTER = "chapter", "Chapter"
    SECTION = "section", "Section"
    SUBSECTION = "subsection", "Subsection"
    APPENDIX = "appendix", "Appendix"
    FRONT_MATTER = "front_matter", "Front Matter"
    BACK_MATTER = "back_matter", "Back Matter"
    OTHER = "other", "Other"


class DocumentStructureNode(models.Model):
    """A structural hierarchy node (chapter, section, part, etc.) in a document."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    processing_run = models.ForeignKey(
        ProcessingRun,
        on_delete=models.CASCADE,
        related_name="structure_nodes",
        db_index=True,
    )
    resource = models.ForeignKey(
        "resources.Resource",
        on_delete=models.CASCADE,
        related_name="structure_nodes",
        db_index=True,
    )
    library = models.ForeignKey(
        "libraries.Library",
        on_delete=models.CASCADE,
        related_name="structure_nodes",
        db_index=True,
    )
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="children",
        db_index=True,
    )
    node_type = models.CharField(
        max_length=30,
        choices=StructureNodeType.choices,
        default=StructureNodeType.OTHER,
        db_index=True,
    )
    level = models.PositiveIntegerField(
        default=1,
        help_text="1-based hierarchy depth level (1=top/root level).",
    )
    title = models.CharField(
        max_length=500,
        help_text="Original title/heading of this structural node.",
    )
    normalized_title = models.CharField(
        max_length=500,
        help_text="Canonical normalized title.",
    )
    page_start = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="First page number (1-indexed) containing this structural node.",
    )
    page_end = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Last page number (1-indexed) containing this structural node.",
    )
    sequence = models.PositiveIntegerField(
        help_text="Zero-based sequence order within the processing run.",
    )
    source = models.CharField(
        max_length=50,
        default="native",
        help_text="Source of hierarchy detection (e.g. native, heading_style).",
    )
    confidence = models.FloatField(
        null=True,
        blank=True,
        help_text="Confidence score (0.0 to 1.0) if node was inferred.",
    )
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Arbitrary structural metadata (e.g. outline destination details).",
    )
    created_at = models.DateTimeField(
        default=timezone.now,
        editable=False,
    )

    class Meta:
        """Model metadata and constraints."""

        db_table = "document_structure_node"
        ordering = ["processing_run", "sequence"]
        verbose_name = "document structure node"
        verbose_name_plural = "document structure nodes"
        constraints = [
            models.UniqueConstraint(
                fields=["processing_run", "sequence"],
                name="document_structure_node_run_seq_unique",
                violation_error_message=(
                    "Structure node sequence must be unique per processing run."
                ),
            ),
        ]
        indexes = [
            models.Index(fields=["processing_run", "parent"]),
            models.Index(fields=["resource", "page_start", "page_end"]),
            models.Index(fields=["library", "resource"]),
        ]

    def __str__(self) -> str:
        """Return human-readable representation."""
        return (
            f"DocumentStructureNode(id={self.id}, run={self.processing_run_id}, "
            f"type={self.node_type}, title={self.title!r}, seq={self.sequence})"
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
    structure_node = models.ForeignKey(
        DocumentStructureNode,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="chunks",
        db_index=True,
        help_text="Deepest enclosing structural node for this chunk.",
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


class BookIndexEntry(models.Model):
    """A back-of-book subject index term mapping to target physical document pages."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    processing_run = models.ForeignKey(
        ProcessingRun,
        on_delete=models.CASCADE,
        related_name="index_entries",
        db_index=True,
    )
    resource = models.ForeignKey(
        "resources.Resource",
        on_delete=models.CASCADE,
        related_name="index_entries",
        db_index=True,
    )
    term = models.CharField(
        max_length=255,
        help_text="Original index term text (e.g. 'chemical kinetics').",
    )
    normalized_term = models.CharField(
        max_length=255,
        db_index=True,
        help_text="Canonical normalized term for case/punctuation-insensitive lookup.",
    )
    subterm = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="Optional subentry specification (e.g. 'temperature effects').",
    )
    raw_page_references = models.CharField(
        max_length=255,
        help_text="Raw extracted page reference string (e.g. '6, 27, 103-105').",
    )
    target_physical_pages = models.JSONField(
        default=list,
        help_text="List of resolved 1-based physical page numbers.",
    )
    created_at = models.DateTimeField(
        default=timezone.now,
        editable=False,
    )

    class Meta:
        """Model metadata and constraints."""

        db_table = "book_index_entry"
        ordering = ["processing_run", "normalized_term"]
        verbose_name = "book index entry"
        verbose_name_plural = "book index entries"
        indexes = [
            models.Index(fields=["resource", "normalized_term"]),
            models.Index(fields=["processing_run", "normalized_term"]),
        ]

    def __str__(self) -> str:
        """Return human-readable representation."""
        sub = f" / {self.subterm}" if self.subterm else ""
        return (
            f"BookIndexEntry(id={self.id}, term={self.term!r}{sub}, "
            f"pages={self.target_physical_pages})"
        )


class PageLabelSource(models.TextChoices):
    """Source of page label mapping."""

    NATIVE = "native", "Native PDF /PageLabels"
    DETECTED = "detected", "Header/Footer Inferred"
    DEFAULT = "default", "Default 1:1 Physical"


class DocumentPageMap(models.Model):
    """Maps physical document pages to printed page labels (e.g. physical 12 -> printed '1')."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    processing_run = models.ForeignKey(
        ProcessingRun,
        on_delete=models.CASCADE,
        related_name="page_maps",
        db_index=True,
    )
    resource = models.ForeignKey(
        "resources.Resource",
        on_delete=models.CASCADE,
        related_name="page_maps",
        db_index=True,
    )
    physical_page = models.PositiveIntegerField(
        help_text="1-based physical document page number.",
    )
    printed_label = models.CharField(
        max_length=50,
        db_index=True,
        help_text="Printed page label (e.g. '1', 'iv', 'A-1', 'cover').",
    )
    normalized_label = models.CharField(
        max_length=50,
        db_index=True,
        help_text="Normalized page label for case/punctuation-insensitive lookup.",
    )
    source = models.CharField(
        max_length=20,
        choices=PageLabelSource.choices,
        default=PageLabelSource.DEFAULT,
        help_text="Source of page mapping.",
    )
    created_at = models.DateTimeField(
        default=timezone.now,
        editable=False,
    )

    class Meta:
        """Model metadata and constraints."""

        db_table = "document_page_map"
        ordering = ["processing_run", "physical_page"]
        verbose_name = "document page map"
        verbose_name_plural = "document page maps"
        constraints = [
            models.UniqueConstraint(
                fields=["processing_run", "physical_page"],
                name="document_page_map_run_physical_unique",
                violation_error_message="Physical page must be unique per processing run.",
            ),
        ]
        indexes = [
            models.Index(fields=["resource", "normalized_label"]),
            models.Index(fields=["processing_run", "normalized_label"]),
        ]

    def __str__(self) -> str:
        """Return human-readable representation."""
        return (
            f"DocumentPageMap(run={self.processing_run_id}, "
            f"physical={self.physical_page} -> label={self.printed_label!r}, source={self.source})"
        )


