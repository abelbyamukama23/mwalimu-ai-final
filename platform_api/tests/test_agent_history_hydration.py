"""Tests for canonical session history hydration service."""

from __future__ import annotations

import uuid

import pytest
from django.contrib.auth import get_user_model

from platform_api.apps.agents.hydration import (
    hydrate_session_history,
)
from platform_api.apps.agents.models import (
    AgentSession,
    AgentSessionMessage,
    AgentSessionStatus,
    MessageRole,
)
from platform_api.apps.institutions.models import Institution

User = get_user_model()


@pytest.fixture
def institution(db: None) -> Institution:
    """Create a test institution."""
    return Institution.objects.create(
        name="History Test Academy",
        slug=f"history-test-academy-{uuid.uuid4().hex[:8]}",
    )


@pytest.fixture
def user(db: None, institution: Institution) -> User:
    """Create a test user."""
    return User.objects.create_user(
        email=f"history_user_{uuid.uuid4().hex[:8]}@example.com",
        password="ValidPassword123!",
    )


@pytest.fixture
def session(db: None, user: User, institution: Institution) -> AgentSession:
    """Create a test agent session."""
    return AgentSession.objects.create(
        user=user,
        institution=institution,
        title="Multi-Turn Research Thread",
        status=AgentSessionStatus.ACTIVE,
    )


@pytest.mark.django_db
def test_hydrate_empty_session_returns_empty_list(session: AgentSession) -> None:
    """An empty session produces an empty history list."""
    history = hydrate_session_history(session)
    assert history == []


@pytest.mark.django_db
def test_hydrate_preserves_chronological_sequence_order(session: AgentSession) -> None:
    """Hydrated messages are strictly ordered by sequence ASC."""
    AgentSessionMessage.objects.create(
        session=session,
        role=MessageRole.USER,
        content="What is photosynthesis?",
        sequence=0,
    )
    AgentSessionMessage.objects.create(
        session=session,
        role=MessageRole.ASSISTANT,
        content="Photosynthesis is the process by which plants make food.",
        sequence=1,
    )
    AgentSessionMessage.objects.create(
        session=session,
        role=MessageRole.USER,
        content="What are the light reactions?",
        sequence=2,
    )

    history = hydrate_session_history(session)
    assert len(history) == 3
    assert history[0] == {"role": "user", "content": "What is photosynthesis?"}
    assert history[1] == {
        "role": "assistant",
        "content": "Photosynthesis is the process by which plants make food.",
    }
    assert history[2] == {"role": "user", "content": "What are the light reactions?"}


@pytest.mark.django_db
def test_hydrate_filters_out_system_messages(session: AgentSession) -> None:
    """System messages are excluded from runtime projection."""
    AgentSessionMessage.objects.create(
        session=session,
        role=MessageRole.SYSTEM,
        content="Internal administrative notice: session started.",
        sequence=0,
    )
    AgentSessionMessage.objects.create(
        session=session,
        role=MessageRole.USER,
        content="Hello!",
        sequence=1,
    )
    AgentSessionMessage.objects.create(
        session=session,
        role=MessageRole.ASSISTANT,
        content="Hello! How can I help you today?",
        sequence=2,
    )

    history = hydrate_session_history(session)
    assert len(history) == 2
    assert history[0] == {"role": "user", "content": "Hello!"}
    assert history[1] == {
        "role": "assistant",
        "content": "Hello! How can I help you today?",
    }


@pytest.mark.django_db
def test_hydrate_bounds_history_to_max_messages(session: AgentSession) -> None:
    """Hydration respects max_messages bound and takes the most recent messages."""
    for i in range(10):
        role = MessageRole.USER if i % 2 == 0 else MessageRole.ASSISTANT
        AgentSessionMessage.objects.create(
            session=session,
            role=role,
            content=f"Message {i}",
            sequence=i,
        )

    # Request max 4 messages -> should get messages 6, 7, 8, 9
    history = hydrate_session_history(session, max_messages=4)
    assert len(history) == 4
    assert [m["content"] for m in history] == [
        "Message 6",
        "Message 7",
        "Message 8",
        "Message 9",
    ]
    # Check that sequence ordering is preserved
    assert history[0]["role"] == "user"
    assert history[1]["role"] == "assistant"
    assert history[2]["role"] == "user"
    assert history[3]["role"] == "assistant"


@pytest.mark.django_db
def test_hydrate_excludes_sensitive_internal_fields(session: AgentSession) -> None:
    """Hydrated messages contain ONLY role and content, no IDs or metadata."""
    AgentSessionMessage.objects.create(
        session=session,
        role=MessageRole.USER,
        content="Research query",
        citations=[{"resource_id": str(uuid.uuid4()), "score": 0.95}],
        sequence=0,
    )

    history = hydrate_session_history(session)
    assert len(history) == 1
    assert set(history[0].keys()) == {"role", "content"}
    assert "citations" not in history[0]
    assert "id" not in history[0]
    assert "session_id" not in history[0]
    assert "created_at" not in history[0]


@pytest.mark.django_db
def test_hydrate_zero_or_negative_max_messages(session: AgentSession) -> None:
    """Non-positive max_messages returns empty list."""
    AgentSessionMessage.objects.create(
        session=session,
        role=MessageRole.USER,
        content="Hello",
        sequence=0,
    )
    assert hydrate_session_history(session, max_messages=0) == []
    assert hydrate_session_history(session, max_messages=-5) == []
