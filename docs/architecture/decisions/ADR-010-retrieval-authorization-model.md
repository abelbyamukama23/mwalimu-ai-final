# ADR-010: Server-Authoritative Retrieval Authorization & Delegation Model

## Status

Accepted

## Context

The Knowledge Gateway serves vector retrieval requests for users directly (via frontend) and on behalf of users (via Agent Service and MCP tools). We must define:
1. The exact delegation and execution identity model for Agent Service → Knowledge Gateway calls without introducing full IAM/OAuth bloat.
2. The clear separation among three distinct platform capabilities: Library Discovery, Knowledge Retrieval, and Resource Download.
3. The immutable `EffectiveRetrievalScope` domain contract and scope-narrowing invariant.

## Decision

We establish a **server-authoritative, fail-closed authorization and delegation model** executed by a dedicated domain component (`KnowledgeAuthorizationPolicy`).

### 1. Delegated Execution Credential Specification

When the Agent Service acts on behalf of a user, it uses a short-lived **Delegated Execution Token** (HMAC-SHA256 JWT). This token is strictly a **delegation/execution credential**, NOT a replacement for primary user authentication.

| Property | Value / Specification | Description |
|----------|-----------------------|-------------|
| **Issuer (`iss`)** | `mwalimu-platform-api` | Minted by Platform API when dispatching an `AgentRun` or session. |
| **Audience (`aud`)** | `mwalimu-knowledge-gateway` | Restricted specifically to Knowledge Gateway retrieval endpoints. |
| **Signing Key** | Platform API `DELEGATION_SIGNING_KEY` (falls back to `SECRET_KEY`) | Kept confidential in Platform API environment. |
| **Verification** | `DelegatedExecutionAuthentication` | Custom DRF authentication backend in the Knowledge Gateway. |
| **Execution Identity (`sub`)** | `user_id` (UUID) | The authoritative subject on whose behalf retrieval executes. |
| **Audit Identity (`context`)** | `agent_run_id`, `session_id` | Provenance metadata correlating agent execution and user session. |
| **Issued At (`iat`)** | Unix timestamp | Timestamp when credential was minted. |
| **Expiry (`exp`)** | $\text{iat} + 900\text{s}$ (15 minutes) | Short-lived, matching agent turn lifetime. |
| **Nonce (`jti`)** | UUID4 string | Unique token identifier for tracing and optional replay protection. |
| **Replay Protection** | Timestamp window + JTI tracking | Bounded 15-min lifetime; active `AgentRun` state verified. |
| **Revocation / Cancellation** | `AgentRun.status` validation | If the associated `AgentRun` is marked `CANCELLED` or `FAILED` in Platform API, subsequent delegation calls fail closed. |
| **Key Rotation** | `kid` header support | Key ID header in JWT header allows graceful zero-downtime rotation. |

**Zero Trust in Agent Claims**: The token contains NO permission claims, NO institution IDs, and NO library IDs. The Gateway takes only the verified `user_id` and independently resolves permissions from authoritative database tables.

### 2. Capability Separation: Discovery vs. Retrieval vs. Download

The platform strictly differentiates three distinct capabilities:

```
┌───────────────────────────────────────────────────────────────────────────┐
│                      Capability Authorization Matrix                      │
├───────────────────────┬───────────────────────┬───────────────────────────┤
│ Capability            │ Scope / Target        │ Required Authorization    │
├───────────────────────┼───────────────────────┼───────────────────────────┤
│ 1. Library Discovery  │ Metadata (name, slug, │ • Institution Admin, OR   │
│    (Slice 2)          │ description, catalog) │ • Library is DISCOVERABLE │
│                       │                       │   and user is active      │
│                       │                       │   institution member, OR  │
│                       │                       │ • Explicit Access Policy  │
├───────────────────────┼───────────────────────┼───────────────────────────┤
│ 2. Knowledge          │ Document Chunks,      │ • Institution Admin, OR   │
│    Retrieval          │ Embeddings, Vector    │ • Explicit Access Policy  │
│    (Slice 5)          │ Similarity Search     │   (ADMIN, TEACHER,        │
│                       │                       │   STUDENT role)           │
├───────────────────────┼───────────────────────┼───────────────────────────┤
│ 3. Resource Download  │ Raw Binary Files from │ • Existing Slice 3 rules  │
│    (Slice 3)          │ Object Storage        │   via can_access_library  │
│                       │                       │   (unchanged)             │
└───────────────────────┴───────────────────────┴───────────────────────────┘
```

- **Discovery $\neq$ Knowledge Retrieval**: `LibraryVisibility.DISCOVERABLE` allows catalog browsing only. Knowledge chunk retrieval strictly requires an explicit `LibraryAccessPolicy` or Institution Admin status.
- **Resource Download Unchanged**: Downloading original binary files remains strictly governed by Slice 3's `ResourceViewSet.download` and `can_access_library`. Knowledge retrieval does not become a universal bypass or replacement for Resource download.

### 3. Immutable `EffectiveRetrievalScope` Value Object

The authorization policy outputs an immutable value object using `frozenset`:

```python
@dataclass(frozen=True)
class EffectiveRetrievalScope:
    authorized_library_ids: frozenset[uuid.UUID]
    authorized_resource_ids: frozenset[uuid.UUID] | None

    @property
    def is_empty(self) -> bool:
        return len(self.authorized_library_ids) == 0 or (
            self.authorized_resource_ids is not None
            and len(self.authorized_resource_ids) == 0
        )
```

#### The Scope-Narrowing Invariant:
$$\text{effective\_scope} = \text{requested\_scope} \cap \text{server\_authorized\_scope}$$

- Downstream components (`SearchKnowledgeUseCase`, `PgVectorRetriever`) receive **ONLY** the immutable `EffectiveRetrievalScope`.
- They never receive the raw caller-requested IDs.
- A caller may narrow scope, but has **no structural mechanism to widen scope**.
- If `is_empty` is `True`, the Gateway short-circuits immediately, returning `200 OK` with `results: []` without invoking pgvector.

## Consequences

### Positive

- Clean, unbypassable zero-trust delegation for agent runs.
- Absolute clarity between metadata discovery, chunk retrieval, and raw file downloads.
- Immutable scope objects eliminate any accidental scope widening bugs in downstream code.

### Negative

- Requires minting and verifying delegation tokens on Agent Service turn lifecycles.

## Related Decisions

- ADR-001: Service Boundaries.
- ADR-006: pgvector Schema and Indexing.
- ADR-009: Knowledge Gateway Placement and Boundary.
- ADR-011: Retrieval API Contract and Provenance Specification.
