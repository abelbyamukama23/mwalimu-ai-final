"""Model Context Protocol (MCP) Streamable HTTP JSON-RPC 2.0 client."""

from __future__ import annotations

import logging
import uuid
from typing import Any

import httpx

logger = logging.getLogger(__name__)

MCP_PROTOCOL_VERSION = "2024-11-05"


class McpError(Exception):
    """Raised when an MCP protocol, connection, or execution error occurs."""


class McpClientManager:
    """Manages low-level JSON-RPC communication with an external MCP Server over Streamable HTTP."""

    def __init__(
        self,
        server_url: str,
        headers: dict[str, str] | None = None,
        timeout: float = 15.0,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.server_url = server_url.rstrip("/")
        self.headers = headers or {}
        self.timeout = timeout
        self._custom_client = http_client
        self._is_initialized = False

    def _get_client(self) -> httpx.AsyncClient:
        """Return an async HTTP client configured for MCP JSON-RPC."""
        if self._custom_client is not None:
            return self._custom_client
        req_headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "User-Agent": "Mwalimu-AgentService-MCP/1.0",
            **self.headers,
        }
        return httpx.AsyncClient(headers=req_headers, timeout=self.timeout)

    async def _send_rpc(self, method: str, params: dict[str, Any] | None = None) -> Any:
        """Send a JSON-RPC 2.0 request and return the 'result' object."""
        request_id = str(uuid.uuid4())
        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params or {},
        }

        client = self._get_client()
        try:
            # If using self._custom_client, do not manage with context manager if external
            if self._custom_client is not None:
                resp = await client.post(self.server_url, json=payload)
            else:
                async with client:
                    resp = await client.post(self.server_url, json=payload)

            if resp.status_code != 200:
                raise McpError(
                    f"MCP server returned HTTP {resp.status_code}: {resp.text}"
                )

            data = resp.json()
            if "error" in data:
                err = data["error"]
                msg = err.get("message", "Unknown MCP error")
                code = err.get("code", -32603)
                raise McpError(f"MCP RPC Error [{code}]: {msg}")

            return data.get("result", {})
        except httpx.RequestError as exc:
            raise McpError(f"Network error communicating with MCP server '{self.server_url}': {exc}") from exc

    async def initialize(self) -> dict[str, Any]:
        """Perform MCP protocol handshake (initialize + notifications/initialized)."""
        params = {
            "protocolVersion": MCP_PROTOCOL_VERSION,
            "capabilities": {
                "roots": {"listChanged": False},
                "sampling": {},
            },
            "clientInfo": {
                "name": "mwalimu-agent-service",
                "version": "0.1.0",
            },
        }
        result = await self._send_rpc("initialize", params)
        self._is_initialized = True
        logger.info("Initialized MCP connection to %s: server=%s", self.server_url, result.get("serverInfo"))
        return result

    async def list_tools(self) -> list[dict[str, Any]]:
        """Query 'tools/list' and return list of tool specification dictionaries."""
        if not self._is_initialized:
            await self.initialize()

        result = await self._send_rpc("tools/list", {})
        return result.get("tools", [])

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> str:
        """Invoke 'tools/call' on the remote MCP server and return text output."""
        if not self._is_initialized:
            await self.initialize()

        params = {
            "name": name,
            "arguments": arguments,
        }
        result = await self._send_rpc("tools/call", params)

        # Extract content chunks
        content_items = result.get("content", [])
        text_outputs: list[str] = []

        for item in content_items:
            if item.get("type") == "text":
                text_outputs.append(item.get("text", ""))
            elif item.get("type") == "image":
                text_outputs.append("[Image Content Received]")
            elif item.get("type") == "resource":
                res = item.get("resource", {})
                text_outputs.append(f"Resource ({res.get('uri')}): {res.get('text', '')}")

        output_str = "\n".join(text_outputs) if text_outputs else str(result)

        if result.get("isError"):
            raise McpError(f"MCP tool execution failed: {output_str}")

        return output_str
