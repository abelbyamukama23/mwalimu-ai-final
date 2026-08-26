"""ToolRegistry — Centralized 5-stage capability execution pipeline.

Stages:
1. Tool Resolution & Existence Check
2. Allowlist Policy Enforcement
3. JSON Schema & Argument Validation
4. Scoped Credential Injection (for credential-aware tools)
5. Timed & Cancelable Execution
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import jsonschema  # type: ignore[import-untyped]

from agent_service.domain.context import ExecutionContext
from agent_service.domain.message import ToolCallRequest, ToolResult
from agent_service.domain.protocols import ToolProtocol

logger = logging.getLogger(__name__)

# Default per-tool execution timeout (seconds)
DEFAULT_TOOL_TIMEOUT = 15.0


class ToolRegistry:
    """Registry managing tool resolution and the 5-stage execution pipeline.

    The registry does NOT contain business logic for individual tools.
    Individual tools remain independent ToolProtocol implementations.
    """

    def __init__(
        self,
        tools: list[ToolProtocol] | None = None,
        default_timeout: float = DEFAULT_TOOL_TIMEOUT,
    ) -> None:
        self._tools: dict[str, ToolProtocol] = {}
        self._default_timeout = default_timeout
        if tools:
            for tool in tools:
                self.register(tool)

    def register(self, tool: ToolProtocol) -> None:
        """Register a capability by its definition name."""
        name = tool.definition.name
        if name in self._tools:
            raise ValueError(f"Tool '{name}' is already registered.")
        self._tools[name] = tool
        logger.debug("Tool registered: %s", name)

    def get(self, name: str) -> ToolProtocol | None:
        """Resolve a tool by name, or return None."""
        return self._tools.get(name)

    def list_definitions(
        self,
        context: ExecutionContext | None = None,
    ) -> list[Any]:
        """Return ToolDefinition objects for all registered tools.

        If context has an allowlist, only return allowed tool defs.
        """
        from agent_service.domain.protocols import ToolDefinition

        defs: list[ToolDefinition] = []
        for name, tool in self._tools.items():
            if context is not None and not context.is_tool_allowed(name):
                continue
            defs.append(tool.definition)
        return defs

    async def execute(
        self,
        request: ToolCallRequest,
        context: ExecutionContext,
        cancellation_token: asyncio.Event | None = None,
    ) -> ToolResult:
        """Execute the 5-stage capability pipeline."""

        # Stage 1: Tool Resolution
        tool = self._tools.get(request.tool_name)
        if tool is None:
            logger.warning("Unknown tool requested: %s", request.tool_name)
            return ToolResult(
                call_id=request.call_id,
                tool_name=request.tool_name,
                success=False,
                output="",
                error=f"Unknown tool: '{request.tool_name}'",
            )

        # Stage 2: Allowlist Policy Enforcement
        if not context.is_tool_allowed(request.tool_name):
            logger.warning(
                "Tool '%s' blocked by allowlist for run %s",
                request.tool_name,
                context.agent_run_id,
            )
            return ToolResult(
                call_id=request.call_id,
                tool_name=request.tool_name,
                success=False,
                output="",
                error=(
                    f"Tool '{request.tool_name}' is not permitted for this execution."
                ),
            )

        # Stage 3: JSON Schema & Argument Validation
        try:
            arguments = json.loads(request.arguments_json)
        except (json.JSONDecodeError, TypeError) as exc:
            return ToolResult(
                call_id=request.call_id,
                tool_name=request.tool_name,
                success=False,
                output="",
                error=f"Invalid JSON arguments: {exc}",
            )

        schema = tool.definition.parameters_schema
        try:
            jsonschema.validate(instance=arguments, schema=schema)
        except jsonschema.ValidationError as exc:
            return ToolResult(
                call_id=request.call_id,
                tool_name=request.tool_name,
                success=False,
                output="",
                error=(f"Schema validation error: {exc.message}"),
            )

        # Stage 4: Credential injection is handled by
        # individual credential-aware tools internally.
        # The registry does not inject credentials directly;
        # it passes the context through to the tool.

        # Stage 5: Timed & Cancelable Execution
        try:
            result = await asyncio.wait_for(
                tool.execute(
                    arguments=arguments,
                    context=context,
                    cancellation_token=cancellation_token,
                ),
                timeout=self._default_timeout,
            )
        except TimeoutError:
            logger.warning(
                "Tool '%s' timed out after %.1fs for run %s",
                request.tool_name,
                self._default_timeout,
                context.agent_run_id,
            )
            return ToolResult(
                call_id=request.call_id,
                tool_name=request.tool_name,
                success=False,
                output="",
                error=(
                    f"Tool '{request.tool_name}' timed out "
                    f"after {self._default_timeout}s."
                ),
            )
        except asyncio.CancelledError:
            logger.info("Tool '%s' execution cancelled.", request.tool_name)
            raise
        except Exception as exc:
            # Catch-all: sanitize unexpected errors
            logger.error(
                "Tool '%s' raised unexpected error: %s",
                request.tool_name,
                exc,
                exc_info=True,
            )
            return ToolResult(
                call_id=request.call_id,
                tool_name=request.tool_name,
                success=False,
                output="",
                error=(f"Internal tool error in '{request.tool_name}'."),
            )

        # Ensure call_id is correctly set on result
        if result.call_id != request.call_id:
            result = ToolResult(
                call_id=request.call_id,
                tool_name=result.tool_name,
                success=result.success,
                output=result.output,
                error=result.error,
                citation_evidence=result.citation_evidence,
            )

        return result
