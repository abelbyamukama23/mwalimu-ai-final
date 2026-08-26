# ADR-017: MCP Integration Boundary

## Status

Accepted (Design Phase — Slice 6)

## Context

The Model Context Protocol (MCP) provides an open standard for AI models to discover and consume tools and resources from external servers.

We must define how MCP integrates into Mwalimu without allowing MCP to blur service boundaries or replace the core Agent Runtime.

## Decision

We establish that **MCP is an integration protocol and capability adapter layer**, NOT the Agent Runtime itself.

### 1. Architectural Placement of MCP

```
┌────────────────────────────────────────────────────────┐
│                     Agent Service                      │
│                                                        │
│  ┌──────────────────────────────────────────────────┐  │
│  │               Agent Execution Loop               │  │
│  └────────────────────────┬─────────────────────────┘  │
│                           │ uses                       │
│  ┌────────────────────────▼─────────────────────────┐  │
│  │                    ToolRegistry                  │  │
│  └───────┬──────────────────┬─────────────────┬─────┘  │
│          │                  │                 │        │
│          ▼                  ▼                 ▼        │
│    Native Tools     Knowledge Client     MCP Adapter   │
└───────────────────────────────────────────────┼────────┘
                                                │
                                                │ Streamable HTTP
                                                ▼
                                      ┌───────────────────┐
                                      │ External MCP Server│
                                      └───────────────────┘
```

### 2. Core Integration Rules

1. **Adapter Pattern**: The Agent Service acts as an **MCP Client**. Discovered MCP tools are adapted into the standard `ToolProtocol` and registered in the `ToolRegistry`.
2. **Preferred Transport**: Remote MCP connections use **Streamable HTTP**. Local developer integrations may use `stdio`. Legacy SSE is supported only where required for backward compatibility.
3. **Authorization Boundary**: The MCP Server is untrusted. MCP tools cannot receive raw administrative credentials; they receive only scoped, delegated contexts or explicit user approvals.
4. **Tool Schema Translation**: MCP tool schemas (`tools/list`) are dynamically converted into standard `ToolDefinition` JSON Schemas for model consumption.
5. **No System of Record**: MCP tools never become persistent stores for Mwalimu domain state.

## Consequences

### Positive

- Clean separation between internal reasoning loops and third-party tool protocols.
- Enables dynamic expansion of tool ecosystems without refactoring the agent runtime.
- Standardized security boundary prevents external MCP servers from accessing internal services directly.

### Negative

- Network latency overhead when discovering and executing tools on remote MCP servers.

## Related Decisions

- [ADR-001: Service Boundaries](ADR-001-service-boundaries.md)
- [ADR-012: Agent Runtime Boundary](ADR-012-agent-runtime-boundary.md)
- [ADR-016: Capability / Tool Architecture](ADR-016-capability-tool-architecture.md)
