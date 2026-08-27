"""Unit tests for KnowledgeSearchTool and Slice 5 Gateway integration."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from agent_service.domain.context import ExecutionContext
from agent_service.infrastructure.credential_vault import DelegatedCredentialVault
from agent_service.infrastructure.tools.knowledge_search import KnowledgeSearchTool


def _create_test_context() -> ExecutionContext:
    return ExecutionContext(
        user_id=uuid.uuid4(),
        agent_run_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
    )


@pytest.mark.asyncio
async def test_knowledge_search_missing_credential_fails_safely() -> None:
    """Missing credential in vault produces safe error without raising exception."""
    vault = DelegatedCredentialVault()
    tool = KnowledgeSearchTool(credential_vault=vault)
    ctx = _create_test_context()

    res = await tool.execute(arguments={"query": "mitochondria"}, context=ctx)
    assert res.success is False
    assert "credential missing" in (res.error or "").lower()


@pytest.mark.asyncio
async def test_knowledge_search_preserves_14_field_evidence_contract() -> None:
    """14-field evidence from Gateway response is mapped into EvidenceCitation."""
    vault = DelegatedCredentialVault()
    ctx = _create_test_context()
    raw_token = "secret-delegated-token-12345"
    vault.store(ctx.agent_run_id, raw_token)

    mock_client = AsyncMock(spec=httpx.AsyncClient)

    chunk_uuid = str(uuid.uuid4())
    res_uuid = str(uuid.uuid4())
    lib_uuid = str(uuid.uuid4())

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "query": "photosynthesis",
        "result_count": 1,
        "embedding_model": "text-embedding-3-small",
        "embedding_version": "1",
        "results": [
            {
                "chunk_id": chunk_uuid,
                "score": 0.892,
                "text": "Chloroplasts perform photosynthesis in plant cells.",
                "provenance": {
                    "resource_id": res_uuid,
                    "resource_name": "Plant_Biology.pdf",
                    "library_id": lib_uuid,
                    "library_name": "Biology 101",
                    "page_start": 42,
                    "page_end": 43,
                    "section": "Chapter 4 > Light Reactions",
                    "sequence": 7,
                    "char_start": 12000,
                    "char_end": 13500,
                    "content_sha256": "abc123sha256",
                },
            }
        ],
        "metadata": {"search_time_ms": 15},
    }
    mock_client.post.return_value = mock_response

    tool = KnowledgeSearchTool(credential_vault=vault, http_client=mock_client)
    res = await tool.execute(
        arguments={"query": "photosynthesis", "top_k": 5}, context=ctx
    )

    assert res.success is True
    assert "Chloroplasts perform photosynthesis" in res.output
    assert "Plant_Biology.pdf" in res.output
    assert res.citation_evidence is not None
    assert len(res.citation_evidence) == 1

    cit = res.citation_evidence[0]
    assert str(cit.chunk_id) == chunk_uuid
    assert str(cit.resource_id) == res_uuid
    assert cit.resource_name == "Plant_Biology.pdf"
    assert str(cit.library_id) == lib_uuid
    assert cit.library_name == "Biology 101"
    assert cit.page_start == 42
    assert cit.page_end == 43
    assert cit.section == "Chapter 4 > Light Reactions"
    assert cit.sequence == 7
    assert cit.char_start == 12000
    assert cit.char_end == 13500
    assert cit.content_sha256 == "abc123sha256"
    assert cit.score == 0.892

    # Verify Authorization header and endpoint
    mock_client.post.assert_called_once()
    call_kwargs = mock_client.post.call_args.kwargs
    assert call_kwargs["headers"]["Authorization"] == f"Bearer {raw_token}"
    assert call_kwargs["json"]["query"] == "photosynthesis"
    assert call_kwargs["json"]["top_k"] == 5

    # Verify secret token is NOT in output or result
    assert raw_token not in res.output
    assert raw_token not in (res.error or "")


@pytest.mark.asyncio
async def test_knowledge_search_error_responses() -> None:
    """HTTP 401, 429, 500, timeout, and connection errors are normalized."""
    vault = DelegatedCredentialVault()
    ctx = _create_test_context()
    vault.store(ctx.agent_run_id, "token-1")

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    tool = KnowledgeSearchTool(credential_vault=vault, http_client=mock_client)

    # 1. 401 / 403
    mock_client.post.return_value = MagicMock(status_code=401)
    res_401 = await tool.execute(arguments={"query": "test"}, context=ctx)
    assert res_401.success is False
    assert "unauthorized" in (res_401.error or "").lower()

    # 2. 429
    mock_client.post.return_value = MagicMock(status_code=429)
    res_429 = await tool.execute(arguments={"query": "test"}, context=ctx)
    assert res_429.success is False
    assert "rate limit" in (res_429.error or "").lower()

    # 3. 503
    mock_client.post.return_value = MagicMock(status_code=503)
    res_503 = await tool.execute(arguments={"query": "test"}, context=ctx)
    assert res_503.success is False
    assert "temporarily unavailable" in (res_503.error or "").lower()

    # 4. Timeout
    mock_client.post.side_effect = httpx.TimeoutException("Timeout")
    res_timeout = await tool.execute(arguments={"query": "test"}, context=ctx)
    assert res_timeout.success is False
    assert "timed out" in (res_timeout.error or "").lower()

    # 5. Connection error
    mock_client.post.side_effect = httpx.ConnectError("Connection refused")
    res_conn = await tool.execute(arguments={"query": "test"}, context=ctx)
    assert res_conn.success is False
    assert "failed to connect" in (res_conn.error or "").lower()


@pytest.mark.asyncio
async def test_knowledge_search_handles_title_fallback_schema() -> None:
    """Test fallback when Gateway uses 'title' and verify CitationResponse."""
    from agent_service.presentation.schemas import CitationResponse

    vault = DelegatedCredentialVault()
    ctx = _create_test_context()
    vault.store(ctx.agent_run_id, "token-fallback")

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    res_uuid = str(uuid.uuid4())
    lib_uuid = str(uuid.uuid4())

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "query": "soil notes",
        "results": [
            {
                "chunk_id": str(uuid.uuid4()),
                "score": 0.95,
                "text": "Vetiver grass roots go 3 meters deep.",
                "provenance": {
                    "resource_id": res_uuid,
                    "title": "Soil_Science_Notes.pdf",
                    "library_id": lib_uuid,
                    "library_name": "Amina Notes",
                },
            }
        ],
    }
    mock_client.post.return_value = mock_response

    tool = KnowledgeSearchTool(credential_vault=vault, http_client=mock_client)
    res = await tool.execute(arguments={"query": "soil notes"}, context=ctx)

    assert res.success is True
    assert res.citation_evidence is not None
    assert len(res.citation_evidence) == 1
    domain_cit = res.citation_evidence[0]
    assert domain_cit.resource_name == "Soil_Science_Notes.pdf"

    # Verify presentation schema mapping sets both title and resource_name
    schema_cit = CitationResponse.from_domain(domain_cit)
    assert schema_cit.resource_name == "Soil_Science_Notes.pdf"
    assert schema_cit.title == "Soil_Science_Notes.pdf"
    assert schema_cit.library_name == "Amina Notes"

