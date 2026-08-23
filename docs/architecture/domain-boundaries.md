# Domain Boundaries

This document defines the core domain concepts and their boundaries in Mwalimu.

## Library

A **Library** is a logical knowledge and security boundary, not a deployment boundary.

- Resources, connections, users, permissions, and agent sessions are scoped to a library.
- Multiple libraries share the same infrastructure: PostgreSQL, pgvector, object storage, Redis, and Celery workers.
- There is **no vector database per library**.
- There is **no embedding service per library**.

## User & Permissions

Users belong to the platform and are authorized within libraries. Authorization is enforced in code, not delegated to an LLM. A tool or resource being discoverable does not grant permission to use it.

## Connector

A `Connector` is a reusable definition of how to reach an external system.

- It describes protocol, authentication type, and required configuration schema.
- It does not contain credentials.
- It is shared or reusable across libraries.

## Connection

A `Connection` is an instantiated, authenticated link scoped to a library.

- It holds credentials or tokens required to reach an external system.
- It belongs to exactly one library.
- It references a connector.

## Resource

A `Resource` is a piece of knowledge owned by a library.

- It may be uploaded directly, imported from a connection, or generated.
- Original files are stored in object storage.
- Extracted text, chunks, embeddings, and metadata are stored in PostgreSQL + pgvector.

## Connector != Connection != Library

These concepts are intentionally separate:

- **Connector** = how to reach a system.
- **Connection** = authenticated access to that system for a library.
- **Library** = workspace that owns resources and authorizations.

## Agent & Session

An **Agent** is a configured runtime that can process tasks. A **Session** represents a single interaction lifecycle.

- Agent behavior is driven by the OpenAI Agents SDK running in the Agent Service.
- The Agent Service does not store domain state directly; it fetches context from the Platform API.

## Tools

- **Native Mwalimu tools** are implemented inside the Agent Service.
- **External MCP tools** are provided by third-party MCP servers and invoked through the MCP client layer.
- Tool discovery does not imply authorization. The Agent Service and Platform API enforce authorization independently.

## Ingestion Pipeline

Ingestion is asynchronous work performed by Celery workers on behalf of the Platform API:

1. Accept or fetch original resource.
2. Store original file in object storage.
3. Extract text and metadata.
4. Chunk and generate embeddings.
5. Store chunks and vectors in PostgreSQL via pgvector.

## Authorization Axioms

- **Discovery is not authorization.** A user or agent may know a tool exists without being allowed to call it.
- **LLM behavior is not authorization.** The model cannot decide to bypass access controls.
- Authorization failures **fail closed**: if a check cannot complete, access is denied.
