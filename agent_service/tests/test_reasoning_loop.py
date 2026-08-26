"""Comprehensive unit and integration tests for ReasoningLoop orchestrator."""

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from agent_service.application.reasoning_loop import ReasoningLoop
from agent_service.application.use_cases import (
    build_context_advisory,
    build_learner_adaptation,
)
from agent_service.domain.context import ExecutionContext
from agent_service.domain.message import (
    MessageRole,
    ModelMessage,
    ModelStreamChunk,
    ModelUsage,
    ToolCallRequest,
)
from agent_service.domain.run import AgentRun, RunStatus
from agent_service.infrastructure.credential_vault import DelegatedCredentialVault
from agent_service.infrastructure.model_gateway.errors import ModelRateLimitError
from agent_service.infrastructure.model_gateway.fake_provider import FakeModelProvider
from agent_service.infrastructure.tool_registry import ToolRegistry
from agent_service.infrastructure.tools.calculator import CalculatorTool
from agent_service.infrastructure.tools.knowledge_search import KnowledgeSearchTool
from agent_service.presentation.schemas import (
    ContextItemPayload,
    LearnerPreferencesPayload,
    ResolvedContextPayload,
)


def _create_context(
    max_steps: int = 10,
    timeout_seconds: float = 60.0,
    allowlist: frozenset[str] | None = None,
) -> ExecutionContext:
    return ExecutionContext(
        user_id=uuid.uuid4(),
        agent_run_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        max_steps=max_steps,
        timeout_seconds=timeout_seconds,
        tool_allowlist=allowlist,
    )


@pytest.mark.asyncio
async def test_reasoning_loop_final_answer_without_tools() -> None:
    """Model immediately produces answer -> run completes cleanly in 1 step."""
    provider = FakeModelProvider()
    provider.add_response(
        content="Paris is the capital of France.",
        prompt_tokens=15,
        completion_tokens=8,
    )

    registry = ToolRegistry([CalculatorTool()])
    loop = ReasoningLoop(model_provider=provider, tool_registry=registry)

    context = _create_context()
    run = AgentRun(id=context.agent_run_id, context=context)

    result_run = await loop.execute_run(
        run=run,
        context=context,
        initial_user_prompt="What is the capital of France?",
    )

    assert result_run.status == RunStatus.COMPLETED
    assert result_run.answer == "Paris is the capital of France."
    assert result_run.step_count == 1
    assert result_run.total_prompt_tokens == 15
    assert result_run.total_completion_tokens == 8
    assert result_run.finished_at is not None


@pytest.mark.asyncio
async def test_reasoning_loop_single_tool_call_cycle() -> None:
    """Model calls calculator -> gets result -> produces final answer."""
    provider = FakeModelProvider()
    # Turn 1: model requests calculator
    tc = ToolCallRequest(
        call_id="c1",
        tool_name="calculator",
        arguments_json='{"expression": "12 * 12"}',
    )
    provider.add_response(
        content=None,
        tool_calls=[tc],
        finish_reason="tool_calls",
        prompt_tokens=20,
        completion_tokens=10,
    )
    # Turn 2: model uses tool result to answer
    provider.add_response(
        content="12 multiplied by 12 is 144.",
        prompt_tokens=35,
        completion_tokens=12,
    )

    registry = ToolRegistry([CalculatorTool()])
    loop = ReasoningLoop(model_provider=provider, tool_registry=registry)

    context = _create_context()
    run = AgentRun(id=context.agent_run_id, context=context)

    result_run = await loop.execute_run(
        run=run,
        context=context,
        initial_user_prompt="Calculate 12 * 12",
    )

    assert result_run.status == RunStatus.COMPLETED
    assert result_run.answer == "12 multiplied by 12 is 144."
    assert result_run.step_count == 2
    assert result_run.total_prompt_tokens == 55
    assert result_run.total_completion_tokens == 22


