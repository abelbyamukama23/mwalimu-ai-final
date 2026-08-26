"""Data models for durable agent sessions, run records, and canonical transcripts.

Models defined here:
- AgentSession: persistent multi-turn conversational thread.
- AgentRunRecord: durable system-of-record ledger of dispatched agent executions.
- AgentSessionMessage: individual messages in the canonical session transcript.
"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

# ---------------------------------------------------------------------------
# Choice enumerations
# ---------------------------------------------------------------------------


class AgentSessionStatus(models.TextChoices):
    """Lifecycle statuses for an agent session."""

    ACTIVE = "active", "Active"
    ARCHIVED = "archived", "Archived"


class AgentRunStatus(models.TextChoices):
    """Lifecycle statuses for an agent run record."""

    CREATED = "created", "Created"
    QUEUED = "queued", "Queued"
    RUNNING = "running", "Running"
    AWAITING_INPUT = "awaiting_input", "Awaiting Input"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"
    CANCELLED = "cancelled", "Cancelled"
    TIMED_OUT = "timed_out", "Timed Out"


TERMINAL_STATUSES: frozenset[str] = frozenset(
    {
        AgentRunStatus.COMPLETED,
        AgentRunStatus.FAILED,
        AgentRunStatus.CANCELLED,
        AgentRunStatus.TIMED_OUT,
    }
)


class MessageRole(models.TextChoices):
    """Roles for messages in the canonical session transcript."""

    USER = "user", "User"
    ASSISTANT = "assistant", "Assistant"
    SYSTEM = "system", "System"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class AgentSession(models.Model):
    """A persistent multi-turn conversational thread.

    Scoped to an authenticated user and an institution context. Optionally
    bound to a primary library for targeted knowledge retrieval.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="agent_sessions",
    )
    institution = models.ForeignKey(
        "institutions.Institution",
        on_delete=models.CASCADE,
        related_name="agent_sessions",
        null=True,
        blank=True,
        help_text=(
            "The institution context for this session. Null for memberless users "
            "who only have access to platform/public knowledge."
        ),
    )
    primary_library = models.ForeignKey(
        "libraries.Library",
        on_delete=models.SET_NULL,
        related_name="agent_sessions",
        null=True,
        blank=True,
    )
    title = models.CharField(max_length=255)
    status = models.CharField(
        max_length=20,
        choices=AgentSessionStatus.choices,
        default=AgentSessionStatus.ACTIVE,
        db_index=True,
    )
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Arbitrary session configuration and preferences.",
    )

    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        """Model metadata and constraints."""

        db_table = "agents_session"
        ordering = ["-updated_at"]
        verbose_name = "agent session"
        verbose_name_plural = "agent sessions"
        indexes = [
            models.Index(fields=["user", "-updated_at"]),
            models.Index(fields=["institution", "-updated_at"]),
        ]

    def __str__(self) -> str:
        """Return a human-readable session description."""
        return f"AgentSession({self.id}, user={self.user_id}, title={self.title!r})"


