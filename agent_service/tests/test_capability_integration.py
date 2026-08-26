"""End-to-end integration tests for the capability pipeline with FakeModelProvider."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from agent_service.domain.context import ExecutionContext
from agent_service.domain.memory import WorkingContextBuffer
from agent_service.domain.message import ToolCallRequest
from agent_service.infrastructure.credential_vault import DelegatedCredentialVault
from agent_service.infrastructure.model_gateway.fake_provider import FakeModelProvider
from agent_service.infrastructure.tool_registry import ToolRegistry
from agent_service.infrastructure.tools.calculator import CalculatorTool
from agent_service.infrastructure.tools.knowledge_search import KnowledgeSearchTool


@pytest.mark.asyncio
async def test_full_capability_and_memory_pipeline_integration() -> None:
    """Verify end-to-end flow: Model -> Tool -> Gateway -> Memory -> Model."""
    # 1. Setup execution context and vault
    user_id = uuid.uuid4()
    run_id = uuid.uuid4()
    session_id = uuid.uuid4()
    context = ExecutionContext(
        user_id=user_id,
        agent_run_id=run_id,
        session_id=session_id,
    )

    vault = DelegatedCredentialVault()
    delegated_token = "mock-delegated-jwt-token"
    vault.store(run_id, delegated_token)

    # 2. Setup mock Slice 5 Gateway HTTP client
    chunk_id = str(uuid.uuid4())
    res_id = str(uuid.uuid4())
    lib_id = str(uuid.uuid4())

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "query": "photosynthesis chloroplasts",
        "result_count": 1,
        "embedding_model": "text-embedding-3-small",
        "embedding_version": "1",
        "results": [
            {
                "chunk_id": chunk_id,
                "score": 0.92,
                "text": "Chloroplasts contain chlorophyll which absorbs sunlight.",
                "provenance": {
                    "resource_id": res_id,
                    "resource_name": "Bio101.pdf",
                    "library_id": lib_id,
                    "library_name": "Biology Library",
                    "page_start": 50,
                    "page_end": 50,
                    "section": "Chapter 5",
                    "sequence": 1,
                    "char_start": 0,
                    "char_end": 500,
                    "content_sha256": "sha256hash",
                },
            }
        ],
        "metadata": {"search_time_ms": 10},
    }
    mock_client.post.return_value = mock_resp

    # 3. Setup capabilities in ToolRegistry
    calc_tool = CalculatorTool()
    search_tool = KnowledgeSearchTool(
        credential_vault=vault,
        http_client=mock_client,
    )
    registry = ToolRegistry([calc_tool, search_tool])

    # 4. Setup WorkingContextBuffer
    buffer = WorkingContextBuffer(
        system_prompt="You are a helpful biology tutor.",
        history_messages=[],
    )
    buffer.add_user_message("How do plants capture light energy?")

    # 5. Model step 1: emits tool call request
    model_provider = FakeModelProvider()
    tc = ToolCallRequest(
        call_id="call-knowledge-1",
        tool_name="knowledge_search",
        arguments_json='{"query": "photosynthesis chloroplasts", "top_k": 3}',
    )
    model_provider.add_response(
        content=None,
        tool_calls=[tc],
        finish_reason="tool_calls",
    )

    resp1 = await model_provider.generate(messages=buffer.get_messages_for_model())
    assert resp1.finish_reason == "tool_calls"
    assert resp1.message.tool_calls == [tc]

    # Record assistant message into memory
    buffer.add_assistant_message(tool_calls=[tc])

    # 6. Execute capability via ToolRegistry
    tool_result = await registry.execute(tc, context)
    assert tool_result.success is True
    assert "Chloroplasts contain chlorophyll" in tool_result.output
    assert tool_result.citation_evidence is not None
    assert len(tool_result.citation_evidence) == 1

    # Record tool result into memory
    buffer.add_tool_result(tool_result)
    assert len(buffer.citations) == 1

    # 7. Model step 2: synthesizes answer using tool result
    final_answer = (
        "Plants capture light energy using chloroplasts, which contain chlorophyll."
    )
    model_provider.add_response(content=final_answer, finish_reason="stop")

    resp2 = await model_provider.generate(messages=buffer.get_messages_for_model())
    assert resp2.message.content == final_answer

    # 8. Terminal cleanup: purge credentials from vault
    assert vault.purge(run_id) is True
    assert vault.retrieve(run_id) is None
