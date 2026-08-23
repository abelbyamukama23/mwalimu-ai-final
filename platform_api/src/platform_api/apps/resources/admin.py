"""Django admin configuration for resources."""

from django.contrib import admin

from .models import Resource


@admin.register(Resource)
class ResourceAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    """Admin configuration for Resource."""

    list_display = (
        "name",
        "resource_type",
        "library",
        "status",
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
