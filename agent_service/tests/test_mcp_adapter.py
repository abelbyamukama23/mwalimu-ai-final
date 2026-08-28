"""Unit tests for Model Context Protocol (MCP) client, adapter, and ToolRegistry mounting."""

from __future__ import annotations

import uuid
import httpx
import pytest

from agent_service.domain.context import ExecutionContext
from agent_service.domain.message import ToolCallRequest
from agent_service.infrastructure.tool_registry import ToolRegistry
from agent_service.infrastructure.tools.mcp_adapter import McpToolAdapter
from agent_service.infrastructure.tools.mcp_client import McpClientManager, McpError


def _create_test_context(
    allowlist: frozenset[str] | None = None,
    timeout_seconds: float = 60.0,
) -> ExecutionContext:
    return ExecutionContext(
        user_id=uuid.uuid4(),
        agent_run_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        timeout_seconds=timeout_seconds,
        tool_allowlist=allowlist,
    )


@pytest.mark.asyncio
async def test_mcp_client_handshake_and_tool_call() -> None:
    """McpClientManager initializes protocol and invokes tools/call over JSON-RPC."""
    async def handler(request: httpx.Request) -> httpx.Response:
        body = request.read().decode("utf-8")
        if '"method": "initialize"' in body or '"method":"initialize"' in body:
            return httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": "1",
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "serverInfo": {"name": "figma-mcp-server", "version": "1.0"},
                        "capabilities": {"tools": {}},
                    },
                },
            )
        elif '"method": "tools/list"' in body or '"method":"tools/list"' in body:
            return httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": "2",
                    "result": {
                        "tools": [
                            {
                                "name": "get_figma_frame",
                                "description": "Fetch design node by frame ID",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {"frame_id": {"type": "string"}},
                                    "required": ["frame_id"],
                                },
                            }
                        ]
                    },
                },
            )
        elif '"method": "tools/call"' in body or '"method":"tools/call"' in body:
            return httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": "3",
                    "result": {
                        "content": [
                            {"type": "text", "text": "Frame 'Login Screen' rendered with 5 buttons."}
                        ]
                    },
                },
            )
        return httpx.Response(404)

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = McpClientManager(
        server_url="https://mcp.example.com",
        http_client=mock_client,
    )

    init_res = await client.initialize()
    assert init_res["serverInfo"]["name"] == "figma-mcp-server"

    tools = await client.list_tools()
    assert len(tools) == 1
    assert tools[0]["name"] == "get_figma_frame"

    output = await client.call_tool("get_figma_frame", {"frame_id": "1:234"})
    assert "Frame 'Login Screen'" in output


@pytest.mark.asyncio
async def test_mcp_tool_adapter_5_stage_registry_pipeline() -> None:
    """McpToolAdapter adapts into ToolProtocol and passes the 5-stage ToolRegistry pipeline."""
    async def handler(request: httpx.Request) -> httpx.Response:
        body = request.read().decode("utf-8")
        if "tools/call" in body:
            return httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": "req-1",
                    "result": {
                        "content": [{"type": "text", "text": "Calculated derivative: 2x + 3"}]
                    },
                },
            )
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": "req-init",
                "result": {"protocolVersion": "2024-11-05", "tools": []},
            },
        )

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = McpClientManager(server_url="https://mcp.math.com", http_client=mock_client)

    tool_spec = {
        "name": "solve_math",
        "description": "Symbolic math solver",
        "inputSchema": {
            "type": "object",
            "properties": {"equation": {"type": "string"}},
            "required": ["equation"],
        },
    }

    adapter = McpToolAdapter(mcp_client=client, tool_spec=tool_spec)
    assert adapter.definition.name == "solve_math"
    assert adapter.definition.description == "Symbolic math solver"

    registry = ToolRegistry([adapter])
    ctx = _create_test_context(allowlist=frozenset(["solve_math"]))

    req = ToolCallRequest(
        call_id="call-123",
        tool_name="solve_math",
        arguments_json='{"equation": "x^2 + 3x"}',
    )

    res = await registry.execute(req, ctx)

    assert res.success is True
    assert res.call_id == "call-123"
    assert "Calculated derivative: 2x + 3" in res.output
