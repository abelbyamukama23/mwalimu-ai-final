"""Django admin configuration for memberships."""

from django.contrib import admin

from .models import Membership


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    """Admin configuration for Membership."""

    list_display = ("user", "institution", "role", "status", "created_at", "updated_at")
    list_filter = ("role", "status", "created_at")
    search_fields = ("user__email", "institution__name", "institution__slug")
    ordering = ("-created_at",)
    readonly_fields = ("created_at", "updated_at")
    autocomplete_fields = ("user", "institution")