@pytest.mark.asyncio
async def test_reasoning_loop_multiple_tool_calls_in_one_turn() -> None:
    """Model requests 2 tool calls in a single turn -> both execute and return."""
    provider = FakeModelProvider()
    tc1 = ToolCallRequest(
        call_id="c1",
        tool_name="calculator",
        arguments_json='{"expression": "10 + 5"}',
    )
    tc2 = ToolCallRequest(
        call_id="c2",
        tool_name="calculator",
        arguments_json='{"expression": "20 * 3"}',
    )
    provider.add_response(
        content=None,
        tool_calls=[tc1, tc2],
        finish_reason="tool_calls",
    )
    provider.add_response(content="10+5 is 15 and 20*3 is 60.")

    registry = ToolRegistry([CalculatorTool()])
    loop = ReasoningLoop(model_provider=provider, tool_registry=registry)

    context = _create_context()
    run = AgentRun(id=context.agent_run_id, context=context)

    result_run = await loop.execute_run(
        run=run,
        context=context,
        initial_user_prompt="Compute 10+5 and 20*3",
    )

    assert result_run.status == RunStatus.COMPLETED
    assert result_run.answer == "10+5 is 15 and 20*3 is 60."
    assert result_run.step_count == 2


@pytest.mark.asyncio
async def test_reasoning_loop_preserves_evidence_citations() -> None:
    """KnowledgeSearchTool citation evidence is accumulated on final AgentRun."""
    vault = DelegatedCredentialVault()
    context = _create_context()
    vault.store(context.agent_run_id, "test-token")

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    res_id = str(uuid.uuid4())
    lib_id = str(uuid.uuid4())
    chunk_id = str(uuid.uuid4())

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "query": "mitochondria ATP",
        "result_count": 1,
        "embedding_model": "text-embedding-3-small",
        "embedding_version": "1",
        "results": [
            {
                "chunk_id": chunk_id,
                "score": 0.95,
                "text": "Mitochondria produce ATP via oxidative phosphorylation.",
                "provenance": {
                    "resource_id": res_id,
                    "resource_name": "CellBio.pdf",
                    "library_id": lib_id,
                    "library_name": "Bio Lib",
                    "page_start": 105,
                    "page_end": 106,
                    "section": "Chapter 6",
                    "sequence": 3,
                    "char_start": 500,
                    "char_end": 1200,
                    "content_sha256": "sha256abc",
                },
            }
        ],
        "metadata": {"search_time_ms": 12},
    }
    mock_client.post.return_value = mock_resp

    search_tool = KnowledgeSearchTool(credential_vault=vault, http_client=mock_client)
    registry = ToolRegistry([search_tool])

    provider = FakeModelProvider()
    tc = ToolCallRequest(
        call_id="c1",
        tool_name="knowledge_search",
        arguments_json='{"query": "mitochondria ATP"}',
    )
    provider.add_response(content=None, tool_calls=[tc], finish_reason="tool_calls")
    provider.add_response(
        content="Mitochondria produce ATP as the energy currency of the cell."
    )

    loop = ReasoningLoop(model_provider=provider, tool_registry=registry)
    run = AgentRun(id=context.agent_run_id, context=context)

    result_run = await loop.execute_run(
        run=run,
        context=context,
        initial_user_prompt="What do mitochondria produce?",
    )

    assert result_run.status == RunStatus.COMPLETED
    assert len(result_run.citations) == 1
    cit = result_run.citations[0]
    assert cit.resource_name == "CellBio.pdf"
    assert cit.page_start == 105
    assert cit.score == 0.95


@pytest.mark.asyncio
async def test_reasoning_loop_step_budget_exhaustion() -> None:
    """Run transitions to TIMED_OUT when exceeding max_steps."""
    provider = FakeModelProvider()
    tc = ToolCallRequest(
        call_id="c1",
        tool_name="calculator",
        arguments_json='{"expression": "1 + 1"}',
    )
    for _ in range(10):
        provider.add_response(content=None, tool_calls=[tc], finish_reason="tool_calls")

    registry = ToolRegistry([CalculatorTool()])
    loop = ReasoningLoop(
        model_provider=provider,
        tool_registry=registry,
        max_identical_tool_calls=10,
    )

    context = _create_context(max_steps=3)
    run = AgentRun(id=context.agent_run_id, context=context)

    result_run = await loop.execute_run(
        run=run,
        context=context,
        initial_user_prompt="Loop forever",
    )

    assert result_run.status == RunStatus.TIMED_OUT
    assert "MAX_STEPS_EXCEEDED" in (result_run.error_message or "")
    assert result_run.step_count == 3


