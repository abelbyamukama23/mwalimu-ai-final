"""Tests for AgentSession, AgentRunRecord, and AgentSessionMessage data models.

Covers:
- Model creation, UUID identity, ownership, and timestamps.
- Foreign-key relationships and cascade deletion.
- Status enumerations and lifecycle transitions.
- Database constraints: unique session sequence, one assistant per run.
- Idempotency invariants at the persistence layer.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest
from django.db import IntegrityError
from django.utils import timezone

from platform_api.apps.agents.models import (
    TERMINAL_STATUSES,
    AgentRunRecord,
    AgentRunStatus,
    AgentSession,
    AgentSessionMessage,
    AgentSessionStatus,
    MessageRole,
)
from platform_api.apps.institutions.models import Institution, InstitutionStatus
from platform_api.apps.libraries.models import Library, LibraryStatus, LibraryVisibility

if TYPE_CHECKING:
    from platform_api.apps.users.models import User


# ---------------------------------------------------------------------------
# Local fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def institution(db: None) -> Institution:
    """Return a test institution."""
    return Institution.objects.create(
        name="Test University",
        slug="test-university",
        status=InstitutionStatus.ACTIVE,
    )


@pytest.fixture
def user(db: None) -> User:
    """Return a test user."""
    from django.contrib.auth import get_user_model

    return get_user_model().objects.create_user(
        email="agent-tester@example.com",
        password="test-password-123",
    )


@pytest.fixture
def second_user(db: None) -> User:
    """Return a second test user."""
    from django.contrib.auth import get_user_model

    return get_user_model().objects.create_user(
        email="agent-tester-2@example.com",
        password="test-password-456",
    )


@pytest.fixture
def library(institution: Institution) -> Library:
    """Return a test library."""
    return Library.objects.create(
        institution=institution,
        name="Test Library",
        slug="test-library",
        status=LibraryStatus.ACTIVE,
        visibility=LibraryVisibility.RESTRICTED,
    )


@pytest.fixture
def session(user: User, institution: Institution) -> AgentSession:
    """Return a test agent session."""
    return AgentSession.objects.create(
        user=user,
        institution=institution,
        title="Test Session",
    )


@pytest.fixture
def session_with_library(
    user: User, institution: Institution, library: Library
) -> AgentSession:
    """Return a test agent session scoped to a library."""
    return AgentSession.objects.create(
        user=user,
        institution=institution,
        primary_library=library,
        title="Library-Scoped Session",
    )


@pytest.fixture
def run_record(session: AgentSession, user: User) -> AgentRunRecord:
    """Return a test agent run record."""
    return AgentRunRecord.objects.create(
        session=session,
        user=user,
        prompt="What is photosynthesis?",
    )


# ---------------------------------------------------------------------------
# AgentSession tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_session_creation(user: User, institution: Institution) -> None:
    """An AgentSession can be created with expected default fields."""
    session = AgentSession.objects.create(
        user=user,
        institution=institution,
        title="My First Session",
    )

    assert isinstance(session.id, uuid.UUID)
    assert session.user == user
    assert session.institution == institution
    assert session.title == "My First Session"
    assert session.status == AgentSessionStatus.ACTIVE
    assert session.primary_library is None
    assert session.metadata == {}
    assert session.created_at is not None
    assert session.updated_at is not None


@pytest.mark.django_db
def test_session_uuid_is_unique(user: User, institution: Institution) -> None:
    """Each AgentSession receives a distinct UUID."""
    s1 = AgentSession.objects.create(
        user=user, institution=institution, title="Session 1"
    )
    s2 = AgentSession.objects.create(
        user=user, institution=institution, title="Session 2"
    )
    assert s1.id != s2.id


@pytest.mark.django_db
def test_session_with_library(
    session_with_library: AgentSession, library: Library
) -> None:
    """An AgentSession can be optionally scoped to a primary library."""
    assert session_with_library.primary_library == library
    assert session_with_library.primary_library_id == library.pk


@pytest.mark.django_db
def test_session_without_library(session: AgentSession) -> None:
    """An AgentSession can exist without a primary library."""
    assert session.primary_library is None


@pytest.mark.django_db
def test_session_library_set_null_on_delete(
    session_with_library: AgentSession, library: Library
) -> None:
    """Deleting a library sets session.primary_library to NULL."""
    library.delete()
    session_with_library.refresh_from_db()
    assert session_with_library.primary_library is None


@pytest.mark.django_db
def test_session_metadata_default(session: AgentSession) -> None:
    """Session metadata defaults to an empty dict."""
    assert session.metadata == {}


@pytest.mark.django_db
def test_session_metadata_custom(user: User, institution: Institution) -> None:
    """Session metadata supports arbitrary JSON."""
    session = AgentSession.objects.create(
        user=user,
        institution=institution,
        title="Custom Metadata Session",
        metadata={"mode": "study", "language": "en"},
    )
    assert session.metadata["mode"] == "study"
    assert session.metadata["language"] == "en"


@pytest.mark.django_db
def test_session_status_archived(session: AgentSession) -> None:
    """A session can be archived."""
    session.status = AgentSessionStatus.ARCHIVED
    session.save(update_fields=["status", "updated_at"])
    session.refresh_from_db()
    assert session.status == AgentSessionStatus.ARCHIVED


@pytest.mark.django_db
def test_session_str_representation(session: AgentSession) -> None:
    """Session __str__ returns a readable representation."""
    result = str(session)
    assert "AgentSession(" in result
    assert str(session.id) in result


@pytest.mark.django_db
def test_session_user_cascade_delete(user: User, institution: Institution) -> None:
    """Deleting a user cascades to their sessions."""
    session = AgentSession.objects.create(
        user=user, institution=institution, title="Cascade Test"
    )
    session_id = session.id
    user.delete()
    assert not AgentSession.objects.filter(pk=session_id).exists()


@pytest.mark.django_db
def test_session_institution_cascade_delete(
    user: User, institution: Institution
) -> None:
    """Deleting an institution cascades to its sessions."""
    session = AgentSession.objects.create(
        user=user, institution=institution, title="Cascade Test"
    )
    session_id = session.id
    institution.delete()
    assert not AgentSession.objects.filter(pk=session_id).exists()


# ---------------------------------------------------------------------------
# AgentRunRecord tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_run_record_creation(session: AgentSession, user: User) -> None:
    """An AgentRunRecord can be created with expected default fields."""
    run = AgentRunRecord.objects.create(
        session=session,
        user=user,
        prompt="Explain mitosis.",
    )

    assert isinstance(run.id, uuid.UUID)
    assert run.session == session
    assert run.user == user
    assert run.prompt == "Explain mitosis."
    assert run.status == AgentRunStatus.CREATED
    assert run.answer is None
    assert run.citations == []
    assert run.error_code is None
    assert run.error_message is None
    assert run.step_count == 0
    assert run.prompt_tokens == 0
    assert run.completion_tokens == 0
    assert run.total_tokens == 0
    assert run.timeout_seconds == 60.0
    assert run.max_steps == 10
    assert run.created_at is not None
    assert run.queued_at is not None
    assert run.started_at is None
    assert run.finished_at is None
    assert run.updated_at is not None


@pytest.mark.django_db
def test_run_record_uuid_is_unique(session: AgentSession, user: User) -> None:
    """Each AgentRunRecord receives a distinct UUID."""
    r1 = AgentRunRecord.objects.create(session=session, user=user, prompt="Q1")
    r2 = AgentRunRecord.objects.create(session=session, user=user, prompt="Q2")
    assert r1.id != r2.id


@pytest.mark.django_db
def test_run_record_lifecycle_timestamps(session: AgentSession, user: User) -> None:
    """Run record supports the full lifecycle timestamp progression."""
    run = AgentRunRecord.objects.create(
        session=session, user=user, prompt="Test timestamps."
    )
    assert run.started_at is None
    assert run.finished_at is None

    now = timezone.now()
    run.status = AgentRunStatus.RUNNING
    run.started_at = now
    run.save(update_fields=["status", "started_at", "updated_at"])
    run.refresh_from_db()
    assert run.started_at is not None
    assert run.status == AgentRunStatus.RUNNING

    run.status = AgentRunStatus.COMPLETED
    run.finished_at = timezone.now()
    run.answer = "Photosynthesis converts light energy."
    run.save(update_fields=["status", "finished_at", "answer", "updated_at"])
    run.refresh_from_db()
    assert run.finished_at is not None
    assert run.is_terminal is True


@pytest.mark.django_db
def test_run_record_token_metrics(session: AgentSession, user: User) -> None:
    """Token accounting fields can be updated."""
    run = AgentRunRecord.objects.create(
        session=session, user=user, prompt="Token test."
    )
    run.prompt_tokens = 450
    run.completion_tokens = 200
    run.total_tokens = 650
    run.step_count = 3
    run.save(
        update_fields=[
            "prompt_tokens",
            "completion_tokens",
            "total_tokens",
            "step_count",
            "updated_at",
        ]
    )
    run.refresh_from_db()
    assert run.prompt_tokens == 450
    assert run.completion_tokens == 200
    assert run.total_tokens == 650
    assert run.step_count == 3


@pytest.mark.django_db
def test_run_record_timeout_configuration(session: AgentSession, user: User) -> None:
    """Custom timeout and max_steps can be set."""
    run = AgentRunRecord.objects.create(
        session=session,
        user=user,
        prompt="Custom config.",
        timeout_seconds=120.0,
        max_steps=20,
    )
    assert run.timeout_seconds == 120.0
    assert run.max_steps == 20


@pytest.mark.django_db
def test_run_record_error_fields(session: AgentSession, user: User) -> None:
    """Error code and message can be recorded on failure."""
    run = AgentRunRecord.objects.create(session=session, user=user, prompt="Fail test.")
    run.status = AgentRunStatus.FAILED
    run.error_code = "EXECUTION_TIMEOUT"
    run.error_message = "Run exceeded 60s budget."
    run.finished_at = timezone.now()
    run.save(
        update_fields=[
            "status",
            "error_code",
            "error_message",
            "finished_at",
            "updated_at",
        ]
    )
    run.refresh_from_db()
    assert run.status == AgentRunStatus.FAILED
    assert run.error_code == "EXECUTION_TIMEOUT"
    assert run.is_terminal is True


@pytest.mark.django_db
def test_run_record_is_terminal_property() -> None:
    """The is_terminal property correctly identifies terminal statuses."""
    terminal = {
        AgentRunStatus.COMPLETED,
        AgentRunStatus.FAILED,
        AgentRunStatus.CANCELLED,
        AgentRunStatus.TIMED_OUT,
    }
    non_terminal = {
        AgentRunStatus.CREATED,
        AgentRunStatus.QUEUED,
        AgentRunStatus.RUNNING,
        AgentRunStatus.AWAITING_INPUT,
    }

    for s in terminal:
        assert s in TERMINAL_STATUSES, f"{s} should be terminal"

    for s in non_terminal:
        assert s not in TERMINAL_STATUSES, f"{s} should not be terminal"


@pytest.mark.django_db
def test_run_record_citations_json(session: AgentSession, user: User) -> None:
    """Citations JSONField supports 14-field citation objects."""
    citations = [
        {
            "chunk_id": str(uuid.uuid4()),
            "resource_id": str(uuid.uuid4()),
            "resource_name": "biology.pdf",
            "library_id": str(uuid.uuid4()),
            "library_name": "Science Library",
            "score": 0.92,
            "text": "Photosynthesis is...",
            "section": "Chapter 1",
            "page_start": 1,
            "page_end": 2,
            "char_start": 0,
            "char_end": 200,
            "content_sha256": "abc123",
            "token_count": 45,
        }
    ]
    run = AgentRunRecord.objects.create(
        session=session,
        user=user,
        prompt="Citation test.",
        status=AgentRunStatus.COMPLETED,
        answer="Photosynthesis...",
        citations=citations,
        finished_at=timezone.now(),
    )
    run.refresh_from_db()
    assert len(run.citations) == 1
    assert run.citations[0]["resource_name"] == "biology.pdf"
    assert run.citations[0]["score"] == 0.92


@pytest.mark.django_db
def test_run_record_str_representation(run_record: AgentRunRecord) -> None:
    """Run record __str__ returns a readable representation."""
    result = str(run_record)
    assert "AgentRunRecord(" in result
    assert str(run_record.id) in result


@pytest.mark.django_db
def test_run_record_session_cascade_delete(session: AgentSession, user: User) -> None:
    """Deleting a session cascades to its run records."""
    run = AgentRunRecord.objects.create(session=session, user=user, prompt="Cascade.")
    run_id = run.id
    session.delete()
    assert not AgentRunRecord.objects.filter(pk=run_id).exists()


@pytest.mark.django_db
def test_run_record_user_cascade_delete(
    session: AgentSession, user: User, institution: Institution
) -> None:
    """Deleting a user cascades to their run records."""
    run = AgentRunRecord.objects.create(session=session, user=user, prompt="Cascade.")
    run_id = run.id
    user.delete()
    assert not AgentRunRecord.objects.filter(pk=run_id).exists()


@pytest.mark.django_db
def test_multiple_runs_per_session(session: AgentSession, user: User) -> None:
    """A session can have multiple runs."""
    r1 = AgentRunRecord.objects.create(session=session, user=user, prompt="Q1")
    r2 = AgentRunRecord.objects.create(session=session, user=user, prompt="Q2")
    r3 = AgentRunRecord.objects.create(session=session, user=user, prompt="Q3")
    assert session.runs.count() == 3
    assert {r1.id, r2.id, r3.id} == set(session.runs.values_list("id", flat=True))


# ---------------------------------------------------------------------------
# AgentSessionMessage tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_message_creation(session: AgentSession) -> None:
    """An AgentSessionMessage can be created with expected fields."""
    msg = AgentSessionMessage.objects.create(
        session=session,
        role=MessageRole.USER,
        content="What is DNA?",
        sequence=0,
    )

    assert isinstance(msg.id, uuid.UUID)
    assert msg.session == session
    assert msg.run is None
    assert msg.role == MessageRole.USER
    assert msg.content == "What is DNA?"
    assert msg.citations == []
    assert msg.sequence == 0
    assert msg.created_at is not None


@pytest.mark.django_db
def test_message_ordering(session: AgentSession) -> None:
    """Messages are ordered by session and sequence."""
    AgentSessionMessage.objects.create(
        session=session, role=MessageRole.USER, content="Q1", sequence=0
    )
    AgentSessionMessage.objects.create(
        session=session, role=MessageRole.ASSISTANT, content="A1", sequence=1
    )
    AgentSessionMessage.objects.create(
        session=session, role=MessageRole.USER, content="Q2", sequence=2
    )

    messages = list(session.messages.all())
    assert len(messages) == 3
    assert messages[0].sequence == 0
    assert messages[1].sequence == 1
    assert messages[2].sequence == 2
    assert messages[0].role == MessageRole.USER
    assert messages[1].role == MessageRole.ASSISTANT


@pytest.mark.django_db
def test_message_with_run_correlation(
    session: AgentSession, run_record: AgentRunRecord
) -> None:
    """A message can be correlated with a specific run."""
    msg = AgentSessionMessage.objects.create(
        session=session,
        run=run_record,
        role=MessageRole.ASSISTANT,
        content="Photosynthesis is...",
        sequence=1,
    )
    assert msg.run == run_record
    assert msg.run_id == run_record.pk


@pytest.mark.django_db
def test_message_run_set_null_on_delete(session: AgentSession, user: User) -> None:
    """Deleting a run sets message.run to NULL (preserves transcript)."""
    run = AgentRunRecord.objects.create(
        session=session, user=user, prompt="Ephemeral run."
    )
    msg = AgentSessionMessage.objects.create(
        session=session,
        run=run,
        role=MessageRole.ASSISTANT,
        content="Answer from deleted run.",
        sequence=0,
    )
    run.delete()
    msg.refresh_from_db()
    assert msg.run is None
    assert msg.content == "Answer from deleted run."


@pytest.mark.django_db
def test_message_citations_json(session: AgentSession) -> None:
    """Message citations support structured JSON evidence."""
    citations = [{"resource_name": "bio.pdf", "score": 0.88}]
    msg = AgentSessionMessage.objects.create(
        session=session,
        role=MessageRole.ASSISTANT,
        content="Based on the textbook...",
        citations=citations,
        sequence=0,
    )
    msg.refresh_from_db()
    assert msg.citations[0]["resource_name"] == "bio.pdf"


@pytest.mark.django_db
def test_message_str_representation(session: AgentSession) -> None:
    """Message __str__ returns a readable representation."""
    msg = AgentSessionMessage.objects.create(
        session=session, role=MessageRole.USER, content="Hello", sequence=0
    )
    result = str(msg)
    assert "AgentSessionMessage(" in result
    assert "seq=0" in result


@pytest.mark.django_db
def test_message_session_cascade_delete(
    session: AgentSession,
) -> None:
    """Deleting a session cascades to its messages."""
    AgentSessionMessage.objects.create(
        session=session, role=MessageRole.USER, content="Bye", sequence=0
    )
    session_id = session.id
    session.delete()
    assert not AgentSessionMessage.objects.filter(session_id=session_id).exists()


# ---------------------------------------------------------------------------
# Database constraint tests — Invariant A: unique (session, sequence)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_duplicate_sequence_rejected(session: AgentSession) -> None:
    """The database rejects duplicate sequence numbers within a session."""
    AgentSessionMessage.objects.create(
        session=session, role=MessageRole.USER, content="First", sequence=0
    )
    with pytest.raises(IntegrityError):
        AgentSessionMessage.objects.create(
            session=session, role=MessageRole.ASSISTANT, content="Dup", sequence=0
        )


@pytest.mark.django_db
def test_same_sequence_allowed_across_sessions(
    user: User, institution: Institution
) -> None:
    """Different sessions can use the same sequence numbers."""
    s1 = AgentSession.objects.create(user=user, institution=institution, title="S1")
    s2 = AgentSession.objects.create(user=user, institution=institution, title="S2")
    AgentSessionMessage.objects.create(
        session=s1, role=MessageRole.USER, content="Q1", sequence=0
    )
    msg2 = AgentSessionMessage.objects.create(
        session=s2, role=MessageRole.USER, content="Q1", sequence=0
    )
    assert msg2.sequence == 0


# ---------------------------------------------------------------------------
# Database constraint tests — Invariant B: one assistant per run
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_one_assistant_per_run_enforced(session: AgentSession, user: User) -> None:
    """The database rejects a second assistant message for the same run."""
    run = AgentRunRecord.objects.create(
        session=session, user=user, prompt="Invariant B test."
    )
    AgentSessionMessage.objects.create(
        session=session,
        run=run,
        role=MessageRole.ASSISTANT,
        content="First answer.",
        sequence=1,
    )
    with pytest.raises(IntegrityError):
        AgentSessionMessage.objects.create(
            session=session,
            run=run,
            role=MessageRole.ASSISTANT,
            content="Duplicate answer.",
            sequence=2,
        )


@pytest.mark.django_db
def test_user_message_not_blocked_by_assistant_constraint(
    session: AgentSession, user: User
) -> None:
    """User messages for the same run are not blocked by the assistant constraint."""
    run = AgentRunRecord.objects.create(
        session=session, user=user, prompt="Invariant B scope test."
    )
    # User message with run correlation
    AgentSessionMessage.objects.create(
        session=session,
        run=run,
        role=MessageRole.USER,
        content="User prompt.",
        sequence=0,
    )
    # Assistant message for same run
    AgentSessionMessage.objects.create(
        session=session,
        run=run,
        role=MessageRole.ASSISTANT,
        content="Assistant answer.",
        sequence=1,
    )
    # Second user message for same run should be fine
    # (constraint only applies to assistant role)
    msg3 = AgentSessionMessage.objects.create(
        session=session,
        run=run,
        role=MessageRole.USER,
        content="Follow-up.",
        sequence=2,
    )
    assert msg3.role == MessageRole.USER


@pytest.mark.django_db
def test_different_runs_can_each_have_assistant_message(
    session: AgentSession, user: User
) -> None:
    """Different runs can each produce one assistant message."""
    run1 = AgentRunRecord.objects.create(session=session, user=user, prompt="Q1")
    run2 = AgentRunRecord.objects.create(session=session, user=user, prompt="Q2")

    AgentSessionMessage.objects.create(
        session=session,
        run=run1,
        role=MessageRole.ASSISTANT,
        content="Answer 1.",
        sequence=1,
    )
    msg2 = AgentSessionMessage.objects.create(
        session=session,
        run=run2,
        role=MessageRole.ASSISTANT,
        content="Answer 2.",
        sequence=3,
    )
    assert msg2.run == run2
    assert session.messages.filter(role=MessageRole.ASSISTANT).count() == 2


@pytest.mark.django_db
def test_assistant_without_run_not_constrained(
    session: AgentSession,
) -> None:
    """Assistant messages without a run FK are not subject to the constraint."""
    AgentSessionMessage.objects.create(
        session=session,
        run=None,
        role=MessageRole.ASSISTANT,
        content="System greeting.",
        sequence=0,
    )
    msg2 = AgentSessionMessage.objects.create(
        session=session,
        run=None,
        role=MessageRole.ASSISTANT,
        content="Another greeting.",
        sequence=1,
    )
    assert msg2.run is None


# ---------------------------------------------------------------------------
# Idempotency model tests (no endpoint yet — data model only)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_idempotent_completion_model_support(session: AgentSession, user: User) -> None:
    """The data model supports first, repeated, and conflicting completions.

    This test proves the persistence layer can support idempotent completion
    synchronization without implementing the endpoint.
    """
    run = AgentRunRecord.objects.create(
        session=session,
        user=user,
        prompt="Idempotency test.",
        status=AgentRunStatus.RUNNING,
        started_at=timezone.now(),
    )

    # Simulate first completion
    run.status = AgentRunStatus.COMPLETED
    run.answer = "The answer is 42."
    run.finished_at = timezone.now()
    run.save(update_fields=["status", "answer", "finished_at", "updated_at"])
    run.refresh_from_db()
    assert run.is_terminal is True

    # Simulate repeated identical completion — model accepts same status
    run.status = AgentRunStatus.COMPLETED
    run.save(update_fields=["status", "updated_at"])
    run.refresh_from_db()
    assert run.status == AgentRunStatus.COMPLETED

    # Simulate conflicting completion — model allows status override
    # (application logic will reject this; model doesn't enforce ordering)
    run.status = AgentRunStatus.FAILED
    run.save(update_fields=["status", "updated_at"])
    run.refresh_from_db()
    assert run.status == AgentRunStatus.FAILED
    assert run.is_terminal is True


@pytest.mark.django_db
def test_transcript_idempotency_via_run_constraint(
    session: AgentSession, user: User
) -> None:
    """The one-assistant-per-run constraint prevents duplicate transcripts.

    Even if completion sync is retried, the database blocks a second
    assistant message for the same run.
    """
    run = AgentRunRecord.objects.create(
        session=session,
        user=user,
        prompt="Transcript idempotency test.",
        status=AgentRunStatus.COMPLETED,
        answer="42",
        finished_at=timezone.now(),
    )

    # First transcript message succeeds
    AgentSessionMessage.objects.create(
        session=session,
        run=run,
        role=MessageRole.ASSISTANT,
        content="42",
        sequence=1,
    )

    # Retried transcript message fails at DB level
    with pytest.raises(IntegrityError):
        AgentSessionMessage.objects.create(
            session=session,
            run=run,
            role=MessageRole.ASSISTANT,
            content="42",
            sequence=2,
        )


# ---------------------------------------------------------------------------
# Full cascade test
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_full_cascade_session_to_messages_and_runs(
    user: User, institution: Institution
) -> None:
    """Deleting a session cascades to runs and messages."""
    session = AgentSession.objects.create(
        user=user, institution=institution, title="Full Cascade"
    )
    run = AgentRunRecord.objects.create(session=session, user=user, prompt="Test.")
    AgentSessionMessage.objects.create(
        session=session,
        run=run,
        role=MessageRole.USER,
        content="Q",
        sequence=0,
    )
    AgentSessionMessage.objects.create(
        session=session,
        run=run,
        role=MessageRole.ASSISTANT,
        content="A",
        sequence=1,
    )

    session_id = session.id
    run_id = run.id

    session.delete()

    assert not AgentSession.objects.filter(pk=session_id).exists()
    assert not AgentRunRecord.objects.filter(pk=run_id).exists()
    assert not AgentSessionMessage.objects.filter(session_id=session_id).exists()


@pytest.mark.django_db
def test_queued_at_and_created_at_populated(session: AgentSession, user: User) -> None:
    """Both created_at and queued_at are populated on creation."""
    run = AgentRunRecord.objects.create(
        session=session, user=user, prompt="Timestamp test."
    )
    assert run.created_at is not None
    assert run.queued_at is not None
    # queued_at and created_at should be very close in time
    delta = abs((run.queued_at - run.created_at).total_seconds())
    assert delta < 1.0
