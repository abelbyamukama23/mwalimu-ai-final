# ADR-014: Execution Context & Scoped Credential Propagation

## Status

Accepted (Design Phase — Slice 6 Revision)

## Context

When an agent executes on behalf of a user, it requires runtime identity and execution metadata (user identity, correlation IDs, session tracking, step and time budgets).

However, exposing raw authorization credentials (such as the `DelegatedExecutionToken`) globally across all runtime components (LLM prompts, conversation memory buffers, general step logs, native tools) poses a critical security risk:
1. The LLM could be tricked via prompt injection into repeating or leaking the token.
2. In-process native tools (e.g. calculator, python sandbox) do not need authorization tokens.
3. Only specific authenticated capability adapters (e.g., the `KnowledgeGatewayClient`) legitimately require the delegated token to communicate with the Platform API.

We must define a secure, segregated credential mechanism that isolates delegated credentials from the LLM prompt and working memory while preserving immutable authoritative execution identity.

## Decision

We decouple the core domain `ExecutionContext` from the credential transport layer and establish a dedicated **`ScopedCredentialProvider`** for capability execution.

### 1. Segregated `ExecutionContext` (Domain Value Object)

`ExecutionContext` is an immutable domain value object containing only authoritative identity, correlation tracking, and execution parameters. It contains **NO raw credentials**:

```python
@dataclass(frozen=True)
class ExecutionContext:
    """Immutable domain execution context (No raw credentials)."""
    # 1. Authoritative Identity
    user_id: uuid.UUID
    
    # 2. Correlation Identifiers
    agent_run_id: uuid.UUID
    session_id: uuid.UUID
    
    # 3. Execution Budgets & Limits
    max_steps: int = 10
    timeout_seconds: float = 60.0
    token_budget: int = 4000
    
    # 4. Client / Runtime Preferences
    locale: str = "en"
    tool_allowlist: frozenset[str] | None = None  # None = all registered tools
```

### 2. `DelegatedCredentialVault` (Infrastructure Layer)

The raw `DelegatedExecutionToken` (minted by the Platform API via HMAC-SHA256) is held exclusively in an infrastructure-level `DelegatedCredentialVault` keyed by `agent_run_id`.

```python
class DelegatedCredentialVault:
    """Secure memory vault for delegated execution tokens."""
    
    def store_token(self, agent_run_id: uuid.UUID, token: str) -> None: ...
    def get_token(self, agent_run_id: uuid.UUID) -> str: ...
    def purge_token(self, agent_run_id: uuid.UUID) -> None: ...
```

### 3. Capability-Specific Token Injection

- The **Reasoning Loop** operates purely with `ExecutionContext` and normalized `ModelMessage` objects. It has zero knowledge of the raw token.
- When the `ReasoningLoopEngine` requests capability execution via the `ToolRegistry`, only authorized capability adapters (such as `KnowledgeGatewayClient`) are injected with the token directly from the `DelegatedCredentialVault`.
- Native tools (e.g. `calculator`), MCP tools, and model prompt formatters never receive or access the token.
- Upon run completion (terminal state), the token is immediately purged from the vault.

### 4. Core Security Invariants

1. **Zero Credential Exposure to LLM**: The `DelegatedExecutionToken` is never placed into system prompts, user prompts, assistant messages, or tool result text.
2. **Zero In-Process Privilege Escalation**: Model responses cannot alter the `ExecutionContext` or manipulate the vault.
3. **Short-Lived Delegation**: Delegated tokens expire after 15 minutes and are strictly scoped to the `mwalimu-knowledge-gateway` audience.

## Consequences

### Positive

- Complete protection against prompt injection token exfiltration.
- Principle of Least Privilege: only capability adapters making remote Platform API calls receive delegated credentials.
- Clean separation between domain execution context and transport security tokens.

### Negative

- Requires credential vault lifecycle management (registration on run dispatch, cleanup on run finalization).

## Related Decisions

- [ADR-009: Knowledge Gateway Placement](ADR-009-knowledge-gateway-placement.md)
- [ADR-010: Retrieval Authorization Model](ADR-010-retrieval-authorization-model.md)
- [ADR-012: Agent Runtime Boundary](ADR-012-agent-runtime-boundary.md)
- [ADR-016: Capability / Tool Architecture](ADR-016-capability-tool-architecture.md)