@pytest.mark.asyncio
async def test_reasoning_loop_total_timeout() -> None:
    """Run transitions to TIMED_OUT when duration exceeds timeout_seconds."""
    from agent_service.domain.protocols import ToolDefinition, ToolProtocol

    class SlowTool(ToolProtocol):
        @property
        def definition(self) -> ToolDefinition:
            return ToolDefinition(
                name="slow_tool",
                description="Slow",
                parameters_schema={"type": "object"},
            )

        async def execute(
            self,
            arguments: dict,
            context: ExecutionContext,
            cancellation_token=None,
        ):
            await asyncio.sleep(0.5)
            return None  # type: ignore

    provider = FakeModelProvider()
    tc = ToolCallRequest(call_id="c1", tool_name="slow_tool", arguments_json="{}")
    provider.add_response(content=None, tool_calls=[tc])

    registry = ToolRegistry([SlowTool()], default_timeout=5.0)
    loop = ReasoningLoop(model_provider=provider, tool_registry=registry)

    context = _create_context(timeout_seconds=0.1)
    run = AgentRun(id=context.agent_run_id, context=context)

    result_run = await loop.execute_run(
        run=run,
        context=context,
        initial_user_prompt="Execute slow tool",
    )

    assert result_run.status == RunStatus.TIMED_OUT
    assert "TOTAL_RUN_TIMEOUT_EXCEEDED" in (result_run.error_message or "")


@pytest.mark.asyncio
async def test_reasoning_loop_cancellation() -> None:
    """Signaled cancellation event transitions run to CANCELLED state immediately."""
    provider = FakeModelProvider()
    registry = ToolRegistry([CalculatorTool()])
    loop = ReasoningLoop(model_provider=provider, tool_registry=registry)

    context = _create_context()
    run = AgentRun(id=context.agent_run_id, context=context)

    token = asyncio.Event()
    token.set()  # Cancelled before start

    result_run = await loop.execute_run(
        run=run,
        context=context,
        initial_user_prompt="Hello",
        cancellation_token=token,
    )

    assert result_run.status == RunStatus.CANCELLED
    assert result_run.error_code == "CANCELLED"


@pytest.mark.asyncio
async def test_reasoning_loop_cycle_detection() -> None:
    """Repeated identical tool calls trigger LOOP_DETECTED failure."""
    provider = FakeModelProvider()
    tc = ToolCallRequest(
        call_id="c1",
        tool_name="calculator",
        arguments_json='{"expression": "2 + 2"}',
    )
    for _ in range(5):
        provider.add_response(content=None, tool_calls=[tc], finish_reason="tool_calls")

    registry = ToolRegistry([CalculatorTool()])
    loop = ReasoningLoop(
        model_provider=provider,
        tool_registry=registry,
        max_identical_tool_calls=3,
    )

    context = _create_context(max_steps=10)
    run = AgentRun(id=context.agent_run_id, context=context)

    result_run = await loop.execute_run(
        run=run,
        context=context,
        initial_user_prompt="Loop cycle test",
    )

    assert result_run.status == RunStatus.FAILED
    assert result_run.error_code == "LOOP_DETECTED"
    assert "Repeated identical tool call sequence" in (result_run.error_message or "")


@pytest.mark.asyncio
async def test_reasoning_loop_model_provider_error() -> None:
    """ModelProviderError transitions run to FAILED state with error code."""
    provider = FakeModelProvider()
    provider.error_to_raise = ModelRateLimitError(
        "Rate limit exceeded by provider", provider="openai"
    )

    registry = ToolRegistry([CalculatorTool()])
    loop = ReasoningLoop(model_provider=provider, tool_registry=registry)

    context = _create_context()
    run = AgentRun(id=context.agent_run_id, context=context)

    result_run = await loop.execute_run(
        run=run,
        context=context,
        initial_user_prompt="Test error",
    )

    assert result_run.status == RunStatus.FAILED
    assert result_run.error_code == "ModelRateLimitError"
    assert "Rate limit exceeded" in (result_run.error_message or "")


