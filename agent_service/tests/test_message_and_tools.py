"""Unit tests for domain messages, tool definitions, results, and protocols."""

import asyncio
import uuid
from collections.abc import AsyncIterator
from typing import Any

from agent_service.domain.context import ExecutionContext
from agent_service.domain.message import (
    EvidenceCitation,
    MessageRole,
    ModelMessage,
    ModelResponse,
    ModelStreamChunk,
    ModelUsage,
    ToolCallRequest,
    ToolResult,
)
from agent_service.domain.protocols import (
    ModelProviderProtocol,
    ToolDefinition,
    ToolProtocol,
)


def test_evidence_citation_initialization() -> None:
    """EvidenceCitation holds 14-field citation provenance."""
    res_id = uuid.uuid4()
    lib_id = uuid.uuid4()
    chunk_id = uuid.uuid4()

    citation = EvidenceCitation(
        resource_id=res_id,
        resource_name="Textbook.pdf",
        library_id=lib_id,
        library_name="Science Library",
        page_start=5,
        page_end=6,
        section="Chapter 2 > Cell Structure",
        sequence=1,
        char_start=100,
        char_end=250,
        content_sha256="sha-test-123",
        chunk_id=chunk_id,
        score=0.95,
    )

    assert citation.resource_id == res_id
    assert citation.resource_name == "Textbook.pdf"
    assert citation.library_id == lib_id
    assert citation.library_name == "Science Library"
    assert citation.page_start == 5
    assert citation.page_end == 6
    assert citation.section == "Chapter 2 > Cell Structure"
    assert citation.sequence == 1
    assert citation.char_start == 100
    assert citation.char_end == 250
    assert citation.content_sha256 == "sha-test-123"
    assert citation.chunk_id == chunk_id
    assert citation.score == 0.95


def test_model_message_and_roles() -> None:
    """ModelMessage represents system, user, assistant, and tool messages."""
    sys_msg = ModelMessage(role=MessageRole.SYSTEM, content="You are a tutor.")
    assert sys_msg.role == MessageRole.SYSTEM
    assert sys_msg.content == "You are a tutor."

    tc = ToolCallRequest(
        call_id="call-1",
        tool_name="knowledge_search",
        arguments_json='{"query": "photosynthesis"}',
    )
    asst_msg = ModelMessage(role=MessageRole.ASSISTANT, tool_calls=[tc])
    assert asst_msg.role == MessageRole.ASSISTANT
    assert asst_msg.tool_calls == [tc]

    tool_msg = ModelMessage(
        role=MessageRole.TOOL, content="Search results", tool_call_id="call-1"
    )
    assert tool_msg.role == MessageRole.TOOL
    assert tool_msg.tool_call_id == "call-1"


def test_model_usage_and_response() -> None:
    """ModelUsage tracks token consumption in ModelResponse."""
    usage = ModelUsage(prompt_tokens=150, completion_tokens=45, total_tokens=195)
    msg = ModelMessage(role=MessageRole.ASSISTANT, content="Done.")
    resp = ModelResponse(message=msg, finish_reason="stop", usage=usage)

    assert resp.message == msg
    assert resp.finish_reason == "stop"
    assert resp.usage.total_tokens == 195


class FakeTool:
    """Sample tool implementation for protocol compliance testing."""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="calculator",
            description="Perform basic math",
            parameters_schema={
                "type": "object",
                "properties": {"expression": {"type": "string"}},
                "required": ["expression"],
            },
        )

    async def execute(
        self,
        arguments: dict[str, Any],
        context: ExecutionContext,
        cancellation_token: asyncio.Event | None = None,
    ) -> ToolResult:
        return ToolResult(
            call_id="call-test",
            tool_name="calculator",
            success=True,
            output="42",
        )


class FakeModelProvider:
    """Sample model provider implementation for protocol compliance testing."""

    @property
    def provider_name(self) -> str:
        return "fake_provider"

    @property
    def default_model(self) -> str:
        return "fake-model-1"

    async def generate(
        self,
        messages: list[ModelMessage],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        cancellation_token: asyncio.Event | None = None,
    ) -> ModelResponse:
        return ModelResponse(
            message=ModelMessage(role=MessageRole.ASSISTANT, content="Fake answer"),
            finish_reason="stop",
            usage=ModelUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
        )

    async def stream_generate(
        self,
        messages: list[ModelMessage],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        cancellation_token: asyncio.Event | None = None,
    ) -> AsyncIterator[ModelStreamChunk]:
        yield ModelStreamChunk(delta_content="Fake ")
        yield ModelStreamChunk(delta_content="answer", finish_reason="stop")


def test_tool_protocol_compliance() -> None:
    """FakeTool satisfies ToolProtocol at runtime."""
    tool = FakeTool()
    assert isinstance(tool, ToolProtocol)
    assert tool.definition.name == "calculator"


def test_model_provider_protocol_compliance() -> None:
    """FakeModelProvider satisfies ModelProviderProtocol at runtime."""
    provider = FakeModelProvider()
    assert isinstance(provider, ModelProviderProtocol)
    assert provider.provider_name == "fake_provider"
    assert provider.default_model == "fake-model-1"
