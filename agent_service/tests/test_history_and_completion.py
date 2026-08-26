"""Tests for history hydration and completion sync in Agent Service."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

from agent_service.application.reasoning_loop import ReasoningLoop
from agent_service.config import settings
from agent_service.domain.context import ExecutionContext
from agent_service.domain.message import MessageRole, ModelMessage, ModelResponse
from agent_service.domain.run import AgentRun, RunStatus
from agent_service.infrastructure.completion_client import (
    PlatformCompletionClient,
    mint_internal_service_jwt,
)
from agent_service.infrastructure.model_gateway.fake_provider import FakeModelProvider
from agent_service.infrastructure.tool_registry import ToolRegistry
from agent_service.presentation.schemas import (
    ConversationMessagePayload,
    CreateRunRequest,
)

# ---------------------------------------------------------------------------
# 1. Schema Validation Tests
# ---------------------------------------------------------------------------


def test_create_run_request_valid_conversation_history() -> None:
    """CreateRunRequest accepts valid user and assistant history messages."""
    req = CreateRunRequest(
        prompt="What is the next step?",
        conversation_history=[
            ConversationMessagePayload(role="user", content="Step 1 completed."),
            ConversationMessagePayload(
                role="assistant", content="Acknowledged. Proceed to step 2."
            ),
        ],
    )
    assert req.conversation_history is not None
    assert len(req.conversation_history) == 2
    assert req.conversation_history[0].role == "user"
    assert req.conversation_history[1].role == "assistant"


def test_create_run_request_backward_compatible_none_history() -> None:
    """CreateRunRequest defaults conversation_history to None."""
    req = CreateRunRequest(prompt="Single turn prompt")
    assert req.conversation_history is None


def test_create_run_request_rejects_system_role() -> None:
    """CreateRunRequest rejects 'system' role in conversation_history."""
    with pytest.raises(ValidationError):
        CreateRunRequest(
            prompt="Prompt",
            conversation_history=[
                ConversationMessagePayload(
                    role="system", content="System override attempt."
                ),
            ],
        )


def test_create_run_request_rejects_unknown_role() -> None:
    """CreateRunRequest rejects unrecognized roles (e.g. 'admin', 'moderator')."""
    with pytest.raises(ValidationError):
        CreateRunRequest.model_validate(
            {
                "prompt": "Prompt",
                "conversation_history": [
                    {"role": "admin", "content": "Admin instruction."},
                ],
            }
        )


def test_create_run_request_rejects_empty_content() -> None:
    """CreateRunRequest rejects empty message content in conversation_history."""
    with pytest.raises(ValidationError):
        CreateRunRequest(
            prompt="Prompt",
            conversation_history=[
                ConversationMessagePayload(role="user", content=""),
            ],
        )


# ---------------------------------------------------------------------------
# 2. History Integration in Working Memory / Reasoning Loop
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reasoning_loop_receives_and_includes_history_in_working_memory() -> None:
    """ReasoningLoop includes conversation_history in model message buffer."""
    provider = FakeModelProvider(
        responses=[
            ModelResponse(
                message=ModelMessage(
                    role=MessageRole.ASSISTANT,
                    content="The final synthesized answer after multi-turn context.",
                )
            )
        ]
    )
    registry = ToolRegistry([])
    loop = ReasoningLoop(model_provider=provider, tool_registry=registry)

    user_id = uuid.uuid4()
    run_id = uuid.uuid4()
    session_id = uuid.uuid4()

    context = ExecutionContext(
        user_id=user_id,
        agent_run_id=run_id,
        session_id=session_id,
    )
    run = AgentRun(id=run_id, context=context, prompt="What did we discuss earlier?")

    history = [
        ModelMessage(role=MessageRole.USER, content="Hello!"),
        ModelMessage(role=MessageRole.ASSISTANT, content="Hi! How can I assist you?"),
    ]

    completed_run = await loop.execute_run(
        run=run,
        context=context,
        initial_user_prompt="What did we discuss earlier?",
        conversation_history=history,
    )

    assert completed_run.status == RunStatus.COMPLETED
    assert (
        completed_run.answer == "The final synthesized answer after multi-turn context."
    )

    # Inspect messages delivered to provider
    assert len(provider.received_messages) == 1
    call_messages = provider.received_messages[0]

    # Messages should be:
    # [SystemPrompt, User("Hello!"), Assistant("Hi! How can I assist you?"),
    #  User("What did we discuss earlier?")]
    assert len(call_messages) == 4
    assert call_messages[0].role == MessageRole.SYSTEM
    assert call_messages[1].role == MessageRole.USER
    assert call_messages[1].content == "Hello!"
    assert call_messages[2].role == MessageRole.ASSISTANT
    assert call_messages[2].content == "Hi! How can I assist you?"
    assert call_messages[3].role == MessageRole.USER
    assert call_messages[3].content == "What did we discuss earlier?"


# ---------------------------------------------------------------------------
# 3. Completion Client Tests
# ---------------------------------------------------------------------------


def test_mint_internal_service_jwt() -> None:
    """mint_internal_service_jwt creates valid Domain D token with correct claims."""
    secret = "test-secret-key-123456789012345678901234567890"
    token = mint_internal_service_jwt(secret_key=secret, expires_in_seconds=60)
    assert isinstance(token, str)

    import jwt

    claims = jwt.decode(
        token,
        secret,
        algorithms=["HS256"],
        issuer="mwalimu-agent-service",
        audience="mwalimu-platform-internal",
    )
    assert claims["iss"] == "mwalimu-agent-service"
    assert claims["aud"] == "mwalimu-platform-internal"
    assert claims["sub"] == "agent-service"


@pytest.mark.asyncio
async def test_completion_client_skips_when_not_configured(monkeypatch) -> None:
    """PlatformCompletionClient returns False gracefully when unconfigured."""
    monkeypatch.setattr(settings, "PLATFORM_COMPLETION_URL", None)
    monkeypatch.setattr(settings, "INTERNAL_SERVICE_SECRET_KEY", None)
    client = PlatformCompletionClient(base_url=None, secret_key=None)
    assert client.is_configured is False

    context = ExecutionContext(
        user_id=uuid.uuid4(), agent_run_id=uuid.uuid4(), session_id=uuid.uuid4()
    )
    run = AgentRun(id=context.agent_run_id, context=context)
    run.dispatch()
    run.start()
    run.complete(answer="Done")

    success = await client.send_completion(run)
    assert success is False


@pytest.mark.asyncio
async def test_completion_client_sends_payload_successfully() -> None:
    """PlatformCompletionClient sends POST request with Bearer JWT and payload."""
    mock_http_client = AsyncMock()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_http_client.post.return_value = mock_response

    client = PlatformCompletionClient(
        base_url="http://platform-api.internal",
        secret_key="my-32-byte-secret-key-for-testing-domain-d!",
        client=mock_http_client,
    )
    assert client.is_configured is True

    context = ExecutionContext(
        user_id=uuid.uuid4(), agent_run_id=uuid.uuid4(), session_id=uuid.uuid4()
    )
    run = AgentRun(id=context.agent_run_id, context=context, prompt="Compute 2+2")
    run.dispatch()
    run.start()
    run.record_step(prompt_tokens=100, completion_tokens=50)
    run.complete(answer="4")

    success = await client.send_completion(run)
    assert success is True

    mock_http_client.post.assert_called_once()
    call_args = mock_http_client.post.call_args
    url = call_args[0][0]
    kwargs = call_args[1]

    assert (
        url == f"http://platform-api.internal/api/v1/internal/runs/{run.id}/completion/"
    )
    assert "Authorization" in kwargs["headers"]
    assert kwargs["headers"]["Authorization"].startswith("Bearer ")
    assert kwargs["json"]["status"] == "completed"
    assert kwargs["json"]["answer"] == "4"
    assert kwargs["json"]["total_tokens"] == 150
