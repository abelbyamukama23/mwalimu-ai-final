"""Unit tests for AgentRun entity and 8-state finite state machine."""

import uuid

import pytest

from agent_service.domain.context import ExecutionContext
from agent_service.domain.message import EvidenceCitation
from agent_service.domain.run import (
    TERMINAL_STATES,
    AgentRun,
    InvalidStateTransitionError,
    RunStatus,
)


@pytest.fixture
def execution_context() -> ExecutionContext:
    """Create a sample ExecutionContext."""
    run_id = uuid.uuid4()
    return ExecutionContext(
        user_id=uuid.uuid4(),
        agent_run_id=run_id,
        session_id=uuid.uuid4(),
        max_steps=5,
        timeout_seconds=30.0,
    )


@pytest.fixture
def agent_run(execution_context: ExecutionContext) -> AgentRun:
    """Create a sample AgentRun in initial CREATED state."""
    return AgentRun(
        id=execution_context.agent_run_id,
        context=execution_context,
        prompt="Explain photosynthesis",
    )


def test_agent_run_initialization(agent_run: AgentRun) -> None:
    """AgentRun initializes in CREATED state with matched correlation IDs."""
    assert agent_run.status == RunStatus.CREATED
    assert agent_run.is_terminal is False
    assert agent_run.step_count == 0
    assert agent_run.total_prompt_tokens == 0
    assert agent_run.total_completion_tokens == 0
    assert agent_run.started_at is None
    assert agent_run.finished_at is None


def test_agent_run_id_must_match_context() -> None:
    """AgentRun.id mismatch with context.agent_run_id raises ValueError."""
    ctx = ExecutionContext(
        user_id=uuid.uuid4(),
        agent_run_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
    )
    with pytest.raises(ValueError, match="must match context.agent_run_id"):
        AgentRun(id=uuid.uuid4(), context=ctx)


def test_happy_path_lifecycle(agent_run: AgentRun) -> None:
    """CREATED -> QUEUED -> RUNNING -> COMPLETED happy path."""
    # 1. Dispatch
    agent_run.dispatch()
    assert agent_run.status == RunStatus.QUEUED
    assert agent_run.is_terminal is False

    # 2. Start
    agent_run.start()
    assert agent_run.status == RunStatus.RUNNING
    assert agent_run.started_at is not None
    assert agent_run.is_terminal is False

    # 3. Record steps
    agent_run.record_step(prompt_tokens=100, completion_tokens=25)
    agent_run.record_step(prompt_tokens=150, completion_tokens=30)
    assert agent_run.step_count == 2
    assert agent_run.total_prompt_tokens == 250
    assert agent_run.total_completion_tokens == 55

    # 4. Complete
    citation = EvidenceCitation(
        resource_id=uuid.uuid4(),
        resource_name="Bio.pdf",
        library_id=uuid.uuid4(),
        library_name="Main Lib",
    )
    agent_run.complete(
        answer="Photosynthesis converts light to glucose.",
        citations=[citation],
    )
    assert agent_run.status == RunStatus.COMPLETED
    assert agent_run.is_terminal is True
    assert agent_run.answer == "Photosynthesis converts light to glucose."
    assert agent_run.citations == [citation]
    assert agent_run.finished_at is not None
    assert agent_run.elapsed_seconds >= 0.0


def test_interactive_awaiting_input_lifecycle(agent_run: AgentRun) -> None:
    """RUNNING -> AWAITING_INPUT -> RUNNING -> COMPLETED."""
    agent_run.dispatch()
    agent_run.start()

    # Request input
    agent_run.request_input()
    assert agent_run.status == RunStatus.AWAITING_INPUT
    assert agent_run.is_terminal is False

    # Provide input
    agent_run.provide_input()
    assert agent_run.status == RunStatus.RUNNING

    agent_run.complete(answer="Final answer after input.")
    assert agent_run.status == RunStatus.COMPLETED


