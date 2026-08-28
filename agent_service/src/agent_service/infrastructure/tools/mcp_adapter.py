"""MCP Tool Adapter — Adapts remote MCP tools into standard ToolProtocol."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from agent_service.domain.context import ExecutionContext
from agent_service.domain.message import ToolResult
from agent_service.domain.protocols import ToolDefinition, ToolProtocol

from .mcp_client import McpClientManager, McpError

logger = logging.getLogger(__name__)


class McpToolAdapter(ToolProtocol):
    """Adapter translating an external MCP tool into the Mwalimu ToolProtocol.

    Conforms to the 5-stage ToolRegistry pipeline and standard execution protocols.
    """

    def __init__(
        self,
        mcp_client: McpClientManager,
        tool_spec: dict[str, Any],
        name_override: str | None = None,
    ) -> None:
        self._mcp_client = mcp_client
        self._raw_name = tool_spec.get("name", "unnamed_mcp_tool")
        self._name = name_override or self._raw_name
        self._description = tool_spec.get("description", f"External MCP tool: {self._name}")
        self._parameters_schema = tool_spec.get(
            "inputSchema", {"type": "object", "properties": {}}
        )

        self._definition = ToolDefinition(
            name=self._name,
            description=self._description,
            parameters_schema=self._parameters_schema,
        )

    @property
    def definition(self) -> ToolDefinition:
        """Return capability metadata and JSON schema."""
        return self._definition

    async def execute(
        self,
        arguments: dict[str, Any],
        context: ExecutionContext,
        cancellation_token: asyncio.Event | None = None,
    ) -> ToolResult:
        """Execute the capability on the remote MCP server."""
        if cancellation_token and cancellation_token.is_set():
            return ToolResult(
                call_id="",
                tool_name=self._name,
                success=False,
                output="",
                error="Execution cancelled by user.",
            )

        try:
            # Remote execution via MCP JSON-RPC
            output = await self._mcp_client.call_tool(
                name=self._raw_name, arguments=arguments
            )
            return ToolResult(
                call_id="",
                tool_name=self._name,
                success=True,
                output=output,
                error=None,
            )
        except McpError as exc:
            logger.warning("MCP tool execution error on '%s': %s", self._name, exc)
            return ToolResult(
                call_id="",
                tool_name=self._name,
                success=False,
                output="",
                error=str(exc),
            )
        except Exception as exc:
            logger.exception("Unexpected error invoking MCP tool '%s': %s", self._name, exc)
            return ToolResult(
                call_id="",
                tool_name=self._name,
                success=False,
                output="",
                error=f"Remote tool invocation failed: {exc}",
            )
