"""AgentRun entity and 8-state finite state machine."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum

from .context import ExecutionContext
from .message import EvidenceCitation


class RunStatus(str, Enum):
    """The 8 formal lifecycle states for an AgentRun."""

    CREATED = "created"
    QUEUED = "queued"
    RUNNING = "running"
    AWAITING_INPUT = "awaiting_input"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


TERMINAL_STATES: frozenset[RunStatus] = frozenset(
    [
        RunStatus.COMPLETED,
        RunStatus.FAILED,
        RunStatus.CANCELLED,
        RunStatus.TIMED_OUT,
    ]
)


class InvalidStateTransitionError(Exception):
    """Raised when an illegal state transition is attempted on an AgentRun."""

    def __init__(self, from_state: RunStatus, to_state: RunStatus, msg: str = ""):
        self.from_state = from_state
        self.to_state = to_state
        super().__init__(
            msg
            or f"Invalid state transition from {from_state.value} to {to_state.value}."
        )


@dataclass
class AgentRun:
    """A single execution instance of an agent task governed by an 8-state machine.

    Attributes:
        id: Unique identifier for this run (matches context.agent_run_id).
        context: Immutable execution context.
        status: Current state in the 8-state machine.
        prompt: Initial user input prompt.
        answer: Final synthesized answer if completed.
        citations: Grounded citation provenance list.
        error_code: Machine-readable error code if failed or timed out.
        error_message: Human-readable error message.
        step_count: Number of reasoning loop cycles executed.
        total_prompt_tokens: Accumulated prompt tokens across all model calls.
        total_completion_tokens: Accumulated completion tokens across all model calls.
        created_at: Run creation timestamp.
        started_at: Execution start timestamp.
        finished_at: Terminal completion/failure timestamp.
    """

    id: uuid.UUID
    context: ExecutionContext
    status: RunStatus = RunStatus.CREATED
    prompt: str = ""
    answer: str | None = None
    citations: list[EvidenceCitation] = field(default_factory=list)
    error_code: str | None = None
    error_message: str | None = None
    step_count: int = 0
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    finished_at: datetime | None = None

    def __post_init__(self) -> None:
        """Ensure id matches context correlation id."""
        if self.id != self.context.agent_run_id:
            raise ValueError(
                f"AgentRun.id ({self.id}) must match context.agent_run_id "
                f"({self.context.agent_run_id})."
            )

    @property
    def is_terminal(self) -> bool:
        """Return True if the run has reached a terminal immutable state."""
        return self.status in TERMINAL_STATES

    @property
    def elapsed_seconds(self) -> float:
        """Return execution duration in seconds."""
        if self.started_at is None:
            return 0.0
        end = self.finished_at or datetime.now(UTC)
        return (end - self.started_at).total_seconds()

    def dispatch(self) -> None:
        """Transition from CREATED -> QUEUED."""
        if self.status != RunStatus.CREATED:
            raise InvalidStateTransitionError(self.status, RunStatus.QUEUED)
        self.status = RunStatus.QUEUED

    def start(self) -> None:
        """Transition from QUEUED -> RUNNING."""
        if self.status != RunStatus.QUEUED:
            raise InvalidStateTransitionError(self.status, RunStatus.RUNNING)
        self.status = RunStatus.RUNNING
        self.started_at = datetime.now(UTC)

    def record_step(self, prompt_tokens: int = 0, completion_tokens: int = 0) -> None:
        """Increment step count and record token usage while RUNNING."""
        if self.status != RunStatus.RUNNING:
            raise InvalidStateTransitionError(
                self.status, self.status, "Cannot record step when not RUNNING."
            )
        self.step_count += 1
        self.total_prompt_tokens += prompt_tokens
        self.total_completion_tokens += completion_tokens

    def request_input(self) -> None:
        """Transition from RUNNING -> AWAITING_INPUT."""
        if self.status != RunStatus.RUNNING:
            raise InvalidStateTransitionError(self.status, RunStatus.AWAITING_INPUT)
        self.status = RunStatus.AWAITING_INPUT

    def provide_input(self) -> None:
        """Transition from AWAITING_INPUT -> RUNNING."""
        if self.status != RunStatus.AWAITING_INPUT:
            raise InvalidStateTransitionError(self.status, RunStatus.RUNNING)
        self.status = RunStatus.RUNNING

    def complete(
        self,
        answer: str,
        citations: list[EvidenceCitation] | None = None,
    ) -> None:
        """Transition from RUNNING -> COMPLETED."""
        if self.status != RunStatus.RUNNING:
            raise InvalidStateTransitionError(self.status, RunStatus.COMPLETED)
        self.status = RunStatus.COMPLETED
        self.answer = answer
        if citations:
            self.citations.extend(citations)
        self.finished_at = datetime.now(UTC)

    def fail(self, error_code: str, error_message: str) -> None:
        """Transition from active state -> FAILED."""
        if self.is_terminal:
            raise InvalidStateTransitionError(
                self.status,
                RunStatus.FAILED,
                f"Cannot fail run already in terminal state {self.status.value}.",
            )
        self.status = RunStatus.FAILED
        self.error_code = error_code
        self.error_message = error_message
        self.finished_at = datetime.now(UTC)

    def cancel(self) -> None:
        """Transition from active state -> CANCELLED."""
        if self.is_terminal:
            raise InvalidStateTransitionError(
                self.status,
                RunStatus.CANCELLED,
                f"Cannot cancel run already in terminal state {self.status.value}.",
            )
        self.status = RunStatus.CANCELLED
        self.error_code = "CANCELLED"
        self.error_message = "Execution cancelled by client."
        self.finished_at = datetime.now(UTC)

    def timeout(self, reason: str = "Execution budget exceeded.") -> None:
        """Transition from RUNNING or AWAITING_INPUT -> TIMED_OUT."""
        if self.is_terminal:
            raise InvalidStateTransitionError(
                self.status,
                RunStatus.TIMED_OUT,
                f"Cannot timeout run already in terminal state {self.status.value}.",
            )
        self.status = RunStatus.TIMED_OUT
        self.error_code = "TIMED_OUT"
        self.error_message = reason
        self.finished_at = datetime.now(UTC)