def test_cancellation_from_various_active_states(
    execution_context: ExecutionContext,
) -> None:
    """Cancellation is legal from CREATED, QUEUED, RUNNING, and AWAITING_INPUT."""
    # From CREATED
    run1 = AgentRun(id=execution_context.agent_run_id, context=execution_context)
    run1.cancel()
    assert run1.status == RunStatus.CANCELLED
    assert run1.is_terminal is True

    # From QUEUED
    run2 = AgentRun(id=execution_context.agent_run_id, context=execution_context)
    run2.dispatch()
    run2.cancel()
    assert run2.status == RunStatus.CANCELLED

    # From RUNNING
    run3 = AgentRun(id=execution_context.agent_run_id, context=execution_context)
    run3.dispatch()
    run3.start()
    run3.cancel()
    assert run3.status == RunStatus.CANCELLED

    # From AWAITING_INPUT
    run4 = AgentRun(id=execution_context.agent_run_id, context=execution_context)
    run4.dispatch()
    run4.start()
    run4.request_input()
    run4.cancel()
    assert run4.status == RunStatus.CANCELLED


def test_failure_transitions(agent_run: AgentRun) -> None:
    """fail() transitions active run to FAILED with error code and details."""
    agent_run.dispatch()
    agent_run.start()
    agent_run.fail(
        error_code="MODEL_TIMEOUT",
        error_message="OpenAI API timed out after 30s.",
    )

    assert agent_run.status == RunStatus.FAILED
    assert agent_run.is_terminal is True
    assert agent_run.error_code == "MODEL_TIMEOUT"
    assert agent_run.error_message == "OpenAI API timed out after 30s."
    assert agent_run.finished_at is not None


def test_timeout_transitions(agent_run: AgentRun) -> None:
    """timeout() transitions active run to TIMED_OUT."""
    agent_run.dispatch()
    agent_run.start()
    agent_run.timeout(reason="Max steps budget (5) exceeded.")

    assert agent_run.status == RunStatus.TIMED_OUT
    assert agent_run.is_terminal is True
    assert agent_run.error_code == "TIMED_OUT"
    assert "Max steps budget" in str(agent_run.error_message)


def test_terminal_state_immutability(agent_run: AgentRun) -> None:
    """No transitions are permitted out of terminal states."""
    agent_run.dispatch()
    agent_run.start()
    agent_run.complete(answer="Done.")
    assert agent_run.is_terminal is True

    # Attempting any action on COMPLETED run raises InvalidStateTransitionError
    with pytest.raises(InvalidStateTransitionError):
        agent_run.start()

    with pytest.raises(InvalidStateTransitionError):
        agent_run.complete("Done again.")

    with pytest.raises(InvalidStateTransitionError):
        agent_run.fail("ERR", "Msg")

    with pytest.raises(InvalidStateTransitionError):
        agent_run.cancel()

    with pytest.raises(InvalidStateTransitionError):
        agent_run.timeout()

    with pytest.raises(InvalidStateTransitionError):
        agent_run.record_step()


def test_illegal_transitions_raise_error(agent_run: AgentRun) -> None:
    """Illegal state transitions raise InvalidStateTransitionError."""
    # Cannot start directly from CREATED (must be QUEUED first)
    with pytest.raises(InvalidStateTransitionError):
        agent_run.start()

    # Cannot complete from CREATED
    with pytest.raises(InvalidStateTransitionError):
        agent_run.complete("Answer")

    # Cannot request input from CREATED
    with pytest.raises(InvalidStateTransitionError):
        agent_run.request_input()


def test_all_8_states_defined() -> None:
    """Ensure exactly 8 states are defined in RunStatus."""
    expected_states = {
        "created",
        "queued",
        "running",
        "awaiting_input",
        "completed",
        "failed",
        "cancelled",
        "timed_out",
    }
    actual_states = {s.value for s in RunStatus}
    assert actual_states == expected_states
    assert len(RunStatus) == 8
    assert len(TERMINAL_STATES) == 4
