"""Django admin registration for Mwalimu context domain models."""

from __future__ import annotations

from django.contrib import admin

from platform_api.apps.admin_ui import CONTEXT_SCOPE_TONE, pill

from .models import (
    ContextDomain,
    ContextResource,
    GeographicUnit,
    InstitutionContextRegion,
    UserFamiliarRegion,
)


@admin.register(GeographicUnit)
class GeographicUnitAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    """Admin configuration for GeographicUnit."""

    list_display = (
        "name",
        "slug",
        "unit_type",
        "parent",
        "country_code",
        "status_badge",
        "created_at",
        "updated_at",
    )
    list_filter = ("unit_type", "status", "country_code")
    search_fields = ("name", "slug")
    ordering = ("name",)
    readonly_fields = ("created_at", "updated_at")
    prepopulated_fields = {"slug": ("name",)}
    autocomplete_fields = ("parent",)
    list_select_related = ("parent",)

    @admin.display(description="Status")
    def status_badge(self, obj: GeographicUnit) -> str:
        return pill(obj.status, "ok" if obj.status == "active" else "muted")


@admin.register(ContextDomain)
class ContextDomainAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    """Admin configuration for ContextDomain."""

    list_display = ("name", "slug", "created_at", "updated_at")
    search_fields = ("name", "slug")
    ordering = ("name",)
    readonly_fields = ("created_at", "updated_at")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(ContextResource)
class ContextResourceAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    """Admin configuration for ContextResource."""

    list_display = (
        "title",
        "geographic_unit",
        "context_domain",
        "scope_badge",
        "institution",
        "status_badge",
        "created_at",
    )
    list_filter = (
        "scope_type",
        "status",
        "context_domain",
        "geographic_unit__unit_type",
    )
    search_fields = ("title", "content", "source_reference")
    ordering = ("-created_at",)
    readonly_fields = ("created_at", "updated_at")
    autocomplete_fields = ("geographic_unit", "context_domain", "institution")
    list_select_related = ("geographic_unit", "context_domain", "institution")

    @admin.display(description="Scope")
    def scope_badge(self, obj: ContextResource) -> str:
        return pill(obj.scope_type, CONTEXT_SCOPE_TONE.get(obj.scope_type, "muted"))

    @admin.display(description="Status")
    def status_badge(self, obj: ContextResource) -> str:
        return pill(obj.status, "ok" if obj.status == "active" else "muted")


@admin.register(UserFamiliarRegion)
class UserFamiliarRegionAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    """Admin configuration for UserFamiliarRegion."""

    list_display = ("user", "geographic_unit", "priority", "created_at")
    list_filter = ("priority", "geographic_unit__unit_type")
    search_fields = ("user__email", "geographic_unit__name")
    ordering = ("priority", "-created_at")
    readonly_fields = ("created_at", "updated_at")
    autocomplete_fields = ("user", "geographic_unit")


@admin.register(InstitutionContextRegion)
class InstitutionContextRegionAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    """Admin configuration for InstitutionContextRegion."""

    list_display = ("institution", "geographic_unit", "priority", "created_at")
    list_filter = ("priority", "geographic_unit__unit_type")
    search_fields = ("institution__name", "geographic_unit__name")
    ordering = ("priority", "-created_at")
    readonly_fields = ("created_at", "updated_at")
    autocomplete_fields = ("institution", "geographic_unit")
