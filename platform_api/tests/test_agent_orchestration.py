"""Tests for AgentRunOrchestrationService."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

import httpx
import pytest

from platform_api.apps.agents.client import (
    AgentServiceClient,
)
from platform_api.apps.agents.models import (
    AgentRunRecord,
    AgentRunStatus,
    AgentSession,
)
from platform_api.apps.agents.orchestration import (
    AgentRunOrchestrationService,
    AgentServiceDispatchFailedError,
    AgentServiceUnavailableError,
)
from platform_api.apps.institutions.models import Institution, InstitutionStatus
from platform_api.apps.libraries.models import Library, LibraryStatus, LibraryVisibility

if TYPE_CHECKING:
    from platform_api.apps.users.models import User


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def institution(db: None) -> Institution:
    """Return a test institution."""
    return Institution.objects.create(
        name="Orchestration University",
        slug="orch-uni",
        status=InstitutionStatus.ACTIVE,
    )


@pytest.fixture
def user(db: None) -> User:
    """Return a test user."""
    from django.contrib.auth import get_user_model

    return get_user_model().objects.create_user(
        email="orchestrator@example.com",
        password="test-password-123",
    )


@pytest.fixture
def library(institution: Institution) -> Library:
    """Return a test library."""
    return Library.objects.create(
        institution=institution,
        name="Orch Library",
        slug="orch-lib",
        status=LibraryStatus.ACTIVE,
        visibility=LibraryVisibility.RESTRICTED,
    )


@pytest.fixture
def session(user: User, institution: Institution) -> AgentSession:
    """Return a test session."""
    return AgentSession.objects.create(
        user=user,
        institution=institution,
        title="Orchestration Session",
    )


@pytest.fixture
def library_session(
    user: User, institution: Institution, library: Library
) -> AgentSession:
    """Return a library-scoped session."""
    return AgentSession.objects.create(
        user=user,
        institution=institution,
        primary_library=library,
        title="Library Orch Session",
    )


# ---------------------------------------------------------------------------
# Orchestration Service Tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_orchestration_successful_dispatch(session: AgentSession, user: User) -> None:
    """Successful dispatch updates AgentRunRecord to QUEUED with queued_at."""
    remote_run_id = uuid.uuid4()

    def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=202,
            json={
                "id": str(remote_run_id),
                "session_id": str(session.pk),
                "status": "queued",
                "prompt": "What is gravity?",
                "created_at": "2026-08-23T15:00:00Z",
                "timeout_seconds": 60.0,
                "max_steps": 10,
            },
        )

    transport = httpx.MockTransport(mock_handler)
    client = AgentServiceClient(
        base_url="http://agent-service.test",
        client=httpx.Client(transport=transport),
    )
    service = AgentRunOrchestrationService(client=client)

    run_record = service.dispatch_session_run(
        session=session,
        user=user,
        prompt="What is gravity?",
        timeout_seconds=60.0,
        max_steps=10,
    )

    assert isinstance(run_record, AgentRunRecord)
    assert run_record.session == session
    assert run_record.user == user
    assert run_record.prompt == "What is gravity?"
    assert run_record.status == AgentRunStatus.QUEUED
    assert run_record.queued_at is not None
    assert run_record.started_at is None
    assert run_record.finished_at is None


@pytest.mark.django_db
def test_orchestration_passes_delegated_token_for_library_session(
    library_session: AgentSession, user: User
) -> None:
    """Library-scoped sessions include DelegatedExecutionToken in dispatch."""
    captured_headers: dict[str, str] = {}

    def mock_handler(request: httpx.Request) -> httpx.Response:
        captured_headers.update(dict(request.headers))
        return httpx.Response(
            status_code=202,
            json={
                "id": str(uuid.uuid4()),
                "session_id": str(library_session.pk),
                "status": "queued",
                "prompt": "Prompt",
                "created_at": "2026-08-23T15:00:00Z",
            },
        )

    transport = httpx.MockTransport(mock_handler)
    client = AgentServiceClient(
        base_url="http://agent-service.test",
        client=httpx.Client(transport=transport),
    )
    service = AgentRunOrchestrationService(client=client)

    service.dispatch_session_run(
        session=library_session,
        user=user,
        prompt="Prompt",
    )

    assert "x-delegated-token" in captured_headers
    assert captured_headers["x-delegated-token"].count(".") == 2  # valid JWT


@pytest.mark.django_db
def test_orchestration_mints_token_with_selected_knowledge_scope(
    session: AgentSession, user: User
) -> None:
    """The delegated token carries the authoritative knowledge scope for retrieval."""
    import jwt
    from django.conf import settings

    captured_headers: dict[str, str] = {}

    def mock_handler(request: httpx.Request) -> httpx.Response:
        captured_headers.update(dict(request.headers))
        return httpx.Response(
            status_code=202,
            json={
                "id": str(uuid.uuid4()),
                "session_id": str(session.pk),
                "status": "queued",
                "prompt": "Prompt",
                "created_at": "2026-08-23T15:00:00Z",
            },
        )

    transport = httpx.MockTransport(mock_handler)
    client = AgentServiceClient(
        base_url="http://agent-service.test",
        client=httpx.Client(transport=transport),
    )
    service = AgentRunOrchestrationService(client=client)

    service.dispatch_session_run(
        session=session,
        user=user,
        prompt="Prompt",
        knowledge_scope="my",
    )

    token = captured_headers["x-delegated-token"]
    payload = jwt.decode(
        token,
        settings.SECRET_KEY,
        algorithms=["HS256"],
        audience="mwalimu-knowledge-gateway",
        issuer="mwalimu-platform-api",
    )
    assert payload["context"]["knowledge_scope"] == "my"


@pytest.mark.django_db
def test_orchestration_defaults_knowledge_scope_to_relevant(
    session: AgentSession, user: User
) -> None:
    """Without an explicit scope the delegated token defaults to 'relevant'."""
    import jwt
    from django.conf import settings

    captured_headers: dict[str, str] = {}

    def mock_handler(request: httpx.Request) -> httpx.Response:
        captured_headers.update(dict(request.headers))
        return httpx.Response(
            status_code=202,
            json={
                "id": str(uuid.uuid4()),
                "session_id": str(session.pk),
                "status": "queued",
                "prompt": "Prompt",
                "created_at": "2026-08-23T15:00:00Z",
            },
        )

    transport = httpx.MockTransport(mock_handler)
    client = AgentServiceClient(
        base_url="http://agent-service.test",
        client=httpx.Client(transport=transport),
    )
    service = AgentRunOrchestrationService(client=client)

    service.dispatch_session_run(session=session, user=user, prompt="Prompt")

    token = captured_headers["x-delegated-token"]
    payload = jwt.decode(
        token,
        settings.SECRET_KEY,
        algorithms=["HS256"],
        audience="mwalimu-knowledge-gateway",
        issuer="mwalimu-platform-api",
    )
    assert payload["context"]["knowledge_scope"] == "relevant"


@pytest.mark.django_db
def test_orchestration_forwards_learner_preferences(
    session: AgentSession, user: User
) -> None:
    """Persisted learner preferences are forwarded in the agent dispatch payload."""
    import json

    from platform_api.apps.users.models import UserPreference

    UserPreference.objects.get_or_create(
        user=user,
        defaults={
            "pedagogical_style": "socratic",
            "explanation_depth": "in_depth",
            "response_language": "sw",
        },
    )

    captured_payload: dict[str, Any] = {}

    def mock_handler(request: httpx.Request) -> httpx.Response:
        captured_payload.update(json.loads(request.content.decode()))
        return httpx.Response(
            status_code=202,
            json={
                "id": str(uuid.uuid4()),
                "session_id": str(session.pk),
                "status": "queued",
                "prompt": "Prompt",
                "created_at": "2026-08-23T15:00:00Z",
            },
        )

    transport = httpx.MockTransport(mock_handler)
    client = AgentServiceClient(
        base_url="http://agent-service.test",
        client=httpx.Client(transport=transport),
    )
    service = AgentRunOrchestrationService(client=client)

    service.dispatch_session_run(session=session, user=user, prompt="Prompt")

    assert captured_payload["preferences"] == {
        "pedagogical_style": "socratic",
        "explanation_depth": "in_depth",
        "response_language": "sw",
    }


@pytest.mark.django_db
def test_orchestration_forwards_no_preferences_when_absent(
    session: AgentSession, user: User
) -> None:
    """A user with no preferences record still dispatches (preferences absent)."""
    import json

    captured_payload: dict[str, Any] = {}

    def mock_handler(request: httpx.Request) -> httpx.Response:
        captured_payload.update(json.loads(request.content.decode()))
        return httpx.Response(
            status_code=202,
            json={
                "id": str(uuid.uuid4()),
                "session_id": str(session.pk),
                "status": "queued",
                "prompt": "Prompt",
                "created_at": "2026-08-23T15:00:00Z",
            },
        )

    transport = httpx.MockTransport(mock_handler)
    client = AgentServiceClient(
        base_url="http://agent-service.test",
        client=httpx.Client(transport=transport),
    )
    service = AgentRunOrchestrationService(client=client)

    service.dispatch_session_run(session=session, user=user, prompt="Prompt")

    assert "preferences" not in captured_payload


@pytest.mark.django_db
def test_orchestration_handles_agent_service_connection_error(
    session: AgentSession, user: User
) -> None:
    """Connection failure transitions AgentRunRecord to FAILED with error details."""

    def mock_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Failed to connect")

    transport = httpx.MockTransport(mock_handler)
    client = AgentServiceClient(
        base_url="http://dead-service.test",
        client=httpx.Client(transport=transport),
    )
    service = AgentRunOrchestrationService(client=client)

    with pytest.raises(AgentServiceUnavailableError) as exc_info:
        service.dispatch_session_run(
            session=session,
            user=user,
            prompt="Prompt on dead service",
        )

    run_record = exc_info.value.run_record
    assert run_record is not None
    run_record.refresh_from_db()
    assert run_record.status == AgentRunStatus.FAILED
    assert run_record.error_code == "AGENT_SERVICE_UNAVAILABLE"
    assert run_record.finished_at is not None
    assert run_record.is_terminal is True


@pytest.mark.django_db
def test_orchestration_handles_agent_service_timeout(
    session: AgentSession, user: User
) -> None:
    """Timeout error transitions AgentRunRecord to FAILED."""

    def mock_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("Timeout after 30s")

    transport = httpx.MockTransport(mock_handler)
    client = AgentServiceClient(
        base_url="http://slow-service.test",
        client=httpx.Client(transport=transport),
    )
    service = AgentRunOrchestrationService(client=client)

    with pytest.raises(AgentServiceUnavailableError) as exc_info:
        service.dispatch_session_run(
            session=session,
            user=user,
            prompt="Prompt on slow service",
        )

    run_record = exc_info.value.run_record
    assert run_record is not None
    run_record.refresh_from_db()
    assert run_record.status == AgentRunStatus.FAILED
    assert run_record.error_code == "AGENT_SERVICE_UNAVAILABLE"


@pytest.mark.django_db
def test_orchestration_handles_agent_service_rejection(
    session: AgentSession, user: User
) -> None:
    """HTTP 400 rejection from Agent Service transitions AgentRunRecord to FAILED."""

    def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=400,
            json={"detail": "Invalid tool allowlist configuration."},
        )

    transport = httpx.MockTransport(mock_handler)
    client = AgentServiceClient(
        base_url="http://agent-service.test",
        client=httpx.Client(transport=transport),
    )
    service = AgentRunOrchestrationService(client=client)

    with pytest.raises(AgentServiceDispatchFailedError) as exc_info:
        service.dispatch_session_run(
            session=session,
            user=user,
            prompt="Invalid prompt",
        )

    run_record = exc_info.value.run_record
    assert run_record is not None
    run_record.refresh_from_db()
    assert run_record.status == AgentRunStatus.FAILED
    assert run_record.error_code == "DISPATCH_REJECTED_400"
    assert "Invalid tool allowlist" in run_record.error_message


@pytest.mark.django_db
def test_orchestration_passes_hydrated_conversation_history(
    session: AgentSession, user: User
) -> None:
    """Orchestrator includes hydrated prior session messages in dispatch payload."""
    import json

    from platform_api.apps.agents.models import AgentSessionMessage, MessageRole

    # Populate canonical history
    AgentSessionMessage.objects.create(
        session=session,
        role=MessageRole.USER,
        content="Prior question",
        sequence=0,
    )
    AgentSessionMessage.objects.create(
        session=session,
        role=MessageRole.ASSISTANT,
        content="Prior answer",
        sequence=1,
    )

    captured_payload: dict[str, Any] = {}

    def mock_handler(request: httpx.Request) -> httpx.Response:
        captured_payload.update(json.loads(request.content.decode()))
        return httpx.Response(
            status_code=202,
            json={
                "id": str(uuid.uuid4()),
                "session_id": str(session.pk),
                "status": "queued",
                "prompt": "Follow up question",
                "created_at": "2026-08-23T15:00:00Z",
            },
        )

    transport = httpx.MockTransport(mock_handler)
    client = AgentServiceClient(
        base_url="http://agent-service.test",
        client=httpx.Client(transport=transport),
    )
    service = AgentRunOrchestrationService(client=client)

    service.dispatch_session_run(
        session=session,
        user=user,
        prompt="Follow up question",
    )

    assert "conversation_history" in captured_payload
    history = captured_payload["conversation_history"]
    assert len(history) == 2
    assert history[0] == {"role": "user", "content": "Prior question"}
    assert history[1] == {"role": "assistant", "content": "Prior answer"}


@pytest.mark.django_db
def test_orchestration_dispatches_resolved_context_from_familiar_region(
    session: AgentSession, user: User
) -> None:
    """Resolved context (with items) is included in the agent dispatch payload."""
    import json

    from platform_api.apps.context.models import (
        ContextDomain,
        ContextResource,
        ContextResourceStatus,
        ContextScopeType,
        GeographicUnit,
        GeographicUnitStatus,
        GeographicUnitType,
        UserFamiliarRegion,
    )

    unit = GeographicUnit.objects.create(
        name="Tororo",
        slug="tororo",
        unit_type=GeographicUnitType.DISTRICT,
        status=GeographicUnitStatus.ACTIVE,
        country_code="UG",
    )
    domain = ContextDomain.objects.create(name="Agriculture", slug="agriculture")
    ContextResource.objects.create(
        geographic_unit=unit,
        context_domain=domain,
        title="Tororo Farming",
        content="In Tororo the main food crops are cassava and maize.",
        scope_type=ContextScopeType.PLATFORM,
        status=ContextResourceStatus.ACTIVE,
        applicable_subjects=["agriculture"],
        applicable_topics=["crops"],
        pedagogical_purposes=["example"],
    )
    UserFamiliarRegion.objects.create(user=user, geographic_unit=unit, priority=1)

    captured_payload: dict[str, Any] = {}

    def mock_handler(request: httpx.Request) -> httpx.Response:
        captured_payload.update(json.loads(request.content.decode()))
        return httpx.Response(
            status_code=202,
            json={
                "id": str(uuid.uuid4()),
                "session_id": str(session.pk),
                "status": "queued",
                "prompt": "Prompt",
                "created_at": "2026-08-23T15:00:00Z",
            },
        )

    transport = httpx.MockTransport(mock_handler)
    client = AgentServiceClient(
        base_url="http://agent-service.test",
        client=httpx.Client(transport=transport),
    )
    service = AgentRunOrchestrationService(client=client)

    service.dispatch_session_run(
        session=session,
        user=user,
        prompt="Explain how farming works in my area",
    )

    context = captured_payload.get("context")
    assert context is not None
    assert context["context_considered"] is True
    assert context["familiar_regions_considered"] is True
    assert len(context["items"]) == 1
    assert context["items"][0]["geographic_unit_name"] == "Tororo"


@pytest.mark.django_db
def test_orchestration_resolved_context_empty_for_memberless_user(
    session: AgentSession, user: User
) -> None:
    """A memberless user with no context triggers no behavioral context injection."""
    import json

    captured_payload: dict[str, Any] = {}

    def mock_handler(request: httpx.Request) -> httpx.Response:
        captured_payload.update(json.loads(request.content.decode()))
        return httpx.Response(
            status_code=202,
            json={
                "id": str(uuid.uuid4()),
                "session_id": str(session.pk),
                "status": "queued",
                "prompt": "Prompt",
                "created_at": "2026-08-23T15:00:00Z",
            },
        )

    transport = httpx.MockTransport(mock_handler)
    client = AgentServiceClient(
        base_url="http://agent-service.test",
        client=httpx.Client(transport=transport),
    )
    service = AgentRunOrchestrationService(client=client)

    service.dispatch_session_run(
        session=session,
        user=user,
        prompt="Explain quickly what gravity is",
    )

    context = captured_payload.get("context")
    assert context is not None
    assert context["context_considered"] is False
    assert context["items"] == []
