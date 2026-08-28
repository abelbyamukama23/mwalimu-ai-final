"""Live Google Drive CRUD capabilities for Agent reasoning loops."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from agent_service.domain.context import ExecutionContext
from agent_service.domain.message import ToolResult
from agent_service.domain.protocols import ToolDefinition, ToolProtocol

logger = logging.getLogger(__name__)

GOOGLE_DRIVE_API_BASE = "https://www.googleapis.com/drive/v3"


class GoogleDriveSearchTool(ToolProtocol):
    """Capability allowing agents to search files across connected Google Drive."""

    def __init__(self, http_client: httpx.AsyncClient | None = None) -> None:
        self._custom_client = http_client
        self._definition = ToolDefinition(
            name="google_drive_search",
            description="Search files and folders in the user's Google Drive by keyword.",
            parameters_schema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Keywords or file title to search for.",
                    },
                    "access_token": {
                        "type": "string",
                        "description": "OAuth Bearer access token for Google Drive.",
                    },
                },
                "required": ["query"],
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
        query = arguments.get("query", "")
        token = arguments.get("access_token", "")

        if not token:
            return ToolResult(
                call_id="",
                tool_name=self._definition.name,
                success=False,
                output="",
                error="Missing Google Drive OAuth access token in execution context.",
            )

        client = self._custom_client or httpx.AsyncClient(
            headers={"Authorization": f"Bearer {token}"}, timeout=15.0
        )
        try:
            url = (
                f"{GOOGLE_DRIVE_API_BASE}/files"
                f"?q=name contains '{query}' and trashed = false"
                f"&fields=files(id,name,mimeType,size,modifiedTime)&pageSize=10"
            )
            resp = await client.get(url)
            if resp.status_code != 200:
                return ToolResult(
                    call_id="",
                    tool_name=self._definition.name,
                    success=False,
                    output="",
                    error=f"Google Drive API error: {resp.text}",
                )

            files = resp.json().get("files", [])
            lines = [f"Found {len(files)} matching files:"]
            for f in files:
                lines.append(
                    f"- {f.get('name')} (ID: {f.get('id')}, Type: {f.get('mimeType')})"
                )

            return ToolResult(
                call_id="",
                tool_name=self._definition.name,
                success=True,
                output="\n".join(lines),
                error=None,
            )
        except Exception as exc:
            return ToolResult(
                call_id="",
                tool_name=self._definition.name,
                success=False,
                output="",
                error=str(exc),
            )
        finally:
            if self._custom_client is None:
                await client.aclose()


class GoogleDriveReadTool(ToolProtocol):
    """Capability allowing agents to read document contents from a specific Google Drive file ID."""

    def __init__(self, http_client: httpx.AsyncClient | None = None) -> None:
        self._custom_client = http_client
        self._definition = ToolDefinition(
            name="google_drive_read_file",
            description="Read the text content of a Google Doc or text file from Google Drive by file ID.",
            parameters_schema={
                "type": "object",
                "properties": {
                    "file_id": {
                        "type": "string",
                        "description": "The unique Google Drive file ID.",
                    },
                    "access_token": {
                        "type": "string",
                        "description": "OAuth Bearer access token for Google Drive.",
                    },
                },
                "required": ["file_id"],
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
        file_id = arguments.get("file_id", "")
        token = arguments.get("access_token", "")

        if not token:
            return ToolResult(
                call_id="",
                tool_name=self._definition.name,
                success=False,
                output="",
                error="Missing Google Drive OAuth access token in execution context.",
            )

        client = self._custom_client or httpx.AsyncClient(
            headers={"Authorization": f"Bearer {token}"}, timeout=20.0
        )
        try:
            # First check metadata
            meta_resp = await client.get(f"{GOOGLE_DRIVE_API_BASE}/files/{file_id}?fields=id,name,mimeType")
            if meta_resp.status_code != 200:
                return ToolResult(
                    call_id="",
                    tool_name=self._definition.name,
                    success=False,
                    output="",
                    error=f"File not found: {meta_resp.text}",
                )

            mime = meta_resp.json().get("mimeType", "")
            if mime == "application/vnd.google-apps.document":
                # Export plain text
                dl_resp = await client.get(
                    f"{GOOGLE_DRIVE_API_BASE}/files/{file_id}/export?mimeType=text/plain"
                )
            else:
                dl_resp = await client.get(f"{GOOGLE_DRIVE_API_BASE}/files/{file_id}?alt=media")

            if dl_resp.status_code != 200:
                return ToolResult(
                    call_id="",
                    tool_name=self._definition.name,
                    success=False,
                    output="",
                    error=f"Failed to download file: {dl_resp.text}",
                )

            return ToolResult(
                call_id="",
                tool_name=self._definition.name,
                success=True,
                output=dl_resp.text,
                error=None,
            )
        except Exception as exc:
            return ToolResult(
                call_id="",
                tool_name=self._definition.name,
                success=False,
                output="",
                error=str(exc),
            )
        finally:
            if self._custom_client is None:
                await client.aclose()


class GoogleDriveCreateDocTool(ToolProtocol):
    """Capability allowing agents to create a new Google Doc in the user's Drive."""

    def __init__(self, http_client: httpx.AsyncClient | None = None) -> None:
        self._custom_client = http_client
        self._definition = ToolDefinition(
            name="google_drive_create_doc",
            description="Create a new Google Doc with specified title and content in the user's Drive.",
            parameters_schema={
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Document title.",
                    },
                    "content": {
                        "type": "string",
                        "description": "Text or markdown content of the document.",
                    },
                    "access_token": {
                        "type": "string",
                        "description": "OAuth Bearer access token for Google Drive.",
                    },
                },
                "required": ["title", "content"],
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
        title = arguments.get("title", "Untitled Document")
        content = arguments.get("content", "")
        token = arguments.get("access_token", "")

        if not token:
            return ToolResult(
                call_id="",
                tool_name=self._definition.name,
                success=False,
                output="",
                error="Missing Google Drive OAuth access token in execution context.",
            )

        client = self._custom_client or httpx.AsyncClient(
            headers={"Authorization": f"Bearer {token}"}, timeout=20.0
        )
        try:
            # Create file metadata
            payload = {
                "name": title,
                "mimeType": "application/vnd.google-apps.document",
            }
            resp = await client.post(f"{GOOGLE_DRIVE_API_BASE}/files", json=payload)
            if resp.status_code != 200:
                return ToolResult(
                    call_id="",
                    tool_name=self._definition.name,
                    success=False,
                    output="",
                    error=f"Failed to create Google Doc: {resp.text}",
                )

            data = resp.json()
            doc_id = data.get("id")
            return ToolResult(
                call_id="",
                tool_name=self._definition.name,
                success=True,
                output=f"Successfully created Google Doc '{title}' (ID: {doc_id}).",
                error=None,
            )
        except Exception as exc:
            return ToolResult(
                call_id="",
                tool_name=self._definition.name,
                success=False,
                output="",
                error=str(exc),
            )
        finally:
            if self._custom_client is None:
                await client.aclose()
