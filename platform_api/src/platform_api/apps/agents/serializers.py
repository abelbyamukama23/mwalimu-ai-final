"""Serializers for public agent sessions, runs, and completion synchronization."""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from platform_api.apps.institutions.models import Institution
from platform_api.apps.libraries.authz import (
    can_access_library,
    is_active_institution_member,
)
from platform_api.apps.libraries.models import Library, LibraryStatus
from platform_api.apps.memberships.models import Membership, MembershipStatus

from .models import (
    TERMINAL_STATUSES,
    AgentRunRecord,
    AgentRunStatus,
    AgentSession,
    AgentSessionMessage,
    AgentSessionStatus,
)

# ---------------------------------------------------------------------------
# Public Session Serializers
# ---------------------------------------------------------------------------


class SessionCreateRequestSerializer(serializers.Serializer[dict[str, Any]]):
    """Request serializer for creating a new AgentSession."""

    title = serializers.CharField(
        max_length=255,
        required=False,
        default="New Session",
        allow_blank=True,
    )
    institution_id = serializers.UUIDField(
        required=False,
        allow_null=True,
        default=None,
    )
    primary_library_id = serializers.UUIDField(
        required=False,
        allow_null=True,
        default=None,
    )
    metadata = serializers.JSONField(
        required=False,
        default=dict,
    )

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        """Validate institution membership and optional primary_library access."""
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            raise serializers.ValidationError("Authentication required.")

        institution_id = attrs.get("institution_id")
        institution: Institution | None
        if institution_id is not None:
            if not is_active_institution_member(user, institution_id):
                raise serializers.ValidationError(
                    {
                        "institution_id": (
                            "You do not have an active membership in this institution."
                        )
                    }
                )
            try:
                institution = Institution.objects.get(pk=institution_id)
            except Institution.DoesNotExist:
                raise serializers.ValidationError(
                    {"institution_id": "Institution not found."}
                ) from None
        else:
            # No explicit institution selected: prefer the user's first active
            # membership; otherwise create a MEMBERLESS session (institution=None)
            # that has access only to platform/public knowledge.
            memberships = list(
                Membership.objects.filter(
                    user=user, status=MembershipStatus.ACTIVE
                ).select_related("institution")
            )
            institution = memberships[0].institution if memberships else None

        attrs["_resolved_institution"] = institution

        primary_library_id = attrs.get("primary_library_id")
        if primary_library_id is not None:
            if institution is None:
                raise serializers.ValidationError(
                    {
                        "primary_library_id": (
                            "A memberless session has no authorized institution "
                            "available for library access."
                        )
                    }
                )
            try:
                library = Library.objects.get(
                    pk=primary_library_id, status=LibraryStatus.ACTIVE
                )
            except Library.DoesNotExist:
                raise serializers.ValidationError(
                    {"primary_library_id": "Library not found or inactive."}
                ) from None

            if library.institution_id != institution.pk:
                raise serializers.ValidationError(
                    {
                        "primary_library_id": (
                            "Library does not belong to the selected institution."
                        )
                    }
                )

            if not can_access_library(user, library):
                raise serializers.ValidationError(
                    {
                        "primary_library_id": (
                            "You do not have permission to access this library."
                        )
                    }
                )

            attrs["_resolved_primary_library"] = library
        else:
            attrs["_resolved_primary_library"] = None

        return attrs


class SessionMessageResponseSerializer(serializers.ModelSerializer):  # type: ignore[type-arg]
    """Public serializer for canonical transcript messages."""

    run_id = serializers.UUIDField(source="run.id", read_only=True, allow_null=True)

    class Meta:
        model = AgentSessionMessage
        fields = [
            "id",
            "sequence",
            "role",
            "content",
            "citations",
            "run_id",
            "created_at",
        ]
        read_only_fields = fields


class SessionResponseSerializer(serializers.ModelSerializer):  # type: ignore[type-arg]
    """Public serializer for AgentSession summaries."""

    institution_id = serializers.UUIDField(read_only=True)
    primary_library_id = serializers.UUIDField(read_only=True, allow_null=True)

    class Meta:
        model = AgentSession
        fields = [
            "id",
            "institution_id",
            "primary_library_id",
            "title",
            "status",
            "metadata",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class SessionDetailResponseSerializer(SessionResponseSerializer):
    """Public serializer for full AgentSession detail with transcript."""

    messages = SessionMessageResponseSerializer(many=True, read_only=True)

    class Meta(SessionResponseSerializer.Meta):
        fields = SessionResponseSerializer.Meta.fields + ["messages"]
        read_only_fields = fields


class SessionUpdateRequestSerializer(serializers.ModelSerializer[AgentSession]):
    """Request serializer for partial session updates (rename and archive)."""

    class Meta:
        model = AgentSession
        fields = ["title", "status"]
        extra_kwargs = {
            "title": {"required": False, "allow_blank": False},
            "status": {"required": False},
        }

    def validate_title(self, value: str) -> str:
        """Reject blank or whitespace-only conversation titles."""
        stripped = (value or "").strip()
        if not stripped:
            raise serializers.ValidationError(
                "Conversation title cannot be empty."
            )
        return stripped

    def validate_status(self, value: str) -> str:
        """Restrict status to active/archived lifecycle transitions."""
        if value not in (
            AgentSessionStatus.ACTIVE,
            AgentSessionStatus.ARCHIVED,
        ):
            raise serializers.ValidationError(
                "Conversation status must be 'active' or 'archived'."
            )
        return value


# ---------------------------------------------------------------------------
# Public Run Serializers
# ---------------------------------------------------------------------------

KNOWN_TOOLS = frozenset({"calculator", "knowledge_search"})


class CreateRunRequestSerializer(serializers.Serializer[dict[str, Any]]):
    """Request serializer for submitting a prompt to an AgentSession."""

    prompt = serializers.CharField(
        min_length=1,
        max_length=50000,
        required=True,
    )
    max_steps = serializers.IntegerField(
        min_value=1,
        max_value=50,
        default=10,
        required=False,
    )
    timeout_seconds = serializers.FloatField(
        min_value=1.0,
        max_value=300.0,
        default=60.0,
        required=False,
    )
    token_budget = serializers.IntegerField(
        min_value=100,
        max_value=32000,
        default=4000,
        required=False,
    )
    locale = serializers.CharField(
        max_length=10,
        default="en",
        required=False,
    )
    tool_allowlist = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        allow_null=True,
        default=None,
    )
    knowledge_scope = serializers.ChoiceField(
        choices=["relevant", "my", "institution", "public"],
        required=False,
        default="relevant",
    )

    def validate_tool_allowlist(self, value: list[str] | None) -> list[str] | None:
        """Ensure tool_allowlist contains only recognized tool names."""
        if value is None:
            return None
        for tool_name in value:
            if tool_name not in KNOWN_TOOLS:
                raise serializers.ValidationError(
                    f"Unknown tool '{tool_name}'. Allowed tools: {sorted(KNOWN_TOOLS)}"
                )
        return value


