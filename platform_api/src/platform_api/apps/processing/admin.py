"""Django admin configuration for document processing models."""

from __future__ import annotations

from django.contrib import admin
from django.db.models import QuerySet
from django.http import HttpRequest

from platform_api.apps.admin_ui import PROCESSING_STATUS_TONE, pill

from .models import ChunkEmbedding, DocumentChunk, ProcessingRun


@admin.register(ProcessingRun)
class ProcessingRunAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    """Admin configuration for ProcessingRun."""

    list_display = (
        "id",
        "resource",
        "library",
        "status_badge",
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
        "error_code",
        "error_message",
    )
    autocomplete_fields = ("resource", "library")
    save_on_top = True
    list_select_related = ("resource", "library")

    @admin.action(description="Requeue selected runs")
    def requeue(self, request: HttpRequest, queryset: QuerySet[ProcessingRun]) -> None:
        """Reset runs to queued and re-dispatch the processing task."""
        from .tasks import process_resource_run

        requeued = 0
        for run in queryset:
            try:
                run.status = "queued"
                run.is_active = False
                run.error_code = None
                run.error_message = None
                run.attempt_count = 0
                run.save(
                    update_fields=[
                        "status",
                        "is_active",
                        "error_code",
                        "error_message",
                        "attempt_count",
                        "updated_at",
                    ]
                )
                process_resource_run.delay(str(run.pk))
                requeued += 1
            except Exception:
                continue
        self.message_user(request, f"Requeued {requeued} of {queryset.count()} run(s).")

    actions = [requeue]

    @admin.display(description="Status")
    def status_badge(self, obj: ProcessingRun) -> str:
        return pill(obj.status, PROCESSING_STATUS_TONE.get(obj.status, "muted"))


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
    list_select_related = ("processing_run", "resource", "library")


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