@pytest.mark.asyncio
async def test_reasoning_loop_tool_error_self_correction() -> None:
    """Tool execution errors are fed back to model allowing graceful recovery."""
    provider = FakeModelProvider()
    # 1. Model attempts division by zero
    tc = ToolCallRequest(
        call_id="c1",
        tool_name="calculator",
        arguments_json='{"expression": "10 / 0"}',
    )
    provider.add_response(content=None, tool_calls=[tc])
    # 2. Model receives division by zero error in tool result and apologizes
    provider.add_response(
        content="I cannot divide by zero as it is mathematically undefined."
    )

    registry = ToolRegistry([CalculatorTool()])
    loop = ReasoningLoop(model_provider=provider, tool_registry=registry)

    context = _create_context()
    run = AgentRun(id=context.agent_run_id, context=context)

    result_run = await loop.execute_run(
        run=run,
        context=context,
        initial_user_prompt="Divide 10 by 0",
    )

    assert result_run.status == RunStatus.COMPLETED
    assert "cannot divide by zero" in (result_run.answer or "")
    assert result_run.step_count == 2


@pytest.mark.asyncio
async def test_reasoning_loop_streams_deltas_to_consumer() -> None:
    """On_delta triggers the streaming path and forwards content deltas."""
    provider = FakeModelProvider()
    provider.stream_chunks = [
        ModelStreamChunk(delta_content="Hello "),
        ModelStreamChunk(delta_content="world!"),
        ModelStreamChunk(
            delta_content="",
            finish_reason="stop",
            usage=ModelUsage(prompt_tokens=5, completion_tokens=2, total_tokens=7),
        ),
    ]

    registry = ToolRegistry([CalculatorTool()])
    loop = ReasoningLoop(model_provider=provider, tool_registry=registry)

    context = _create_context()
    run = AgentRun(id=context.agent_run_id, context=context)
    deltas: list[str] = []

    result_run = await loop.execute_run(
        run=run,
        context=context,
        initial_user_prompt="Say hello",
        on_delta=lambda text: deltas.append(text),
    )

    assert result_run.status == RunStatus.COMPLETED
    assert result_run.answer == "Hello world!"
    assert "".join(deltas) == "Hello world!"
    assert result_run.total_prompt_tokens == 5
    assert result_run.total_completion_tokens == 2


@pytest.mark.asyncio
async def test_reasoning_loop_injects_context_advisory_into_system_prompt() -> None:
    """Resolved-context advisory reaches the model; history preserved."""
    provider = FakeModelProvider()
    provider.add_response(content="Grounded answer.")
    registry = ToolRegistry([CalculatorTool()])
    loop = ReasoningLoop(model_provider=provider, tool_registry=registry)

    context = _create_context()
    run = AgentRun(id=context.agent_run_id, context=context)
    advisory = build_context_advisory(
        ResolvedContextPayload(
            context_considered=True,
            items=[
                ContextItemPayload(
                    resource_id=uuid.uuid4(),
                    geographic_unit_id=uuid.uuid4(),
                    geographic_unit_name="Tororo",
                    geographic_unit_type="district",
                    context_domain="agriculture",
                    title="Tororo Farming",
                    content="In Tororo the main food crops are cassava and maize.",
                    applicable_subjects=["agriculture"],
                    applicable_topics=["crops"],
                    pedagogical_purposes=["example"],
                    source_type="platform",
                    selection_reason="Matched user familiar region.",
                )
            ],
        )
    )

    result_run = await loop.execute_run(
        run=run,
        context=context,
        initial_user_prompt="Explain farming",
        conversation_history=[
            ModelMessage(role=MessageRole.USER, content="Earlier question"),
            ModelMessage(role=MessageRole.ASSISTANT, content="Earlier answer"),
        ],
        context_advisory=advisory,
    )

    assert result_run.status == RunStatus.COMPLETED
    assert result_run.answer == "Grounded answer."
    sent = provider.received_messages[0]
    assert sent[0].role == MessageRole.SYSTEM
    assert "Tororo" in sent[0].content
    assert "cassava" in sent[0].content
    assert any(m.content == "Earlier question" for m in sent)
    assert sent[-1].content == "Explain farming"


