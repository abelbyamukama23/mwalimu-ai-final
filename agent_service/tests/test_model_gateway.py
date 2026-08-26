"""Unit and integration tests for Model Gateway provider adapters and errors."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import openai
import pytest

from agent_service.config import Settings
from agent_service.domain.message import (
    MessageRole,
    ModelMessage,
    ToolCallRequest,
)
from agent_service.domain.protocols import (
    ModelProviderProtocol,
    ToolDefinition,
)
from agent_service.infrastructure.model_gateway import (
    BaseOpenAIAdapter,
    DeepSeekProvider,
    FakeModelProvider,
    GeminiProvider,
    ModelAuthenticationError,
    ModelInvalidRequestError,
    ModelRateLimitError,
    ModelTimeoutError,
    ModelUnavailableError,
    OpenAIProvider,
    get_model_provider,
)


def test_provider_protocol_compliance() -> None:
    """All provider adapters satisfy ModelProviderProtocol at runtime."""
    openai_p = OpenAIProvider()
    gemini_p = GeminiProvider()
    deepseek_p = DeepSeekProvider()
    custom_p = BaseOpenAIAdapter(provider_name="custom", default_model="m1")
    fake_p = FakeModelProvider()

    for p in [openai_p, gemini_p, deepseek_p, custom_p, fake_p]:
        assert isinstance(p, ModelProviderProtocol)


@pytest.mark.asyncio
async def test_openai_adapter_request_response_translation() -> None:
    """BaseOpenAIAdapter converts domain messages and normalizes response."""
    mock_client = MagicMock()
    mock_create = AsyncMock()
    mock_client.chat.completions.create = mock_create

    # Mock OpenAI response structure
    mock_choice = MagicMock()
    mock_choice.finish_reason = "stop"
    mock_choice.message.content = "Photosynthesis is the process..."
    mock_choice.message.tool_calls = None

    mock_usage = MagicMock()
    mock_usage.prompt_tokens = 25
    mock_usage.completion_tokens = 10
    mock_usage.total_tokens = 35

    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_response.usage = mock_usage
    mock_create.return_value = mock_response

    adapter = BaseOpenAIAdapter(
        provider_name="openai",
        default_model="gpt-4o",
        client=mock_client,
    )

    messages = [
        ModelMessage(role=MessageRole.SYSTEM, content="You are a tutor."),
        ModelMessage(role=MessageRole.USER, content="Explain photosynthesis."),
    ]
    tool = ToolDefinition(
        name="search",
        description="Search textbook",
        parameters_schema={"type": "object", "properties": {"q": {"type": "string"}}},
    )

    response = await adapter.generate(messages=messages, tools=[tool])

    assert response.message.role == MessageRole.ASSISTANT
    assert response.message.content == "Photosynthesis is the process..."
    assert response.finish_reason == "stop"
    assert response.usage.prompt_tokens == 25
    assert response.usage.completion_tokens == 10
    assert response.usage.total_tokens == 35

    # Verify message payload sent to SDK
    called_kwargs = mock_create.call_args.kwargs
    assert called_kwargs["model"] == "gpt-4o"
    assert len(called_kwargs["messages"]) == 2
    assert called_kwargs["messages"][0] == {
        "role": "system",
        "content": "You are a tutor.",
    }
    assert called_kwargs["messages"][1] == {
        "role": "user",
        "content": "Explain photosynthesis.",
    }
    assert len(called_kwargs["tools"]) == 1
    assert called_kwargs["tools"][0]["function"]["name"] == "search"


@pytest.mark.asyncio
async def test_tool_call_response_normalization() -> None:
    """Tool calls in provider response are translated to ToolCallRequest."""
    mock_client = MagicMock()
    mock_create = AsyncMock()
    mock_client.chat.completions.create = mock_create

    # Mock tool call in response
    mock_tc1 = MagicMock()
    mock_tc1.id = "call_abc123"
    mock_tc1.function.name = "knowledge_search"
    mock_tc1.function.arguments = '{"query": "chloroplasts", "top_k": 5}'

    mock_choice = MagicMock()
    mock_choice.finish_reason = "tool_calls"
    mock_choice.message.content = None
    mock_choice.message.tool_calls = [mock_tc1]

    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_response.usage = None
    mock_create.return_value = mock_response

    adapter = BaseOpenAIAdapter(
        provider_name="openai", default_model="gpt-4o", client=mock_client
    )
    response = await adapter.generate(
        messages=[
            ModelMessage(role=MessageRole.USER, content="Search for chloroplasts")
        ]
    )

    assert response.finish_reason == "tool_calls"
    assert response.message.tool_calls is not None
    assert len(response.message.tool_calls) == 1

    tc = response.message.tool_calls[0]
    assert tc.call_id == "call_abc123"
    assert tc.tool_name == "knowledge_search"
    assert tc.arguments_json == '{"query": "chloroplasts", "top_k": 5}'


@pytest.mark.asyncio
async def test_streaming_normalization() -> None:
    """Streaming chunks are normalized to ModelStreamChunk instances."""
    mock_client = MagicMock()
    mock_create = AsyncMock()
    mock_client.chat.completions.create = mock_create

    # Mock stream chunks
    c1 = MagicMock()
    c1.choices = [
        MagicMock(delta=MagicMock(content="Hello", tool_calls=None), finish_reason=None)
    ]
    c1.usage = None

    c2 = MagicMock()
    c2.choices = [
        MagicMock(
            delta=MagicMock(content=" world!", tool_calls=None), finish_reason="stop"
        )
    ]
    c2.usage = MagicMock(prompt_tokens=5, completion_tokens=2, total_tokens=7)

    async def fake_stream():
        yield c1
        yield c2

    mock_create.return_value = fake_stream()

    adapter = BaseOpenAIAdapter(
        provider_name="openai", default_model="gpt-4o", client=mock_client
    )
    chunks = []
    async for chunk in adapter.stream_generate(
        messages=[ModelMessage(role=MessageRole.USER, content="Hi")]
    ):
        chunks.append(chunk)

    assert len(chunks) == 2
    assert chunks[0].delta_content == "Hello"
    assert chunks[0].finish_reason is None
    assert chunks[1].delta_content == " world!"
    assert chunks[1].finish_reason == "stop"
    assert chunks[1].usage is not None
    assert chunks[1].usage.total_tokens == 7


@pytest.mark.asyncio
async def test_provider_error_translation() -> None:
    """OpenAI SDK exceptions are translated into standardized domain exceptions."""
    mock_client = MagicMock()
    mock_create = AsyncMock()
    mock_client.chat.completions.create = mock_create
    adapter = BaseOpenAIAdapter(
        provider_name="openai", default_model="gpt-4o", client=mock_client
    )

    msg = [ModelMessage(role=MessageRole.USER, content="Hi")]

    # 1. AuthenticationError -> ModelAuthenticationError
    mock_create.side_effect = openai.AuthenticationError(
        "Invalid API Key", response=MagicMock(status_code=401), body=None
    )
    with pytest.raises(ModelAuthenticationError, match="Invalid API Key"):
        await adapter.generate(messages=msg)

    # 2. RateLimitError -> ModelRateLimitError
    mock_create.side_effect = openai.RateLimitError(
        "Rate limit exceeded", response=MagicMock(status_code=429), body=None
    )
    with pytest.raises(ModelRateLimitError, match="Rate limit"):
        await adapter.generate(messages=msg)

    # 3. APITimeoutError -> ModelTimeoutError
    mock_create.side_effect = openai.APITimeoutError(request=MagicMock())
    with pytest.raises(ModelTimeoutError):
        await adapter.generate(messages=msg)

    # 4. InternalServerError -> ModelUnavailableError
    mock_create.side_effect = openai.InternalServerError(
        "500 Internal Server Error", response=MagicMock(status_code=500), body=None
    )
    with pytest.raises(ModelUnavailableError):
        await adapter.generate(messages=msg)

    # 5. BadRequestError -> ModelInvalidRequestError
    mock_create.side_effect = openai.BadRequestError(
        "Context window exceeded", response=MagicMock(status_code=400), body=None
    )
    with pytest.raises(ModelInvalidRequestError, match="Context window"):
        await adapter.generate(messages=msg)


@pytest.mark.asyncio
async def test_cancellation_token_halts_execution() -> None:
    """Pre-set cancellation token immediately aborts without invoking provider."""
    mock_client = MagicMock()
    adapter = BaseOpenAIAdapter(
        provider_name="openai", default_model="gpt-4o", client=mock_client
    )

    token = asyncio.Event()
    token.set()  # Cancelled

    with pytest.raises(asyncio.CancelledError):
        await adapter.generate(
            messages=[ModelMessage(role=MessageRole.USER, content="Hello")],
            cancellation_token=token,
        )

    mock_client.chat.completions.create.assert_not_called()


def test_factory_provider_instantiation() -> None:
    """get_model_provider correctly instantiates configured provider adapters."""
    # 1. OpenAI
    cfg_openai = Settings(
        DEFAULT_MODEL_PROVIDER="openai", OPENAI_DEFAULT_MODEL="gpt-4o-mini"
    )
    p_openai = get_model_provider(cfg_openai)
    assert isinstance(p_openai, OpenAIProvider)
    assert p_openai.provider_name == "openai"
    assert p_openai.default_model == "gpt-4o-mini"

    # 2. Gemini
    cfg_gemini = Settings(
        DEFAULT_MODEL_PROVIDER="gemini", GEMINI_DEFAULT_MODEL="gemini-1.5-pro"
    )
    p_gemini = get_model_provider(cfg_gemini)
    assert isinstance(p_gemini, GeminiProvider)
    assert p_gemini.provider_name == "gemini"
    assert p_gemini.default_model == "gemini-1.5-pro"

    # 3. DeepSeek
    cfg_ds = Settings(DEFAULT_MODEL_PROVIDER="deepseek")
    p_ds = get_model_provider(cfg_ds)
    assert isinstance(p_ds, DeepSeekProvider)
    assert p_ds.provider_name == "deepseek"
    assert p_ds.default_model == "deepseek-chat"

    # 4. Fake
    cfg_fake = Settings(DEFAULT_MODEL_PROVIDER="fake")
    p_fake = get_model_provider(cfg_fake)
    assert isinstance(p_fake, FakeModelProvider)
    assert p_fake.provider_name == "fake"

    # 5. Invalid provider raises ValueError
    cfg_invalid = Settings(DEFAULT_MODEL_PROVIDER="unsupported-provider")
    with pytest.raises(ValueError, match="Unsupported model provider"):
        get_model_provider(cfg_invalid)


@pytest.mark.asyncio
async def test_fake_model_provider_deterministic_behavior() -> None:
    """FakeModelProvider yields queued responses and simulates tool calls and errors."""
    fake = FakeModelProvider()

    # 1. Default response
    r1 = await fake.generate(
        messages=[ModelMessage(role=MessageRole.USER, content="Q1")]
    )
    assert r1.message.content == "Default deterministic response."
    assert fake.call_count == 1

    # 2. Sequential responses with tool call
    tc = ToolCallRequest(
        call_id="c1", tool_name="search", arguments_json='{"q": "dna"}'
    )
    fake.add_response(content=None, tool_calls=[tc], finish_reason="tool_calls")
    fake.add_response(content="DNA is a double helix.")

    r2 = await fake.generate(
        messages=[ModelMessage(role=MessageRole.USER, content="Q2")]
    )
    assert r2.finish_reason == "tool_calls"
    assert r2.message.tool_calls == [tc]

    r3 = await fake.generate(
        messages=[ModelMessage(role=MessageRole.USER, content="Q3")]
    )
    assert r3.message.content == "DNA is a double helix."
    assert fake.call_count == 3

    # 3. Simulated error
    fake.error_to_raise = ModelRateLimitError("Quota exceeded", provider="fake")
    with pytest.raises(ModelRateLimitError, match="Quota exceeded"):
        await fake.generate(
            messages=[ModelMessage(role=MessageRole.USER, content="Q4")]
        )


@pytest.mark.asyncio
async def test_credential_non_leakage() -> None:
    """API keys are never echoed in ModelMessage or ModelResponse representations."""
    fake_key = "sk-super-secret-key-12345"
    adapter = BaseOpenAIAdapter(
        provider_name="openai",
        default_model="gpt-4o",
        api_key=fake_key,
        client=MagicMock(),
    )

    # Verify adapter representation does not leak key
    assert fake_key not in repr(adapter)
    assert fake_key not in str(adapter)
