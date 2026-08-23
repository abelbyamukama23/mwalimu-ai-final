"""Django admin configuration for institutions."""

from django.contrib import admin

from .models import Institution


@admin.register(Institution)
class InstitutionAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    """Admin configuration for Institution."""

    list_display = ("name", "slug", "status", "created_at", "updated_at")
    list_filter = ("status", "created_at")
    search_fields = ("name", "slug")
    ordering = ("-created_at",)
    readonly_fields = ("created_at", "updated_at")
    prepopulated_fields = {"slug": ("name",)}
