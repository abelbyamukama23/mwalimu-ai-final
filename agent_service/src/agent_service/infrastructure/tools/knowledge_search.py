"""Knowledge Gateway Search Tool connecting to Slice 5 Knowledge Retrieval Gateway."""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

import httpx

from agent_service.config import Settings, settings
from agent_service.domain.context import ExecutionContext
from agent_service.domain.message import EvidenceCitation, ToolResult
from agent_service.domain.protocols import ToolDefinition, ToolProtocol
from agent_service.infrastructure.credential_vault import DelegatedCredentialVault

logger = logging.getLogger(__name__)


class KnowledgeSearchTool(ToolProtocol):
    """Capability that queries Slice 5 Knowledge Gateway using delegated credentials."""

    def __init__(
        self,
        credential_vault: DelegatedCredentialVault,
        base_url: str | None = None,
        timeout_seconds: float | None = None,
        custom_settings: Settings | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        cfg = custom_settings or settings
        self._vault = credential_vault
        self._base_url = (base_url or cfg.PLATFORM_API_BASE_URL).rstrip("/")
        self._timeout_seconds = timeout_seconds or cfg.KNOWLEDGE_GATEWAY_TIMEOUT_SECONDS
        self._http_client = http_client

        self._definition = ToolDefinition(
            name="knowledge_search",
            description=(
                "Search indexed educational knowledge and course materials across "
                "authorized libraries with citation provenance."
            ),
            parameters_schema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query or concept to look up.",
                    },
                    "library_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional library UUIDs to narrow scope.",
                    },
                    "resource_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional resource UUIDs to narrow scope.",
                    },
                    "top_k": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 50,
                        "description": "Max chunks to return (1-50, default 10).",
                    },
                    "similarity_threshold": {
                        "type": "number",
                        "minimum": 0.0,
                        "maximum": 1.0,
                        "description": "Min similarity threshold (0.0 to 1.0).",
                    },
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        )

    @property
    def definition(self) -> ToolDefinition:
        return self._definition

    async def execute(
        self,
        arguments: dict[str, Any],
        context: ExecutionContext,
        cancellation_token: asyncio.Event | None = None,
    ) -> ToolResult:
        if cancellation_token and cancellation_token.is_set():
            raise asyncio.CancelledError("Knowledge search cancelled.")

        # Stage 4: Retrieve delegated execution credential
        token = self._vault.retrieve(context.agent_run_id)
        if not token:
            logger.warning(
                "No delegated credential found in vault for run_id=%s",
                context.agent_run_id,
            )
            return ToolResult(
                call_id="",
                tool_name=self.definition.name,
                success=False,
                output="",
                error="Authentication credential missing for knowledge search.",
            )

        query = arguments.get("query", "")
        payload: dict[str, Any] = {
            "query": query,
            "include_text": True,
        }
        if "library_ids" in arguments:
            payload["library_ids"] = arguments["library_ids"]
        if "resource_ids" in arguments:
            payload["resource_ids"] = arguments["resource_ids"]
        if "top_k" in arguments:
            payload["top_k"] = arguments["top_k"]
        if "similarity_threshold" in arguments:
            payload["similarity_threshold"] = arguments["similarity_threshold"]

        endpoint = f"{self._base_url}/api/v1/knowledge/search/"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        try:
            if self._http_client is not None:
                resp = await self._http_client.post(
                    endpoint,
                    json=payload,
                    headers=headers,
                    timeout=self._timeout_seconds,
                )
            else:
                async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                    resp = await client.post(endpoint, json=payload, headers=headers)
        except httpx.TimeoutException:
            logger.warning(
                "Knowledge gateway request timed out for run_id=%s",
                context.agent_run_id,
            )
            return ToolResult(
                call_id="",
                tool_name=self.definition.name,
                success=False,
                output="",
                error="Knowledge search timed out.",
            )
        except httpx.RequestError as exc:
            logger.error("Knowledge gateway request error: %s", exc)
            return ToolResult(
                call_id="",
                tool_name=self.definition.name,
                success=False,
                output="",
                error="Failed to connect to Knowledge Gateway.",
            )

        if resp.status_code == 401 or resp.status_code == 403:
            return ToolResult(
                call_id="",
                tool_name=self.definition.name,
                success=False,
                output="",
                error="Knowledge retrieval unauthorized or token expired.",
            )
        elif resp.status_code == 429:
            return ToolResult(
                call_id="",
                tool_name=self.definition.name,
                success=False,
                output="",
                error="Knowledge search rate limit exceeded.",
            )
        elif resp.status_code >= 500:
            return ToolResult(
                call_id="",
                tool_name=self.definition.name,
                success=False,
                output="",
                error="Knowledge retrieval service temporarily unavailable.",
            )
        elif resp.status_code != 200:
            return ToolResult(
                call_id="",
                tool_name=self.definition.name,
                success=False,
                output="",
                error=f"Knowledge retrieval failed with status {resp.status_code}.",
            )

        data = resp.json()
        results_data = data.get("results", [])
        if not results_data:
            return ToolResult(
                call_id="",
                tool_name=self.definition.name,
                success=True,
                output="No relevant knowledge chunks found for the query.",
                citation_evidence=[],
            )

        citations: list[EvidenceCitation] = []
        formatted_chunks: list[str] = []

        for idx, item in enumerate(results_data, start=1):
            prov = item.get("provenance", {})
            try:
                chunk_uuid = (
                    uuid.UUID(item["chunk_id"]) if item.get("chunk_id") else None
                )
                res_uuid = uuid.UUID(prov["resource_id"])
                lib_uuid = uuid.UUID(prov["library_id"])
            except (KeyError, ValueError) as exc:
                logger.warning("Invalid UUID in retrieval result: %s", exc)
                continue

            res_name = (
                prov.get("resource_name")
                or prov.get("title")
                or item.get("title")
                or "Unknown Resource"
            )
            lib_name = (
                prov.get("library_name")
                or prov.get("library_title")
                or item.get("library_name")
                or "Unknown Library"
            )
            citation = EvidenceCitation(
                resource_id=res_uuid,
                resource_name=res_name,
                library_id=lib_uuid,
                library_name=lib_name,
                page_start=prov.get("page_start"),
                page_end=prov.get("page_end"),
                section=prov.get("section"),
                sequence=prov.get("sequence", 0),
                char_start=prov.get("char_start", 0),
                char_end=prov.get("char_end", 0),
                content_sha256=prov.get("content_sha256", ""),
                chunk_id=chunk_uuid,
                score=item.get("score"),
            )
            citations.append(citation)

            # Build readable text snippet for LLM
            loc = ""
            if citation.page_start is not None:
                loc = f", p. {citation.page_start}"
                if citation.page_end and citation.page_end != citation.page_start:
                    loc += f"-{citation.page_end}"
            elif citation.section:
                loc = f", {citation.section}"

            chunk_text = item.get("text", "").strip()
            src_info = f"{citation.resource_name}{loc}"
            header = f"[{idx}] (Source: {src_info} | Library: {citation.library_name}):"
            formatted_chunks.append(f"{header}\n{chunk_text}")

        output_text = "\n\n".join(formatted_chunks)
        return ToolResult(
            call_id="",
            tool_name=self.definition.name,
            success=True,
            output=output_text,
            citation_evidence=citations,
        )