@pytest.mark.asyncio
async def test_reasoning_loop_without_context_uses_default_prompt() -> None:
    """Absent context leaves the system prompt unchanged (memberless)."""
    provider = FakeModelProvider()
    provider.add_response(content="Plain answer.")
    registry = ToolRegistry([CalculatorTool()])
    loop = ReasoningLoop(model_provider=provider, tool_registry=registry)

    context = _create_context()
    run = AgentRun(id=context.agent_run_id, context=context)

    result_run = await loop.execute_run(
        run=run,
        context=context,
        initial_user_prompt="Hello",
    )

    assert result_run.status == RunStatus.COMPLETED
    sent = provider.received_messages[0]
    assert sent[0].role == MessageRole.SYSTEM
    assert "Relevant learning context" not in (sent[0].content or "")
    assert sent[-1].content == "Hello"


def test_context_advisory_builder_returns_empty_for_no_context() -> None:
    """No resolved context -> no advisory block (no behavior change)."""
    assert build_context_advisory(None) == ""
    assert build_context_advisory(ResolvedContextPayload()) == ""


@pytest.mark.asyncio
async def test_learner_adaptation_builder_maps_preferences() -> None:
    """pedagogical_style, explanation_depth, response_language map to instructions."""
    s = build_learner_adaptation(
        LearnerPreferencesPayload(
            pedagogical_style="socratic",
            explanation_depth="in_depth",
            response_language="sw",
        )
    )
    assert "Socratic" in s
    assert "in-depth" in s
    assert "Kiswahili" in s

    s2 = build_learner_adaptation(
        LearnerPreferencesPayload(pedagogical_style="intuitive", response_language="en")
    )
    assert "analogy" in s2.lower()
    assert "Kiswahili" not in s2

    # Unsupported language is silently ignored (no broken-language instruction).
    s3 = build_learner_adaptation(LearnerPreferencesPayload(response_language="xx"))
    assert "Respond in" not in s3

    assert build_learner_adaptation(None) == ""


@pytest.mark.asyncio
async def test_reasoning_loop_injects_learner_adaptation() -> None:
    """Learner preferences reach the model as an adaptation segment of the prompt."""
    provider = FakeModelProvider()
    provider.add_response(content="A short response.")
    registry = ToolRegistry([CalculatorTool()])
    loop = ReasoningLoop(model_provider=provider, tool_registry=registry)

    context = _create_context()
    run = AgentRun(id=context.agent_run_id, context=context)

    result_run = await loop.execute_run(
        run=run,
        context=context,
        initial_user_prompt="Explain osmosis.",
        learner_adaptation=build_learner_adaptation(
            LearnerPreferencesPayload(pedagogical_style="socratic")
        ),
    )

    assert result_run.status == RunStatus.COMPLETED
    system = (provider.received_messages[0][0].content or "")
    assert "Learner teaching preferences" in system
    assert "Socratic" in system


class SequenceStreamProvider(FakeModelProvider):
    """Streams a different chunk sequence on each call (multi-turn streaming)."""

    def __init__(self, sequences: list[list[ModelStreamChunk]]) -> None:
        super().__init__()
        self._sequences = sequences
        self._call_index = 0

    async def stream_generate(
        self,
        messages: list[ModelMessage],
        tools: list[object] | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        cancellation_token: asyncio.Event | None = None,
    ):
        seq = self._sequences[min(self._call_index, len(self._sequences) - 1)]
        self._call_index += 1
        for c in seq:
            if cancellation_token and cancellation_token.is_set():
                raise asyncio.CancelledError("Stream cancelled.")
            yield c


