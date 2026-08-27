"""Django admin configuration for resources."""

from __future__ import annotations

from django.contrib import admin
from django.db.models import QuerySet
from django.http import HttpRequest

from platform_api.apps.admin_ui import RESOURCE_STATUS_TONE, pill

from .models import Resource


@admin.register(Resource)
class ResourceAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    """Admin configuration for Resource."""

    list_display = (
        "name",
        "resource_type",
        "library",
        "status_badge",
        "size",
        "content_type",
        "created_by",
        "created_at",
        "updated_at",
    )
    list_filter = (
        "resource_type",
        "status",
        "created_at",
        "library__institution",
    )
    search_fields = (
        "name",
        "original_filename",
        "object_key",
        "library__name",
        "created_by__email",
    )
    ordering = ("-created_at",)
    readonly_fields = (
        "id",
        "object_key",
        "checksum",
        "size",
        "created_at",
        "updated_at",
    )
    autocomplete_fields = ("library", "created_by")
    save_on_top = True
    list_select_related = ("library", "created_by", "library__institution")

    @admin.action(description="Enqueue knowledge processing")
    def enqueue_processing(
        self, request: HttpRequest, queryset: QuerySet[Resource]
    ) -> None:
        """Kick off ingestion/indexing for the selected resources."""
        from platform_api.apps.processing.services import enqueue_processing

        enqueued = 0
        for resource in queryset:
            try:
                enqueue_processing(resource)
                enqueued += 1
            except Exception:
                continue
        self.message_user(
            request,
            f"Enqueued processing for {enqueued} of {queryset.count()} resources.",
        )

    actions = [enqueue_processing]

    @admin.display(description="Status")
    def status_badge(self, obj: Resource) -> str:
        return pill(obj.status, RESOURCE_STATUS_TONE.get(obj.status, "muted"))
