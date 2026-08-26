"""Unit tests for ExecutionContext domain value object."""

import uuid
from dataclasses import FrozenInstanceError

import pytest

from agent_service.domain.context import ExecutionContext


def test_execution_context_valid_initialization() -> None:
    """ExecutionContext initializes with valid attributes and default budgets."""
    u_id = uuid.uuid4()
    run_id = uuid.uuid4()
    sess_id = uuid.uuid4()

    ctx = ExecutionContext(
        user_id=u_id,
        agent_run_id=run_id,
        session_id=sess_id,
    )

    assert ctx.user_id == u_id
    assert ctx.agent_run_id == run_id
    assert ctx.session_id == sess_id
    assert ctx.max_steps == 10
    assert ctx.timeout_seconds == 60.0
    assert ctx.token_budget == 4000
    assert ctx.locale == "en"
    assert ctx.tool_allowlist is None


def test_execution_context_immutability() -> None:
    """ExecutionContext is frozen and raises FrozenInstanceError on mutation."""
    ctx = ExecutionContext(
        user_id=uuid.uuid4(),
        agent_run_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
    )

    with pytest.raises(FrozenInstanceError):
        ctx.max_steps = 20  # type: ignore[misc]


def test_execution_context_type_validations() -> None:
    """Non-UUID arguments raise TypeError."""
    valid_uuid = uuid.uuid4()

    with pytest.raises(TypeError, match="user_id must be a valid UUID"):
        ExecutionContext(
            user_id="not-a-uuid",  # type: ignore[arg-type]
            agent_run_id=valid_uuid,
            session_id=valid_uuid,
        )

    with pytest.raises(TypeError, match="agent_run_id must be a valid UUID"):
        ExecutionContext(
            user_id=valid_uuid,
            agent_run_id="not-a-uuid",  # type: ignore[arg-type]
            session_id=valid_uuid,
        )

    with pytest.raises(TypeError, match="session_id must be a valid UUID"):
        ExecutionContext(
            user_id=valid_uuid,
            agent_run_id=valid_uuid,
            session_id="not-a-uuid",  # type: ignore[arg-type]
        )


def test_execution_context_boundary_validations() -> None:
    """Invalid budget parameters raise ValueError."""
    u_id = uuid.uuid4()
    run_id = uuid.uuid4()
    sess_id = uuid.uuid4()

    with pytest.raises(ValueError, match="max_steps must be at least 1"):
        ExecutionContext(
            user_id=u_id,
            agent_run_id=run_id,
            session_id=sess_id,
            max_steps=0,
        )

    with pytest.raises(ValueError, match="timeout_seconds must be greater than 0"):
        ExecutionContext(
            user_id=u_id,
            agent_run_id=run_id,
            session_id=sess_id,
            timeout_seconds=0.0,
        )

    with pytest.raises(ValueError, match="token_budget must be at least 100"):
        ExecutionContext(
            user_id=u_id,
            agent_run_id=run_id,
            session_id=sess_id,
            token_budget=50,
        )


def test_execution_context_tool_allowlist() -> None:
    """is_tool_allowed correctly checks allowlist boundaries."""
    ctx_unrestricted = ExecutionContext(
        user_id=uuid.uuid4(),
        agent_run_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        tool_allowlist=None,
    )
    assert ctx_unrestricted.is_tool_allowed("knowledge_search") is True
    assert ctx_unrestricted.is_tool_allowed("calculator") is True

    ctx_restricted = ExecutionContext(
        user_id=uuid.uuid4(),
        agent_run_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        tool_allowlist=frozenset(["knowledge_search"]),
    )
    assert ctx_restricted.is_tool_allowed("knowledge_search") is True
    assert ctx_restricted.is_tool_allowed("calculator") is False
