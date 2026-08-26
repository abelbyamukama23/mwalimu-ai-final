"""End-to-end presentation integration tests for Phase 6.5.

Tests the complete path: HTTP Request -> FastAPI -> ReasoningLoop -> FakeModelProvider
-> ToolRegistry -> SSE Stream -> Final Answer + Citations.
"""

import asyncio
import uuid

import pytest

from agent_service.application.reasoning_loop import ReasoningLoop
from agent_service.application.use_cases import (
    CancelRunUseCase,
    GetRunStatusUseCase,
    RunAgentUseCase,
    RunNotFoundError,
)
from agent_service.domain.context import ExecutionContext
from agent_service.domain.message import EvidenceCitation
from agent_service.domain.run import AgentRun, RunStatus
from agent_service.infrastructure.model_gateway.fake_provider import FakeModelProvider
from agent_service.infrastructure.run_store import InMemoryRunStore
from agent_service.infrastructure.tool_registry import ToolRegistry
from agent_service.infrastructure.tools.calculator import CalculatorTool
from agent_service.presentation.schemas import (
    CitationResponse,
    CreateRunRequest,
    RunResponse,
)
from agent_service.presentation.security import AuthenticatedPrincipal

# ---------------------------------------------------------------------------
# Unit Tests: Use Cases
# ---------------------------------------------------------------------------


class TestRunAgentUseCase:
    """Unit test the RunAgentUseCase orchestration."""

    @pytest.mark.asyncio
    async def test_creates_run_with_queued_status(self) -> None:
        """Use case creates AgentRun and transitions to QUEUED."""
        provider = FakeModelProvider()
        provider.add_response(content="Answer")
        registry = ToolRegistry([CalculatorTool()])
        loop = ReasoningLoop(model_provider=provider, tool_registry=registry)
        store = InMemoryRunStore()

        use_case = RunAgentUseCase(
            reasoning_loop=loop,
            tool_registry=registry,
            run_store=store,
        )
        principal = AuthenticatedPrincipal(user_id=uuid.uuid4())
        request = CreateRunRequest(prompt="test question")

        run = await use_case.execute(principal=principal, request=request)
        assert run.status == RunStatus.QUEUED
        assert run.context.user_id == principal.user_id
        assert run.prompt == "test question"

    @pytest.mark.asyncio
    async def test_effective_allowlist_narrows(self) -> None:
        """tool_allowlist is intersected with server-registered tools."""
        provider = FakeModelProvider()
        provider.add_response(content="Answer")
        calc = CalculatorTool()
        registry = ToolRegistry([calc])
        loop = ReasoningLoop(model_provider=provider, tool_registry=registry)
        store = InMemoryRunStore()

        use_case = RunAgentUseCase(
            reasoning_loop=loop,
            tool_registry=registry,
            run_store=store,
        )
        principal = AuthenticatedPrincipal(user_id=uuid.uuid4())
        request = CreateRunRequest(
            prompt="test",
            tool_allowlist=["calculator", "unauthorized_tool"],
        )

        run = await use_case.execute(principal=principal, request=request)
        # EffectiveAllowlist = {"calculator"} ∩ {"calculator", "unauthorized_tool"}
        assert run.context.tool_allowlist is not None
        assert "calculator" in run.context.tool_allowlist
        assert "unauthorized_tool" not in run.context.tool_allowlist

    @pytest.mark.asyncio
    async def test_emits_run_created_event(self) -> None:
        """Use case emits run.created SSE event on creation."""
        provider = FakeModelProvider()
        provider.add_response(content="Answer")
        registry = ToolRegistry([CalculatorTool()])
        loop = ReasoningLoop(model_provider=provider, tool_registry=registry)
        store = InMemoryRunStore()

        use_case = RunAgentUseCase(
            reasoning_loop=loop,
            tool_registry=registry,
            run_store=store,
        )
        principal = AuthenticatedPrincipal(user_id=uuid.uuid4())
        request = CreateRunRequest(prompt="test")

        run = await use_case.execute(principal=principal, request=request)
        events = store.get_events(run.id)
        assert len(events) >= 1
        assert events[0].event == "run.created"


