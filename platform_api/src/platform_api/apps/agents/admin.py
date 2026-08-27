"""Django admin registration for agent sessions, run records, and messages."""

from __future__ import annotations

from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from platform_api.apps.admin_ui import (
    RUN_STATUS_TONE,
    SESSION_STATUS_TONE,
    pill,
    short,
)

from .models import AgentRunRecord, AgentSession, AgentSessionMessage, MessageRole


def _run_pill(status: str) -> str:
    return pill(
        status,
        RUN_STATUS_TONE.get(status, "muted"),
        title=f"Run status: {status}",
    )


class AgentRunRecordInline(admin.TabularInline):  # type: ignore[type-arg]
    """Read-only inline listing of a session's runs."""

    model = AgentRunRecord
    extra = 0
    can_delete = False
    readonly_fields = (
        "status_badge",
        "step_count",
        "tokens",
        "started_at",
        "finished_at",
    )
    ordering = ("-created_at",)

    @admin.display(description="Status")
    def status_badge(self, obj: AgentRunRecord) -> str:
        return _run_pill(obj.status)

    @admin.display(description="Tokens")
    def tokens(self, obj: AgentRunRecord) -> int:
        return obj.prompt_tokens + obj.completion_tokens


class AgentSessionMessageInline(admin.TabularInline):  # type: ignore[type-arg]
    """Read-only inline transcript for a session."""

    model = AgentSessionMessage
    extra = 0
    can_delete = False
    readonly_fields = ("sequence", "role_badge", "message", "created_at")
    ordering = ("sequence",)

    @admin.display(description="Role")
    def role_badge(self, obj: AgentSessionMessage) -> str:
        return pill(
            obj.role,
            "info" if obj.role == MessageRole.ASSISTANT else "muted",
            title=f"Role: {obj.role}",
        )

    @admin.display(description="Message")
    def message(self, obj: AgentSessionMessage) -> str:
        return short(obj.content, 120)


@admin.register(AgentSession)
class AgentSessionAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    """Admin for persistent agent sessions."""

    list_display = (
        "title",
        "user",
        "status_badge",
        "primary_library",
        "message_count",
        "updated_at",
    )
    list_filter = ("status", "institution", "updated_at")
    search_fields = ("title", "user__email", "institution__name")
    ordering = ("-updated_at",)
    readonly_fields = ("id", "created_at", "updated_at")
    inlines = (AgentRunRecordInline, AgentSessionMessageInline)
    save_on_top = True
    list_select_related = ("user", "primary_library", "institution")
    date_hierarchy = "updated_at"

    @admin.display(description="Status")
    def status_badge(self, obj: AgentSession) -> str:
        return pill(obj.status, SESSION_STATUS_TONE.get(obj.status, "muted"))

    @admin.display(description="Messages")
    def message_count(self, obj: AgentSession) -> int:
        return obj.messages.count()


@admin.register(AgentRunRecord)
class AgentRunRecordAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    """Admin for durable agent run records."""

    list_display = (
        "prompt_short",
        "session",
        "user",
        "status_badge",
        "step_count",
        "total_tokens",
        "created_at",
    )
    list_filter = ("status", "created_at")
    search_fields = ("prompt", "session__title", "user__email", "error_code")
    ordering = ("-created_at",)
    readonly_fields = (
        "id",
        "answer",
        "citations",
        "error_code",
        "error_message",
        "step_count",
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "started_at",
        "finished_at",
        "created_at",
        "queued_at",
        "updated_at",
    )
    autocomplete_fields = ("session", "user")
    save_on_top = True
    list_select_related = ("session", "user")
    date_hierarchy = "created_at"

    @admin.display(description="Prompt")
    def prompt_short(self, obj: AgentRunRecord) -> str:
        return format_html(
            '<a href="{}">{}</a>',
            reverse("admin:agents_agentrunrecord_change", args=[obj.pk]),
            short(obj.prompt, 60),
        )

    @admin.display(description="Status")
    def status_badge(self, obj: AgentRunRecord) -> str:
        return _run_pill(obj.status)


@admin.register(AgentSessionMessage)
class AgentSessionMessageAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    """Admin for canonical session transcript messages."""

    list_display = ("session", "role_badge", "message", "sequence", "created_at")
    list_filter = ("role", "created_at")
    search_fields = ("content", "session__title")
    ordering = ("session", "sequence")
    readonly_fields = ("id", "citations", "created_at")
    autocomplete_fields = ("session", "run")
    list_select_related = ("session", "run")
    date_hierarchy = "created_at"

    @admin.display(description="Role")
    def role_badge(self, obj: AgentSessionMessage) -> str:
        return pill(
            obj.role,
            "info" if obj.role == MessageRole.ASSISTANT else "muted",
            title=f"Role: {obj.role}",
        )

    @admin.display(description="Message")
    def message(self, obj: AgentSessionMessage) -> str:
        return short(obj.content, 80)
