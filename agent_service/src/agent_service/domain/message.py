"""Domain representations of messages, tool requests, results, and citations."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum


class MessageRole(str, Enum):
    """Normalized role classification for model messages."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass(frozen=True)
class EvidenceCitation:
    """14-field citation evidence from Knowledge Gateway retrieval."""

    resource_id: uuid.UUID
    resource_name: str
    library_id: uuid.UUID
    library_name: str
    page_start: int | None = None
    page_end: int | None = None
    section: str | None = None
    sequence: int = 0
    char_start: int = 0
    char_end: int = 0
    content_sha256: str = ""
    chunk_id: uuid.UUID | None = None
    score: float | None = None


@dataclass(frozen=True)
class ToolCallRequest:
    """Structured capability invocation request emitted by the model."""

    call_id: str
    tool_name: str
    arguments_json: str


@dataclass(frozen=True)
class ToolResult:
    """Outcome of a capability execution."""

    call_id: str
    tool_name: str
    success: bool
    output: str
    error: str | None = None
    citation_evidence: list[EvidenceCitation] | None = None


@dataclass(frozen=True)
class ModelMessage:
    """Normalized message representation in the agent context."""

    role: MessageRole
    content: str | None = None
    tool_calls: list[ToolCallRequest] | None = None
    tool_call_id: str | None = None


@dataclass(frozen=True)
class ModelUsage:
    """Token consumption metrics for a model invocation."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass(frozen=True)
class ModelResponse:
    """Standardized completion response from a model provider."""

    message: ModelMessage
    finish_reason: str = "stop"  # "stop", "tool_calls", "length", "content_filter"
    usage: ModelUsage = field(default_factory=ModelUsage)


@dataclass(frozen=True)
class ModelStreamChunk:
    """Incremental streaming token or tool call delta."""

    delta_content: str | None = None
    delta_tool_call: ToolCallRequest | None = None
    finish_reason: str | None = None
    usage: ModelUsage | None = None