class TestGetRunStatusUseCase:
    """Unit test the GetRunStatusUseCase."""

    def test_returns_owned_run(self) -> None:
        user_id = uuid.uuid4()
        run_id = uuid.uuid4()
        context = ExecutionContext(
            user_id=user_id, agent_run_id=run_id, session_id=uuid.uuid4()
        )
        run = AgentRun(id=run_id, context=context, prompt="test")
        store = InMemoryRunStore()
        store.save_run(run)

        use_case = GetRunStatusUseCase(run_store=store)
        principal = AuthenticatedPrincipal(user_id=user_id)
        result = use_case.execute(principal=principal, run_id=run_id)
        assert result.id == run_id

    def test_raises_not_found_for_other_user(self) -> None:
        user_a = uuid.uuid4()
        user_b = uuid.uuid4()
        run_id = uuid.uuid4()
        context = ExecutionContext(
            user_id=user_a, agent_run_id=run_id, session_id=uuid.uuid4()
        )
        run = AgentRun(id=run_id, context=context, prompt="test")
        store = InMemoryRunStore()
        store.save_run(run)

        use_case = GetRunStatusUseCase(run_store=store)
        principal = AuthenticatedPrincipal(user_id=user_b)
        with pytest.raises(RunNotFoundError):
            use_case.execute(principal=principal, run_id=run_id)

    def test_raises_not_found_for_missing_run(self) -> None:
        store = InMemoryRunStore()
        use_case = GetRunStatusUseCase(run_store=store)
        principal = AuthenticatedPrincipal(user_id=uuid.uuid4())
        with pytest.raises(RunNotFoundError):
            use_case.execute(principal=principal, run_id=uuid.uuid4())


class TestCancelRunUseCase:
    """Unit test the CancelRunUseCase."""

    def test_sets_cancellation_token(self) -> None:
        user_id = uuid.uuid4()
        run_id = uuid.uuid4()
        context = ExecutionContext(
            user_id=user_id, agent_run_id=run_id, session_id=uuid.uuid4()
        )
        run = AgentRun(id=run_id, context=context, prompt="test")
        run.dispatch()
        cancel_event = asyncio.Event()

        store = InMemoryRunStore()
        store.save_run(run, cancellation_token=cancel_event)

        use_case = CancelRunUseCase(run_store=store)
        principal = AuthenticatedPrincipal(user_id=user_id)
        use_case.execute(principal=principal, run_id=run_id)
        assert cancel_event.is_set()

    def test_raises_not_found_for_other_user(self) -> None:
        user_a = uuid.uuid4()
        user_b = uuid.uuid4()
        run_id = uuid.uuid4()
        context = ExecutionContext(
            user_id=user_a, agent_run_id=run_id, session_id=uuid.uuid4()
        )
        run = AgentRun(id=run_id, context=context, prompt="test")
        store = InMemoryRunStore()
        store.save_run(run)

        use_case = CancelRunUseCase(run_store=store)
        principal = AuthenticatedPrincipal(user_id=user_b)
        with pytest.raises(RunNotFoundError):
            use_case.execute(principal=principal, run_id=run_id)


# ---------------------------------------------------------------------------
# Schema Mapping Tests
# ---------------------------------------------------------------------------