@pytest.mark.asyncio
async def test_streamed_tool_call_is_reconstructed_and_executed() -> None:
    """Streamed tool-call fragments (id on first chunk only) are rebuilt and run."""
    provider = SequenceStreamProvider(
        [
            [
                ModelStreamChunk(
                    delta_tool_call=ToolCallRequest(
                        call_id="c1", tool_name="calculator", arguments_json=""
                    )
                ),
                ModelStreamChunk(
                    delta_tool_call=ToolCallRequest(
                        call_id="", tool_name="", arguments_json='{"expression": "2+2"}'
                    )
                ),
                ModelStreamChunk(
                    delta_content="",
                    finish_reason="tool_calls",
                    usage=ModelUsage(
                        prompt_tokens=5, completion_tokens=1, total_tokens=6
                    ),
                ),
            ],
            [
                ModelStreamChunk(delta_content="The answer is "),
                ModelStreamChunk(
                    delta_content="4.",
                    finish_reason="stop",
                    usage=ModelUsage(
                        prompt_tokens=5, completion_tokens=3, total_tokens=8
                    ),
                ),
            ],
        ]
    )

    registry = ToolRegistry([CalculatorTool()])
    loop = ReasoningLoop(model_provider=provider, tool_registry=registry)

    context = _create_context()
    run = AgentRun(id=context.agent_run_id, context=context)
    deltas: list[str] = []

    result_run = await loop.execute_run(
        run=run,
        context=context,
        initial_user_prompt="What is 2+2?",
        on_delta=lambda text: deltas.append(text),
    )

    assert result_run.status == RunStatus.COMPLETED
    assert result_run.answer == "The answer is 4."
    assert result_run.step_count == 2
    assert "".join(deltas) == "The answer is 4."


@pytest.mark.asyncio
async def test_reasoning_loop_system_prompt_encodes_teaching_protocol() -> None:
    """Mwalimu's system prompt encodes a teach + comprehension-check protocol."""
    provider = FakeModelProvider()
    provider.add_response(content="A short teaching response.")
    registry = ToolRegistry([CalculatorTool()])
    loop = ReasoningLoop(model_provider=provider, tool_registry=registry)

    context = _create_context()
    run = AgentRun(id=context.agent_run_id, context=context)

    result_run = await loop.execute_run(
        run=run,
        context=context,
        initial_user_prompt="What is osmosis?",
    )

    assert result_run.status == RunStatus.COMPLETED
    system = (provider.received_messages[0][0].content or "")
    assert "comprehension question" in system
    assert "misconception" in system
    assert "Do NOT turn ordinary requests into a quiz" in system
    assert "Never fabricate a citation" in system


@pytest.mark.asyncio
async def test_reasoning_loop_reacts_to_answer_using_history() -> None:
    """A second turn is driven by the prior teaching turn in saved history."""
    provider = FakeModelProvider()
    provider.add_response(
        content="Exactly — water moves into the bean. That is osmosis."
    )
    registry = ToolRegistry([CalculatorTool()])
    loop = ReasoningLoop(model_provider=provider, tool_registry=registry)

    context = _create_context()
    run = AgentRun(id=context.agent_run_id, context=context)

    result_run = await loop.execute_run(
        run=run,
        context=context,
        initial_user_prompt="They become bigger.",
        conversation_history=[
            ModelMessage(role=MessageRole.USER, content="What is osmosis?"),
            ModelMessage(
                role=MessageRole.ASSISTANT,
                content=(
                    "Soaking dry beans overnight — what do you think happens to "
                    "the beans?"
                ),
            ),
        ],
    )

    assert result_run.status == RunStatus.COMPLETED
    sent = provider.received_messages[0]
    # history preserved with the teaching turn, followed by the new user answer
    assert sent[1].content == "What is osmosis?"
    assert "overnight" in (sent[2].content or "")
    assert sent[-1].content == "They become bigger."


@pytest.mark.asyncio
async def test_reasoning_loop_resumes_from_awaiting_input() -> None:
    """Run in AWAITING_INPUT state is resumed and completed with new input."""
    provider = FakeModelProvider()
    provider.add_response(content="Answer using provided follow-up info.")

    registry = ToolRegistry([CalculatorTool()])
    loop = ReasoningLoop(model_provider=provider, tool_registry=registry)

    context = _create_context()
    run = AgentRun(id=context.agent_run_id, context=context)
    run.dispatch()
    run.start()
    run.request_input()
    assert run.status == RunStatus.AWAITING_INPUT

    result_run = await loop.execute_run(
        run=run,
        context=context,
        initial_user_prompt="Here is my clarified question.",
    )

    assert result_run.status == RunStatus.COMPLETED
    assert result_run.answer == "Answer using provided follow-up info."
