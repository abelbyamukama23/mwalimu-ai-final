# ADR-016: Capability & Tool Architecture

## Status

Accepted (Design Phase — Slice 6 Revision)

## Context

Agents achieve goals by invoking capabilities: native computational utilities, the Knowledge Gateway (Slice 5), and external tools (via Model Context Protocol - MCP).

However, the LLM must **never directly invoke arbitrary HTTP endpoints or execute unvetted code**. The model merely expresses an *intent* to invoke a capability by producing a structured tool call request.

We must define a controlled, policy-enforced capability execution architecture where the `ToolRegistry` strictly validates the capability name, input schema, tool allowlist, execution policies, timeouts, and scoped credential injection before invoking any capability.

## Decision

We establish a unified **Capability / Tool Interface** (`ToolProtocol`) and a centralized **`ToolRegistry`** that gates and governs all capability execution.

### 1. Unified Tool Protocol

```python
@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    parameters_schema: dict[str, Any]  # Strict JSON Schema

@dataclass(frozen=True)
class ToolResult:
    call_id: str
    tool_name: str
    success: bool
    output: str
    error: str | None = None
    citation_evidence: list[dict[str, Any]] | None = None  # Provenance metadata

class ToolProtocol(Protocol):
    """Protocol for all executable agent capabilities."""
    definition: ToolDefinition

    async def execute(
        self,
        arguments: dict[str, Any],
        context: ExecutionContext,
        cancellation_token: asyncio.Event | None = None,
    ) -> ToolResult:
        ...
```

### 2. The 5-Stage Capability Execution Pipeline

When the model emits a `ToolCallRequest(call_id, tool_name, arguments_json)`, execution proceeds through a strict 5-stage pipeline managed by `ToolRegistry`:

```
Model ToolCallRequest
        │
        ▼
[Stage 1: Tool Resolution & Existence Check]
  • Verify tool_name is registered in ToolRegistry.
  • If not found, return ToolResult(success=False, error="Unknown tool").
        │
        ▼
[Stage 2: Allowlist Policy Enforcement]
  • If context.tool_allowlist is present, verify tool_name ∈ tool_allowlist.
  • If unauthorized, reject with ToolResult(success=False, error="Tool not permitted").
        │
        ▼
[Stage 3: JSON Schema & Argument Validation]
  • Parse arguments_json and validate against tool.definition.parameters_schema.
  • Reject malformed arguments with structured schema error message for model self-correction.
        │
        ▼
[Stage 4: Scoped Credential Injection & Isolation]
  • If the capability requires platform authentication (e.g. KnowledgeGatewayClient),
    inject the delegated token from DelegatedCredentialVault.
  • Native tools (calculator) and MCP tools receive zero platform credentials.
        │
        ▼
[Stage 5: Timed & Cancelable Execution]
  • Execute capability with isolated timeout: asyncio.wait_for(tool.execute(), timeout=15.0).
  • Respect cancellation_token at async boundaries.
  • Sanitize output and wrap in immutable ToolResult.
```

### 3. Capability Classification

1. **Native Tools**: Pure in-process functions (e.g., `calculator`) with no network access.
2. **Knowledge Retrieval Capability**: Strongly-typed HTTP adapter targeting Slice 5 `POST /api/v1/knowledge/search/`.
3. **MCP Tool Adapters**: Strongly-typed client adapters targeting external MCP servers over Streamable HTTP.

## Consequences

### Positive

- Zero arbitrary network execution: model can only invoke strictly defined and registered capabilities.
- Uniform 5-stage gating guarantees allowlist compliance, argument validation, and credential isolation.
- Isolated timeouts prevent hung tools from exhausting worker threads.

### Negative

- Every new capability requires formal registration in the `ToolRegistry`.

## Related Decisions

- [ADR-009: Knowledge Gateway Placement](ADR-009-knowledge-gateway-placement.md)
- [ADR-011: Retrieval Contract & Provenance](ADR-011-retrieval-contract-provenance.md)
- [ADR-014: Execution Context & Identity](ADR-014-execution-context-and-identity.md)
- [ADR-017: MCP Integration Boundary](ADR-017-mcp-integration-boundary.md)
