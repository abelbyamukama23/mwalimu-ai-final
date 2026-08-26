"""Django admin configuration for document processing models."""

from django.contrib import admin

from .models import ChunkEmbedding, DocumentChunk, ProcessingRun


@admin.register(ProcessingRun)
class ProcessingRunAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    """Admin configuration for ProcessingRun."""

    list_display = (
        "id",
        "resource",
        "library",
        "status",
        "current_stage",
        "is_active",
        "embedding_model",
        "embedding_version",
        "attempt_count",
        "created_at",
        "finished_at",
    )
    list_filter = (
        "status",
        "is_active",
        "embedding_model",
        "pipeline_version",
        "created_at",
    )
    search_fields = (
        "id",
        "resource__name",
        "library__name",
        "source_checksum",
        "celery_task_id",
        "error_code",
    )
    ordering = ("-created_at",)
    readonly_fields = (
        "id",
        "source_checksum",
        "created_at",
        "updated_at",
        "queued_at",
    )
    autocomplete_fields = ("resource", "library")


@admin.register(DocumentChunk)
class DocumentChunkAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    """Admin configuration for DocumentChunk."""

    list_display = (
        "id",
        "processing_run",
        "resource",
        "sequence",
        "page_start",
        "page_end",
        "token_count",
        "section",
        "created_at",
    )
    list_filter = ("created_at", "page_start")
    search_fields = (
        "id",
        "text",
        "section",
        "content_sha256",
        "resource__name",
    )
    ordering = ("processing_run", "sequence")
    readonly_fields = ("id", "content_sha256", "created_at")
    autocomplete_fields = ("processing_run", "resource", "library")


@admin.register(ChunkEmbedding)
class ChunkEmbeddingAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    """Admin configuration for ChunkEmbedding."""

    list_display = (
        "id",
        "chunk",
        "embedding_model",
        "embedding_version",
        "dimensions",
        "created_at",
    )
    list_filter = ("embedding_model", "embedding_version", "created_at")
    search_fields = ("id", "chunk__text", "embedding_model")
    ordering = ("-created_at",)
    readonly_fields = ("id", "created_at")
    autocomplete_fields = ("chunk",)