class AgentRunRecord(models.Model):
    """Durable system-of-record ledger of a dispatched agent execution.

    Tracks the full lifecycle from creation through terminal status,
    including prompt, answer, citations, token accounting, and timing.
    The watchdog reconciliation task depends on the distinction between
    queued_at (when the run entered the queue) and started_at (when
    execution actually began).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(
        AgentSession,
        on_delete=models.CASCADE,
        related_name="runs",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="agent_runs",
    )
    prompt = models.TextField(
        help_text="User prompt that initiated this run.",
    )
    status = models.CharField(
        max_length=20,
        choices=AgentRunStatus.choices,
        default=AgentRunStatus.CREATED,
        db_index=True,
    )

    # Terminal result fields
    answer = models.TextField(
        null=True,
        blank=True,
        help_text="Final synthesized answer from the agent.",
    )
    citations = models.JSONField(
        default=list,
        blank=True,
        help_text="List of 14-field citation evidence objects.",
    )
    error_code = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        help_text="Machine-readable failure code.",
    )
    error_message = models.TextField(
        null=True,
        blank=True,
        help_text="Human-readable error details.",
    )

    # Execution metrics
    step_count = models.PositiveIntegerField(
        default=0,
        help_text="Number of reasoning steps executed.",
    )
    prompt_tokens = models.PositiveIntegerField(
        default=0,
        help_text="Total prompt tokens consumed.",
    )
    completion_tokens = models.PositiveIntegerField(
        default=0,
        help_text="Total completion tokens consumed.",
    )
    total_tokens = models.PositiveIntegerField(
        default=0,
        help_text="Total tokens consumed (prompt + completion).",
    )

    # Execution configuration
    timeout_seconds = models.FloatField(
        default=60.0,
        help_text="Maximum execution time budget in seconds.",
    )
    max_steps = models.PositiveIntegerField(
        default=10,
        help_text="Maximum reasoning steps allowed.",
    )

    # Lifecycle timestamps (S7-10: distinguish queue time from execution time)
    created_at = models.DateTimeField(
        default=timezone.now,
        editable=False,
    )
    queued_at = models.DateTimeField(
        default=timezone.now,
        editable=False,
        help_text="When the run entered the dispatch queue.",
    )
    started_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When execution actually began in the Agent Service.",
    )
    finished_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the run reached a terminal status.",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        """Model metadata and constraints."""

        db_table = "agents_run_record"
        ordering = ["-created_at"]
        verbose_name = "agent run record"
        verbose_name_plural = "agent run records"
        indexes = [
            models.Index(fields=["session", "-created_at"]),
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["status", "queued_at"]),
            models.Index(fields=["status", "started_at"]),
        ]

    @property
    def is_terminal(self) -> bool:
        """Return True if the run has reached a terminal status."""
        return self.status in TERMINAL_STATUSES

    def __str__(self) -> str:
        """Return a human-readable run record description."""
        return (
            f"AgentRunRecord({self.id}, session={self.session_id}, "
            f"status={self.status})"
        )


class AgentSessionMessage(models.Model):
    """An individual message in the canonical durable session transcript.

    The Platform API owns the canonical transcript. The Agent Service
    receives only a runtime history projection and manages context-window
    token budgeting. Sequence ordering within a session is enforced by
    a unique database constraint.

    Invariant B: A single AgentRunRecord may produce AT MOST ONE terminal
    assistant transcript message. This is enforced by a conditional unique
    constraint on (run) WHERE role='assistant' AND run IS NOT NULL.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(
        AgentSession,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    run = models.ForeignKey(
        AgentRunRecord,
        on_delete=models.SET_NULL,
        related_name="messages",
        null=True,
        blank=True,
        help_text="The agent run that produced this message, if applicable.",
    )
    role = models.CharField(
        max_length=20,
        choices=MessageRole.choices,
        db_index=True,
    )
    content = models.TextField(
        help_text="Message text content.",
    )
    citations = models.JSONField(
        default=list,
        blank=True,
        help_text="Citation evidence attached to this message.",
    )
    sequence = models.PositiveIntegerField(
        help_text="Zero-based ordering position within the session transcript.",
    )

    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        """Model metadata and constraints."""

        db_table = "agents_session_message"
        ordering = ["session", "sequence"]
        verbose_name = "agent session message"
        verbose_name_plural = "agent session messages"
        constraints = [
            # Invariant A: deterministic ordering — no duplicate sequence numbers.
            models.UniqueConstraint(
                fields=["session", "sequence"],
                name="agents_message_session_sequence_unique",
                violation_error_message=(
                    "A message with this sequence number already exists in the session."
                ),
            ),
            # Invariant B: at most one assistant transcript result per run.
            models.UniqueConstraint(
                fields=["run"],
                condition=models.Q(role="assistant", run__isnull=False),
                name="agents_message_one_assistant_per_run_unique",
                violation_error_message=(
                    "Only one assistant message is allowed per agent run."
                ),
            ),
        ]

    def __str__(self) -> str:
        """Return a human-readable message description."""
        return (
            f"AgentSessionMessage(id={self.id}, session={self.session_id}, "
            f"seq={self.sequence}, role={self.role})"
        )