class StreamingDescriptorSerializer(serializers.Serializer[dict[str, Any]]):
    """Additive descriptor providing SSE connection details and capability token."""

    sse_url = serializers.CharField(
        help_text="Direct W3C SSE endpoint URL for streaming execution events."
    )
    ticket = serializers.CharField(
        help_text="Short-lived Domain S stream capability token."
    )
    expires_in = serializers.IntegerField(
        help_text="Ticket validity lifetime in seconds."
    )


class RunResponseSerializer(serializers.ModelSerializer):  # type: ignore[type-arg]
    """Public serializer for durable AgentRunRecord state."""

    session_id = serializers.UUIDField(read_only=True)
    streaming = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = AgentRunRecord
        fields = [
            "id",
            "session_id",
            "status",
            "prompt",
            "answer",
            "citations",
            "error_code",
            "error_message",
            "step_count",
            "prompt_tokens",
            "completion_tokens",
            "total_tokens",
            "timeout_seconds",
            "max_steps",
            "created_at",
            "queued_at",
            "started_at",
            "finished_at",
            "updated_at",
            "streaming",
        ]
        read_only_fields = fields

    def get_streaming(self, obj: AgentRunRecord) -> dict[str, Any] | None:
        """Return streaming connection details if populated on the instance."""
        streaming_data = getattr(obj, "streaming", None)
        if not streaming_data or not isinstance(streaming_data, dict):
            return None
        serializer = StreamingDescriptorSerializer(data=streaming_data)
        if serializer.is_valid():
            result: dict[str, Any] = dict(serializer.validated_data)
            return result
        return None


# ---------------------------------------------------------------------------
# Internal Completion Serializers (Domain D)
# ---------------------------------------------------------------------------


class RunCompletionCitationSerializer(serializers.Serializer[dict[str, Any]]):
    """Serializer for 14-field citation evidence payloads."""

    resource_id = serializers.UUIDField()
    resource_name = serializers.CharField(max_length=255)
    library_id = serializers.UUIDField()
    library_name = serializers.CharField(max_length=255)
    page_start = serializers.IntegerField(allow_null=True, required=False, default=None)
    page_end = serializers.IntegerField(allow_null=True, required=False, default=None)
    section = serializers.CharField(
        allow_null=True, required=False, allow_blank=True, default=None
    )
    sequence = serializers.IntegerField(default=0)
    char_start = serializers.IntegerField(default=0)
    char_end = serializers.IntegerField(default=0)
    content_sha256 = serializers.CharField(default="", allow_blank=True)
    chunk_id = serializers.UUIDField(allow_null=True, required=False, default=None)
    score = serializers.FloatField(allow_null=True, required=False, default=None)


class RunCompletionRequestSerializer(serializers.Serializer[dict[str, Any]]):
    """Serializer for the Agent Service -> Platform API internal completion payload."""

    status = serializers.ChoiceField(choices=AgentRunStatus.choices)
    answer = serializers.CharField(
        allow_null=True, required=False, allow_blank=True, default=None
    )
    citations = serializers.ListField(
        child=RunCompletionCitationSerializer(),
        required=False,
        default=list,
    )
    error_code = serializers.CharField(
        max_length=100,
        allow_null=True,
        required=False,
        allow_blank=True,
        default=None,
    )
    error_message = serializers.CharField(
        allow_null=True,
        required=False,
        allow_blank=True,
        default=None,
    )
    step_count = serializers.IntegerField(min_value=0, default=0)
    prompt_tokens = serializers.IntegerField(min_value=0, default=0)
    completion_tokens = serializers.IntegerField(min_value=0, default=0)
    total_tokens = serializers.IntegerField(min_value=0, default=0)
    started_at = serializers.DateTimeField(
        allow_null=True, required=False, default=None
    )
    finished_at = serializers.DateTimeField(
        allow_null=True, required=False, default=None
    )

    def validate_status(self, value: str) -> str:
        """Validate that the incoming status is a terminal state."""
        if value not in TERMINAL_STATUSES:
            raise serializers.ValidationError(
                f"Status '{value}' is not a valid terminal status. "
                f"Expected one of: {sorted(TERMINAL_STATUSES)}"
            )
        return value
