"""Domain protocols and capability interfaces for the Agent Service."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from .context import ExecutionContext
from .message import ModelMessage, ModelResponse, ModelStreamChunk, ToolResult


@dataclass(frozen=True)
class ToolDefinition:
    """Capability specification and parameter schema exposed to models."""

    name: str
    description: str
    parameters_schema: dict[str, Any]


@runtime_checkable
class ToolProtocol(Protocol):
    """Abstract protocol for all executable capabilities (native, gateway, MCP)."""

    @property
    def definition(self) -> ToolDefinition:
        """Return the capability definition and JSON schema."""
        ...

    async def execute(
        self,
        arguments: dict[str, Any],
        context: ExecutionContext,
        cancellation_token: asyncio.Event | None = None,
    ) -> ToolResult:
        """Execute the capability within the given execution context.

        Args:
            arguments: Validated parameter dictionary.
            context: Immutable execution context.
            cancellation_token: Optional cancellation event.

        Returns:
            Structured ToolResult.
        """
        ...


@runtime_checkable
class ModelProviderProtocol(Protocol):
    """Minimal, focused protocol for model inference in the Agent Runtime."""

    @property
    def provider_name(self) -> str:
        """Return provider identifier (e.g. openai, gemini, deepseek)."""
        ...

    @property
    def default_model(self) -> str:
        """Return default model identifier."""
        ...

    async def generate(
        self,
        messages: list[ModelMessage],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        cancellation_token: asyncio.Event | None = None,
    ) -> ModelResponse:
        """Execute non-streaming completion."""
        ...

    def stream_generate(
        self,
        messages: list[ModelMessage],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        cancellation_token: asyncio.Event | None = None,
    ) -> AsyncIterator[ModelStreamChunk]:
        """Stream token chunks and partial tool calls."""
        ...
