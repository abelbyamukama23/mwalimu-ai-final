"""Django admin configuration for libraries."""

from django.contrib import admin

from .models import Library, LibraryAccessPolicy


@admin.register(Library)
class LibraryAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    """Admin configuration for Library."""

    list_display = (
        "name",
        "slug",
        "institution",
        "status",
        "visibility",
        "created_at",
        "updated_at",
    )
    list_filter = ("status", "visibility", "created_at", "institution")
    search_fields = ("name", "slug", "institution__name", "institution__slug")
    ordering = ("-created_at",)
    readonly_fields = ("created_at", "updated_at")
    prepopulated_fields = {"slug": ("name",)}
    autocomplete_fields = ("institution",)


@admin.register(LibraryAccessPolicy)
class LibraryAccessPolicyAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    """Admin configuration for LibraryAccessPolicy."""

    list_display = (
        "user",
        "library",
        "role",
        "created_at",
        "updated_at",
    )
    list_filter = ("role", "created_at", "library__institution")
    search_fields = (
        "user__email",
        "library__name",
        "library__slug",
    )
    ordering = ("-created_at",)
    readonly_fields = ("created_at", "updated_at")
    autocomplete_fields = ("user", "library")