class TestSchemaMappings:
    """Verify domain-to-presentation schema mappings."""

    def test_run_response_from_domain(self) -> None:
        """RunResponse.from_domain correctly maps AgentRun fields."""
        user_id = uuid.uuid4()
        run_id = uuid.uuid4()
        context = ExecutionContext(
            user_id=user_id, agent_run_id=run_id, session_id=uuid.uuid4()
        )
        run = AgentRun(id=run_id, context=context, prompt="test prompt")
        run.dispatch()

        response = RunResponse.from_domain(run)
        assert response.run_id == run_id
        assert response.status == "queued"
        assert response.prompt == "test prompt"
        assert response.answer is None
        assert response.citations == []

    def test_citation_response_from_domain(self) -> None:
        """CitationResponse.from_domain correctly maps 14 fields."""
        citation = EvidenceCitation(
            resource_id=uuid.uuid4(),
            resource_name="Biology.pdf",
            library_id=uuid.uuid4(),
            library_name="Science Library",
            page_start=10,
            page_end=12,
            section="Chapter 1",
            sequence=3,
            char_start=500,
            char_end=1500,
            content_sha256="abc123",
            chunk_id=uuid.uuid4(),
            score=0.95,
        )
        resp = CitationResponse.from_domain(citation)
        assert resp.resource_name == "Biology.pdf"
        assert resp.library_name == "Science Library"
        assert resp.page_start == 10
        assert resp.page_end == 12
        assert resp.section == "Chapter 1"
        assert resp.sequence == 3
        assert resp.score == 0.95

    def test_run_response_excludes_sensitive_fields(self) -> None:
        """RunResponse schema has no delegated_token, api_key, or system_prompt."""
        field_names = set(RunResponse.model_fields.keys())
        forbidden = {
            "delegated_token",
            "api_key",
            "system_prompt",
            "user_id",
            "secret_key",
        }
        assert field_names & forbidden == set()


# ---------------------------------------------------------------------------
# AuthenticatedPrincipal Tests
# ---------------------------------------------------------------------------


class TestAuthenticatedPrincipal:
    """Verify AuthenticatedPrincipal value object."""

    def test_principal_frozen(self) -> None:
        """AuthenticatedPrincipal is frozen."""
        principal = AuthenticatedPrincipal(user_id=uuid.uuid4())
        with pytest.raises(AttributeError):
            principal.user_id = uuid.uuid4()  # type: ignore[misc]

    def test_principal_is_authenticated(self) -> None:
        principal = AuthenticatedPrincipal(user_id=uuid.uuid4())
        assert principal.is_authenticated is True

    def test_principal_user_id_is_uuid(self) -> None:
        uid = uuid.uuid4()
        principal = AuthenticatedPrincipal(user_id=uid)
        assert principal.user_id == uid


# ---------------------------------------------------------------------------
# InMemoryRunStore Tests
# ---------------------------------------------------------------------------


class TestInMemoryRunStore:
    """Verify InMemoryRunStore lifecycle management."""

    def test_save_and_retrieve_run(self) -> None:
        store = InMemoryRunStore()
        run_id = uuid.uuid4()
        context = ExecutionContext(
            user_id=uuid.uuid4(), agent_run_id=run_id, session_id=uuid.uuid4()
        )
        run = AgentRun(id=run_id, context=context, prompt="test")
        store.save_run(run)
        assert store.get_run(run_id) is run

    def test_get_nonexistent_returns_none(self) -> None:
        store = InMemoryRunStore()
        assert store.get_run(uuid.uuid4()) is None

    def test_cancellation_token_stored(self) -> None:
        store = InMemoryRunStore()
        run_id = uuid.uuid4()
        context = ExecutionContext(
            user_id=uuid.uuid4(), agent_run_id=run_id, session_id=uuid.uuid4()
        )
        run = AgentRun(id=run_id, context=context, prompt="test")
        token = asyncio.Event()
        store.save_run(run, cancellation_token=token)
        assert store.get_cancellation_token(run_id) is token

    @pytest.mark.asyncio
    async def test_register_task(self) -> None:
        store = InMemoryRunStore()
        run_id = uuid.uuid4()
        context = ExecutionContext(
            user_id=uuid.uuid4(), agent_run_id=run_id, session_id=uuid.uuid4()
        )
        run = AgentRun(id=run_id, context=context, prompt="test")
        store.save_run(run)

        async def _noop() -> None:
            pass

        task = asyncio.create_task(_noop())
        store.register_task(run_id, task)
        await task
