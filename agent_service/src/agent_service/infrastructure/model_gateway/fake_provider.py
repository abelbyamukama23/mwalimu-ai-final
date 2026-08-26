"""Deterministic in-memory FakeModelProvider for unit and integration testing."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from agent_service.domain.message import (
    MessageRole,
    ModelMessage,
    ModelResponse,
    ModelStreamChunk,
    ModelUsage,
    ToolCallRequest,
)
from agent_service.domain.protocols import ModelProviderProtocol, ToolDefinition


class FakeModelProvider(ModelProviderProtocol):
    """Deterministic model provider for tests without external network dependencies.

    Supports pre-configured responses, multi-step sequential responses,
    simulated tool calls, streaming simulation, and programmed exception triggers.
    """

    def __init__(
        self,
        provider_name: str = "fake",
        default_model: str = "fake-model-v1",
        responses: list[ModelResponse] | None = None,
        stream_chunks: list[ModelStreamChunk] | None = None,
        error_to_raise: Exception | None = None,
    ) -> None:
        self._provider_name = provider_name
        self._default_model = default_model
        self.responses = list(responses) if responses else []
        self.stream_chunks = list(stream_chunks) if stream_chunks else []
        self.error_to_raise = error_to_raise

        self.call_count = 0
        self.received_messages: list[list[ModelMessage]] = []
        self.received_tools: list[list[ToolDefinition] | None] = []

    @property
    def provider_name(self) -> str:
        return self._provider_name

    @property
    def default_model(self) -> str:
        return self._default_model

    def add_response(
        self,
        content: str | None = "Default fake answer.",
        tool_calls: list[ToolCallRequest] | None = None,
        finish_reason: str = "stop",
        prompt_tokens: int = 10,
        completion_tokens: int = 5,
    ) -> None:
        """Add a canned response to the sequential response queue."""
        resp = ModelResponse(
            message=ModelMessage(
                role=MessageRole.ASSISTANT,
                content=content,
                tool_calls=tool_calls,
            ),
            finish_reason=finish_reason,
            usage=ModelUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
            ),
        )
        self.responses.append(resp)

    async def generate(
        self,
        messages: list[ModelMessage],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        cancellation_token: asyncio.Event | None = None,
    ) -> ModelResponse:
        """Return next canned response or simulate error."""
        if cancellation_token and cancellation_token.is_set():
            raise asyncio.CancelledError("Operation cancelled before execution.")

        self.call_count += 1
        self.received_messages.append(messages)
        self.received_tools.append(tools)

        if self.error_to_raise:
            raise self.error_to_raise

        if self.responses:
            return self.responses.pop(0)

        # Default fallback response
        return ModelResponse(
            message=ModelMessage(
                role=MessageRole.ASSISTANT,
                content="Default deterministic response.",
            ),
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
        """Stream pre-configured chunks or simulate default streaming."""
        if cancellation_token and cancellation_token.is_set():
            raise asyncio.CancelledError("Operation cancelled before stream start.")

        self.call_count += 1
        self.received_messages.append(messages)
        self.received_tools.append(tools)

        if self.error_to_raise:
            raise self.error_to_raise

        if self.stream_chunks:
            for chunk in self.stream_chunks:
                if cancellation_token and cancellation_token.is_set():
                    raise asyncio.CancelledError("Stream cancelled by client.")
                yield chunk
            return

        # Default fallback stream
        chunks = [
            ModelStreamChunk(delta_content="Default "),
            ModelStreamChunk(delta_content="deterministic "),
            ModelStreamChunk(
                delta_content="response.",
                finish_reason="stop",
                usage=ModelUsage(
                    prompt_tokens=10, completion_tokens=5, total_tokens=15
                ),
            ),
        ]
        for c in chunks:
            if cancellation_token and cancellation_token.is_set():
                raise asyncio.CancelledError("Stream cancelled by client.")
            yield c
