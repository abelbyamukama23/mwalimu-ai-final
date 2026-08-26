"""Base OpenAI-compatible adapter implementing ModelProviderProtocol."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import openai
from openai import AsyncOpenAI

from agent_service.domain.message import (
    MessageRole,
    ModelMessage,
    ModelResponse,
    ModelStreamChunk,
    ModelUsage,
    ToolCallRequest,
)
from agent_service.domain.protocols import ModelProviderProtocol, ToolDefinition

from .errors import (
    ModelAuthenticationError,
    ModelInvalidRequestError,
    ModelProviderError,
    ModelRateLimitError,
    ModelTimeoutError,
    ModelUnavailableError,
)


class BaseOpenAIAdapter(ModelProviderProtocol):
    """Adapter wrapping AsyncOpenAI for OpenAI, Gemini, and DeepSeek endpoints.

    Translates Mwalimu domain message contracts to and from OpenAI-compatible schemas
    and standardizes error handling.
    """

    def __init__(
        self,
        provider_name: str,
        default_model: str,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout_seconds: float = 60.0,
        max_retries: int = 2,
        client: AsyncOpenAI | None = None,
    ) -> None:
        self._provider_name = provider_name
        self._default_model = default_model
        self._timeout_seconds = timeout_seconds

        if client is not None:
            self._client = client
        else:
            self._client = AsyncOpenAI(
                api_key=api_key or "placeholder-key",
                base_url=base_url,
                timeout=timeout_seconds,
                max_retries=max_retries,
            )

    @property
    def provider_name(self) -> str:
        return self._provider_name

    @property
    def default_model(self) -> str:
        return self._default_model

    def _convert_messages(self, messages: list[ModelMessage]) -> list[dict[str, Any]]:
        """Convert domain ModelMessage objects to OpenAI message dictionaries."""
        payload: list[dict[str, Any]] = []
        for msg in messages:
            if msg.role == MessageRole.SYSTEM:
                payload.append({"role": "system", "content": msg.content or ""})
            elif msg.role == MessageRole.USER:
                payload.append({"role": "user", "content": msg.content or ""})
            elif msg.role == MessageRole.ASSISTANT:
                asst_dict: dict[str, Any] = {
                    "role": "assistant",
                    "content": msg.content,
                }
                if msg.tool_calls:
                    asst_dict["tool_calls"] = [
                        {
                            "id": tc.call_id,
                            "type": "function",
                            "function": {
                                "name": tc.tool_name,
                                "arguments": tc.arguments_json,
                            },
                        }
                        for tc in msg.tool_calls
                    ]
                payload.append(asst_dict)
            elif msg.role == MessageRole.TOOL:
                payload.append(
                    {
                        "role": "tool",
                        "content": msg.content or "",
                        "tool_call_id": msg.tool_call_id or "",
                    }
                )
        return payload

    def _convert_tools(
        self, tools: list[ToolDefinition] | None
    ) -> list[dict[str, Any]] | None:
        """Convert domain ToolDefinition objects to OpenAI tool specifications."""
        if not tools:
            return None
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters_schema,
                },
            }
            for t in tools
        ]

    def _translate_exception(self, exc: Exception) -> ModelProviderError:
        """Translate OpenAI SDK exceptions into normalized domain exceptions."""
        msg = str(exc)
        if isinstance(exc, openai.AuthenticationError):
            return ModelAuthenticationError(msg, self.provider_name, exc)
        if isinstance(exc, openai.RateLimitError):
            return ModelRateLimitError(msg, self.provider_name, exc)
        if isinstance(exc, openai.APITimeoutError):
            return ModelTimeoutError(msg, self.provider_name, exc)
        if isinstance(exc, openai.APIConnectionError | openai.InternalServerError):
            return ModelUnavailableError(msg, self.provider_name, exc)
        if isinstance(exc, openai.BadRequestError):
            return ModelInvalidRequestError(msg, self.provider_name, exc)
        if isinstance(exc, openai.OpenAIError):
            return ModelProviderError(msg, self.provider_name, exc)
        return ModelProviderError(
            f"Unexpected provider error: {msg}", self.provider_name, exc
        )

    async def generate(
        self,
        messages: list[ModelMessage],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        cancellation_token: asyncio.Event | None = None,
    ) -> ModelResponse:
        """Execute non-streaming completion."""
        if cancellation_token and cancellation_token.is_set():
            raise asyncio.CancelledError("Operation cancelled before model invocation.")

        formatted_messages = self._convert_messages(messages)
        formatted_tools = self._convert_tools(tools)

        kwargs: dict[str, Any] = {
            "model": self.default_model,
            "messages": formatted_messages,
            "temperature": temperature,
        }
        if formatted_tools:
            kwargs["tools"] = formatted_tools
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens

        try:
            response = await self._client.chat.completions.create(**kwargs)
        except Exception as exc:
            raise self._translate_exception(exc) from exc

        choice = response.choices[0]
        raw_message = choice.message

        tool_calls: list[ToolCallRequest] | None = None
        if raw_message.tool_calls:
            tool_calls = [
                ToolCallRequest(
                    call_id=tc.id,
                    tool_name=tc.function.name,
                    arguments_json=tc.function.arguments,
                )
                for tc in raw_message.tool_calls
            ]

        model_msg = ModelMessage(
            role=MessageRole.ASSISTANT,
            content=raw_message.content,
            tool_calls=tool_calls,
        )

        usage = ModelUsage(
            prompt_tokens=response.usage.prompt_tokens if response.usage else 0,
            completion_tokens=response.usage.completion_tokens if response.usage else 0,
            total_tokens=response.usage.total_tokens if response.usage else 0,
        )

        return ModelResponse(
            message=model_msg,
            finish_reason=choice.finish_reason or "stop",
            usage=usage,
        )

    async def stream_generate(
        self,
        messages: list[ModelMessage],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        cancellation_token: asyncio.Event | None = None,
    ) -> AsyncIterator[ModelStreamChunk]:
        """Stream token deltas and partial tool calls."""
        if cancellation_token and cancellation_token.is_set():
            raise asyncio.CancelledError("Operation cancelled before stream start.")

        formatted_messages = self._convert_messages(messages)
        formatted_tools = self._convert_tools(tools)

        kwargs: dict[str, Any] = {
            "model": self.default_model,
            "messages": formatted_messages,
            "temperature": temperature,
            "stream": True,
        }
        if formatted_tools:
            kwargs["tools"] = formatted_tools
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens

        try:
            stream = await self._client.chat.completions.create(**kwargs)
        except Exception as exc:
            raise self._translate_exception(exc) from exc

        try:
            async for chunk in stream:
                if cancellation_token and cancellation_token.is_set():
                    raise asyncio.CancelledError("Stream cancelled by client.")

                if not chunk.choices:
                    continue

                choice = chunk.choices[0]
                delta = choice.delta

                delta_tool: ToolCallRequest | None = None
                if delta.tool_calls:
                    raw_tc = delta.tool_calls[0]
                    delta_tool = ToolCallRequest(
                        call_id=raw_tc.id or "",
                        tool_name=raw_tc.function.name if raw_tc.function else "",
                        arguments_json=raw_tc.function.arguments
                        if raw_tc.function
                        else "",
                    )

                yield ModelStreamChunk(
                    delta_content=delta.content,
                    delta_tool_call=delta_tool,
                    finish_reason=choice.finish_reason,
                    usage=(
                        ModelUsage(
                            prompt_tokens=chunk.usage.prompt_tokens,
                            completion_tokens=chunk.usage.completion_tokens,
                            total_tokens=chunk.usage.total_tokens,
                        )
                        if chunk.usage
                        else None
                    ),
                )
        except Exception as exc:
            if isinstance(exc, asyncio.CancelledError):
                raise
            raise self._translate_exception(exc) from exc
