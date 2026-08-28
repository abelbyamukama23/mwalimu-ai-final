"""Unit tests for live Google Drive CRUD capabilities."""

from __future__ import annotations

import uuid
import httpx
import pytest

from agent_service.domain.context import ExecutionContext
from agent_service.infrastructure.tools.google_drive_crud import (
    GoogleDriveCreateDocTool,
    GoogleDriveReadTool,
    GoogleDriveSearchTool,
)


def _create_test_context() -> ExecutionContext:
    return ExecutionContext(
        user_id=uuid.uuid4(),
        agent_run_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        timeout_seconds=30.0,
    )


@pytest.mark.asyncio
async def test_google_drive_search_tool() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "files": [
                    {
                        "id": "file_1",
                        "name": "Machine_Learning_Lecture1.gdoc",
                        "mimeType": "application/vnd.google-apps.document",
                    }
                ]
            },
        )

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    tool = GoogleDriveSearchTool(http_client=mock_client)
    ctx = _create_test_context()

    res = await tool.execute(
        {"query": "Machine Learning", "access_token": "mock-token"}, ctx
    )

    assert res.success is True
    assert "Machine_Learning_Lecture1.gdoc" in res.output
    assert "ID: file_1" in res.output


@pytest.mark.asyncio
async def test_google_drive_read_doc_tool() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        if "files/doc_123?fields=" in url_str:
            return httpx.Response(
                200,
                json={"id": "doc_123", "mimeType": "application/vnd.google-apps.document"},
            )
        elif "files/doc_123/export" in url_str:
            return httpx.Response(200, text="# Linear Regression Notes\nw = (X^T X)^-1 X^T y")
        return httpx.Response(404)

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    tool = GoogleDriveReadTool(http_client=mock_client)
    ctx = _create_test_context()

    res = await tool.execute({"file_id": "doc_123", "access_token": "mock-token"}, ctx)

    assert res.success is True
    assert "Linear Regression Notes" in res.output


@pytest.mark.asyncio
async def test_google_drive_create_doc_tool() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"id": "new_doc_999", "name": "AI Study Guide"})

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    tool = GoogleDriveCreateDocTool(http_client=mock_client)
    ctx = _create_test_context()

    res = await tool.execute(
        {"title": "AI Study Guide", "content": "Summary content...", "access_token": "mock-token"},
        ctx,
    )

    assert res.success is True
    assert "Successfully created Google Doc 'AI Study Guide'" in res.output
    assert "new_doc_999" in res.output
