# ADR-015: Model Provider Boundary & Gateway Abstraction

## Status

Accepted (Design Phase — Slice 6 Revision)

## Context

The Mwalimu agent runtime must support multiple large language model providers (OpenAI, Google Gemini, DeepSeek, Anthropic, open-source local LLMs) without hardcoding provider SDKs or vendor-specific message formats into the core agent reasoning loop.

However, we must avoid creating a bloated, generic "AI Framework" (like LangChain or LlamaIndex). The abstraction should strictly represent model inference capabilities required by the Mwalimu Agent Runtime: chat completions, structured tool calling, token usage reporting, and streaming.

## Decision

We establish a focused, provider-neutral **`ModelProviderProtocol`** with normalized message structures, unified tool schema translation, and standardized error classification.

### 1. Unified Message & Tool Call Representation

```python
class MessageRole(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"

@dataclass(frozen=True)
class ToolCallRequest:
    call_id: str
    tool_name: str
    arguments_json: str

@dataclass(frozen=True)
class ModelMessage:
    role: MessageRole
    content: str | None = None
    tool_calls: list[ToolCallRequest] | None = None
    tool_call_id: str | None = None  # Populated when role == TOOL

@dataclass(frozen=True)
class ModelUsage:
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int

@dataclass(frozen=True)
class ModelResponse:
    message: ModelMessage
    finish_reason: str  # "stop", "tool_calls", "length", "content_filter"
    usage: ModelUsage
```

### 2. Minimal Model Provider Protocol

```python
class ModelProviderProtocol(Protocol):
    """Minimal, focused protocol for model inference in the Agent Runtime."""
    
    provider_name: str
    default_model: str

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

    async def stream_generate(
        self,
        messages: list[ModelMessage],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        cancellation_token: asyncio.Event | None = None,
    ) -> AsyncIterator[ModelStreamChunk]:
        """Stream token chunks and partial tool calls."""
        ...
```

### 3. Error Normalization

All vendor SDK exceptions are translated at the adapter boundary into standard domain errors:
- `ModelError` (Base)
  - `ModelRateLimitError` (HTTP 429, triggers exponential backoff retry)
  - `ModelTimeoutError` (Provider latency exceeded)
  - `ModelContextWindowExceededError` (Context window token overflow)
  - `ModelAuthenticationError` (Bad API key / credentials)
  - `ModelServiceUnavailableError` (Provider 500/503 outage)

### 4. Non-Goals (Rejected Bloat)

- No generic chains, agents, memory abstractions, or embeddings in this protocol.
- Embeddings remain in Platform API (Slice 4 `EmbeddingProvider`); `ModelProviderProtocol` handles chat/tool inference only.

## Consequences

### Positive

- Clean, minimal 2-method protocol focused exclusively on model inference.
- Zero vendor lock-in; easily testable with in-memory fake providers.
- Strict isolation of third-party SDK dependencies inside `infrastructure/model_gateway/`.

### Negative

- Provider-specific argument structures must be translated by adapters.

## Related Decisions

- [ADR-001: Service Boundaries](ADR-001-service-boundaries.md)
- [ADR-012: Agent Runtime Boundary](ADR-012-agent-runtime-boundary.md)
- [ADR-016: Capability / Tool Architecture](ADR-016-capability-tool-architecture.md)
